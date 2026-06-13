"""
AFK Fishing Macro for Deepwoken — Standalone Application
Автономное приложение для AFK рыбалки в Deepwoken с GUI.

Механика рыбалки Deepwoken:
1. Закидываем удочку (ЛКМ)
2. Появляется мини-игра QTE — на экране подсвечиваются буквы A, S, D
3. Нужно зажимать соответствующую клавишу + ЛКМ когда буква появляется
4. После завершения — перезаброс
5. Периодически едим из слота с едой
"""

import ctypes
import json
import os
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk

from pynput.keyboard import Controller as KeyboardController
from pynput.keyboard import Key, KeyCode, Listener as KeyboardListener
from pynput.mouse import Button
from pynput.mouse import Controller as MouseController

# ---------------------------------------------------------------------------
# Keyboard / Mouse controllers
# ---------------------------------------------------------------------------
keyboard = KeyboardController()
mouse = MouseController()

SLOT_KEYS = {
    "1": KeyCode.from_char("1"),
    "2": KeyCode.from_char("2"),
    "3": KeyCode.from_char("3"),
    "4": KeyCode.from_char("4"),
    "5": KeyCode.from_char("5"),
    "6": KeyCode.from_char("6"),
    "7": KeyCode.from_char("7"),
    "8": KeyCode.from_char("8"),
    "9": KeyCode.from_char("9"),
    "0": KeyCode.from_char("0"),
}

KEY_A = KeyCode.from_char("a")
KEY_S = KeyCode.from_char("s")
KEY_D = KeyCode.from_char("d")

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

# Default QTE scan regions for 1920x1080 (from original AHK macro)
DEFAULT_REGIONS = {
    "a_x": 880, "a_y": 580,
    "s_x": 950, "s_y": 640,
    "d_x": 1010, "d_y": 575,
    "region_size": 25,
}

# White pixel detection settings
PIXEL_COLOR_TARGET = (255, 255, 255)  # 0xFFFFFF
PIXEL_TOLERANCE = 90


# ---------------------------------------------------------------------------
# Screen capture — uses Windows API (GDI) for speed, fallback to mss
# ---------------------------------------------------------------------------
def _is_windows():
    return sys.platform == "win32"


if _is_windows():
    import ctypes.wintypes

    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32

    def scan_region_for_white(x, y, w, h):
        """Scan a screen region for white-ish pixels using GDI (fast)."""
        hdc_screen = user32.GetDC(0)
        hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
        hbmp = gdi32.CreateCompatibleBitmap(hdc_screen, w, h)
        gdi32.SelectObject(hdc_mem, hbmp)
        gdi32.BitBlt(hdc_mem, 0, 0, w, h, hdc_screen, x, y, 0x00CC0020)

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [
                ("biSize", ctypes.wintypes.DWORD),
                ("biWidth", ctypes.wintypes.LONG),
                ("biHeight", ctypes.wintypes.LONG),
                ("biPlanes", ctypes.wintypes.WORD),
                ("biBitCount", ctypes.wintypes.WORD),
                ("biCompression", ctypes.wintypes.DWORD),
                ("biSizeImage", ctypes.wintypes.DWORD),
                ("biXPelsPerMeter", ctypes.wintypes.LONG),
                ("biYPelsPerMeter", ctypes.wintypes.LONG),
                ("biClrUsed", ctypes.wintypes.DWORD),
                ("biClrImportant", ctypes.wintypes.DWORD),
            ]

        bmi = BITMAPINFOHEADER()
        bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.biWidth = w
        bmi.biHeight = -h  # top-down
        bmi.biPlanes = 1
        bmi.biBitCount = 32
        bmi.biCompression = 0

        buf = ctypes.create_string_buffer(w * h * 4)
        gdi32.GetDIBits(hdc_mem, hbmp, 0, h, buf, ctypes.byref(bmi), 0)

        gdi32.DeleteObject(hbmp)
        gdi32.DeleteDC(hdc_mem)
        user32.ReleaseDC(0, hdc_screen)

        tol = PIXEL_TOLERANCE
        raw = buf.raw
        for i in range(0, len(raw), 4):
            b, g, r = raw[i], raw[i + 1], raw[i + 2]
            if (abs(r - 255) <= tol and abs(g - 255) <= tol and abs(b - 255) <= tol):
                return True
        return False
else:
    try:
        import mss
        import mss.tools
        _sct = mss.mss()
    except ImportError:
        _sct = None

    def scan_region_for_white(x, y, w, h):
        """Scan a screen region for white-ish pixels using mss (cross-platform)."""
        if _sct is None:
            return False
        monitor = {"left": x, "top": y, "width": w, "height": h}
        img = _sct.grab(monitor)
        tol = PIXEL_TOLERANCE
        pixels = img.raw  # BGRA bytes
        for i in range(0, len(pixels), 4):
            b, g, r = pixels[i], pixels[i + 1], pixels[i + 2]
            if (abs(r - 255) <= tol and abs(g - 255) <= tol and abs(b - 255) <= tol):
                return True
        return False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def tap_key(key, hold=0.05):
    keyboard.press(key)
    time.sleep(hold)
    keyboard.release(key)


def press_key(key):
    keyboard.press(key)


def release_key(key):
    keyboard.release(key)


def left_click():
    mouse.click(Button.left)


def left_down():
    mouse.press(Button.left)


def left_up():
    mouse.release(Button.left)


# ---------------------------------------------------------------------------
# Fishing Macro Engine
# ---------------------------------------------------------------------------
class FishingMacro:
    """
    Deepwoken fishing macro logic:
    - Scans screen for QTE prompts (A/S/D white regions)
    - Holds corresponding key + LMB when detected
    - Re-casts when no QTE detected for a while (failsafe)
    - Eats food every N minutes
    - Anti-AFK movement
    """

    FAILSAFE_MAX = 25      # ticks before re-cast (1 tick = ~0.1s of scan cycle)
    FAILSAFE_QTE = 3        # failsafe resets to this when QTE detected
    SCAN_INTERVAL = 0.08    # seconds between scans (~100ms like AHK)

    def __init__(self, app):
        self.app = app
        self._running = False
        self._thread = None
        self._stop_event = threading.Event()

    @property
    def running(self):
        return self._running

    def start(self):
        if self._running:
            return
        self._stop_event.clear()
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        self.app.log("Макрос запущен")

    def stop(self):
        if not self._running:
            return
        self._stop_event.set()
        self._running = False
        # Release all keys on stop
        for k in (KEY_A, KEY_S, KEY_D):
            try:
                release_key(k)
            except Exception:
                pass
        try:
            left_up()
        except Exception:
            pass
        self.app.log("Макрос остановлен")

    def _stopped(self):
        return self._stop_event.is_set()

    def _sleep(self, seconds):
        """Sleep with stop-check."""
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if self._stopped():
                return True
            time.sleep(min(0.05, end - time.monotonic()))
        return False

    # -- Eating --------------------------------------------------------------

    def _eat(self):
        """Switch to food, eat (LMB), switch back to rod, re-cast."""
        food_key = SLOT_KEYS[self.app.food_slot.get()]
        rod_key = SLOT_KEYS[self.app.rod_slot.get()]

        self.app.log("Переключение на еду...")

        # Release everything first
        for k in (KEY_A, KEY_S, KEY_D):
            release_key(k)
        left_up()
        if self._sleep(0.2):
            return

        # Equip food
        tap_key(food_key)
        if self._sleep(0.5):
            return

        # Eat (LMB click)
        left_click()
        self.app.log("Едим...")
        if self._sleep(3.0):
            return

        # Second click (sometimes needed)
        left_click()
        if self._sleep(3.0):
            return

        # Switch back to rod
        self.app.log("Возврат к удочке")
        tap_key(rod_key)
        if self._sleep(1.0):
            return

        # Re-cast
        left_click()
        self.app.log("Перезаброс после еды")
        if self._sleep(0.1):
            return

    # -- Anti-AFK ------------------------------------------------------------

    def _anti_afk(self):
        self.app.log("Анти-АФК движение")
        tap_key(KEY_D, hold=0.12)
        if self._sleep(0.2):
            return
        tap_key(KEY_A, hold=0.12)

    # -- Casting (re-cast with failsafe) ------------------------------------

    def _recast(self):
        """Release all, eat canteen, re-equip rod, cast."""
        self.app.log("Перезаброс удочки...")

        for k in (KEY_A, KEY_S, KEY_D):
            release_key(k)
        left_up()
        if self._sleep(0.25):
            return

        rod_key = SLOT_KEYS[self.app.rod_slot.get()]
        tap_key(rod_key)
        if self._sleep(1.0):
            return

        # Cast
        left_down()
        if self._sleep(0.02):
            return
        left_up()
        self.app.log("Удочка заброшена")

    # -- QTE scanning -------------------------------------------------------

    def _get_regions(self):
        """Get current scan regions from GUI settings."""
        size = self.app.region_size.get()
        return {
            "a": (self.app.a_x.get(), self.app.a_y.get(), size, size),
            "s": (self.app.s_x.get(), self.app.s_y.get(), size, size),
            "d": (self.app.d_x.get(), self.app.d_y.get(), size, size),
        }

    def _scan_qte(self, regions):
        """Scan for QTE prompts and respond. Returns True if any QTE detected."""
        detected = False

        # Scan A
        ax, ay, aw, ah = regions["a"]
        if scan_region_for_white(ax, ay, aw, ah):
            release_key(KEY_S)
            release_key(KEY_D)
            press_key(KEY_A)
            left_down()
            detected = True
        else:
            release_key(KEY_A)

        # Scan S
        sx, sy, sw, sh = regions["s"]
        if scan_region_for_white(sx, sy, sw, sh):
            release_key(KEY_A)
            release_key(KEY_D)
            press_key(KEY_S)
            left_click()
            detected = True
        else:
            release_key(KEY_S)

        # Scan D
        dx, dy, dw, dh = regions["d"]
        if scan_region_for_white(dx, dy, dw, dh):
            release_key(KEY_A)
            release_key(KEY_S)
            press_key(KEY_D)
            left_down()
            detected = True
        else:
            release_key(KEY_D)

        return detected

    # -- Main loop -----------------------------------------------------------

    def _loop(self):
        eat_interval = self.app.eat_interval.get() * 60  # min -> sec
        afk_interval = self.app.afk_interval.get()       # sec

        # Delay before start
        self.app.log("Старт через 3 сек — переключитесь в игру!")
        if self._sleep(3.0):
            self._running = False
            self.app.update_button_state()
            return

        # Initial cast
        rod_key = SLOT_KEYS[self.app.rod_slot.get()]
        tap_key(rod_key)
        if self._sleep(0.3):
            self._running = False
            self.app.update_button_state()
            return
        left_click()
        self.app.log("Удочка заброшена — начинаю сканирование QTE")

        failsafe = self.FAILSAFE_MAX
        last_eat = time.monotonic()
        last_afk = time.monotonic()
        scan_count = 0

        while not self._stopped():
            now = time.monotonic()

            # --- Eating (every N minutes) ---
            if now - last_eat >= eat_interval:
                self._eat()
                last_eat = time.monotonic()
                failsafe = self.FAILSAFE_MAX
                if self._stopped():
                    break
                continue

            # --- Anti-AFK ---
            if now - last_afk >= afk_interval:
                self._anti_afk()
                last_afk = time.monotonic()
                if self._stopped():
                    break

            # --- QTE scanning ---
            regions = self._get_regions()
            qte_found = self._scan_qte(regions)

            if qte_found:
                failsafe = self.FAILSAFE_QTE
                scan_count += 1
                if scan_count % 20 == 0:
                    self.app.log(f"QTE обнаружено (скан #{scan_count})")
            else:
                # Decrement failsafe every ~10 scans (≈1 second)
                scan_count += 1
                if scan_count % 10 == 0:
                    failsafe -= 1
                    self.app.update_failsafe(failsafe)

            # --- Failsafe: re-cast when no QTE for too long ---
            if failsafe <= 0:
                self.app.log("Нет QTE — перезаброс")
                self._recast()
                failsafe = self.FAILSAFE_MAX
                if self._stopped():
                    break

            # Scan interval
            time.sleep(self.SCAN_INTERVAL)

        # Cleanup
        for k in (KEY_A, KEY_S, KEY_D):
            try:
                release_key(k)
            except Exception:
                pass
        try:
            left_up()
        except Exception:
            pass
        self._running = False
        self.app.update_button_state()


# ---------------------------------------------------------------------------
# Config save/load
# ---------------------------------------------------------------------------
def save_config(data):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def load_config():
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# GUI Application
# ---------------------------------------------------------------------------
class App:
    BG = "#1a1a2e"
    FG = "#eaeaea"
    ACCENT = "#e94560"
    ENTRY_BG = "#16213e"
    BTN_START = "#00b894"
    BTN_STOP = "#d63031"

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("AFK Fishing Macro — Deepwoken")
        self.root.geometry("460x750")
        self.root.resizable(False, False)
        self.root.configure(bg=self.BG)

        cfg = load_config()

        # --- Variables ---
        self.food_slot = tk.StringVar(value=cfg.get("food_slot", "2"))
        self.rod_slot = tk.StringVar(value=cfg.get("rod_slot", "1"))
        self.eat_interval = tk.DoubleVar(value=cfg.get("eat_interval", 8.0))
        self.afk_interval = tk.DoubleVar(value=cfg.get("afk_interval", 30.0))

        # QTE scan regions
        self.a_x = tk.IntVar(value=cfg.get("a_x", DEFAULT_REGIONS["a_x"]))
        self.a_y = tk.IntVar(value=cfg.get("a_y", DEFAULT_REGIONS["a_y"]))
        self.s_x = tk.IntVar(value=cfg.get("s_x", DEFAULT_REGIONS["s_x"]))
        self.s_y = tk.IntVar(value=cfg.get("s_y", DEFAULT_REGIONS["s_y"]))
        self.d_x = tk.IntVar(value=cfg.get("d_x", DEFAULT_REGIONS["d_x"]))
        self.d_y = tk.IntVar(value=cfg.get("d_y", DEFAULT_REGIONS["d_y"]))
        self.region_size = tk.IntVar(value=cfg.get("region_size", DEFAULT_REGIONS["region_size"]))

        self.macro = FishingMacro(self)

        self._build_ui()
        self._setup_hotkey()

    # -- UI ------------------------------------------------------------------

    def _build_ui(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TCombobox", fieldbackground=self.ENTRY_BG,
                        background=self.ENTRY_BG, foreground=self.FG)

        # Title
        tk.Label(self.root, text="AFK Fishing Macro",
                 font=("Segoe UI", 20, "bold"),
                 bg=self.BG, fg=self.ACCENT).pack(pady=(14, 2))
        tk.Label(self.root, text="Deepwoken | QTE Auto-Fish",
                 font=("Segoe UI", 10), bg=self.BG, fg="#888").pack(pady=(0, 10))

        # ── Slot settings ──
        sf = tk.LabelFrame(self.root, text=" Слоты и таймеры ",
                           font=("Segoe UI", 11, "bold"),
                           bg=self.BG, fg=self.FG, bd=1, relief="groove")
        sf.pack(padx=14, pady=4, fill="x")

        slot_vals = list(SLOT_KEYS.keys())
        self._combo_row(sf, "Слот еды (1-0):", self.food_slot, slot_vals, 0)
        self._combo_row(sf, "Слот удочки (1-0):", self.rod_slot, slot_vals, 1)
        self._entry_row(sf, "Еда каждые (мин):", self.eat_interval, 2)
        self._entry_row(sf, "Анти-АФК (сек):", self.afk_interval, 3)

        # ── QTE scan regions ──
        qf = tk.LabelFrame(self.root, text=" Координаты QTE (1920x1080 по умолчанию) ",
                           font=("Segoe UI", 10, "bold"),
                           bg=self.BG, fg=self.FG, bd=1, relief="groove")
        qf.pack(padx=14, pady=4, fill="x")

        self._xy_row(qf, "A — X,Y:", self.a_x, self.a_y, 0)
        self._xy_row(qf, "S — X,Y:", self.s_x, self.s_y, 1)
        self._xy_row(qf, "D — X,Y:", self.d_x, self.d_y, 2)
        self._entry_row(qf, "Размер области:", self.region_size, 3)

        tk.Label(qf, text="Подсказка: координаты — верхний левый угол области сканирования",
                 font=("Segoe UI", 8), bg=self.BG, fg="#666",
                 wraplength=400).grid(row=4, column=0, columnspan=3, pady=(2, 6), padx=8)

        # ── Start / Stop ──
        self.btn = tk.Button(
            self.root, text="СТАРТ  (F6)", font=("Segoe UI", 14, "bold"),
            bg=self.BTN_START, fg="white", activebackground="#00a884",
            relief="flat", bd=0, cursor="hand2", command=self._toggle,
        )
        self.btn.pack(padx=14, pady=10, fill="x", ipady=8)

        # ── Status ──
        status_frame = tk.Frame(self.root, bg=self.BG)
        status_frame.pack(fill="x", padx=14)

        self.status_var = tk.StringVar(value="Остановлен")
        tk.Label(status_frame, textvariable=self.status_var,
                 font=("Segoe UI", 11), bg=self.BG, fg="#aaa").pack(side="left")

        self.failsafe_var = tk.StringVar(value="")
        tk.Label(status_frame, textvariable=self.failsafe_var,
                 font=("Segoe UI", 10), bg=self.BG, fg="#666").pack(side="right")

        # ── Log ──
        lf = tk.LabelFrame(self.root, text=" Лог ", font=("Segoe UI", 10, "bold"),
                           bg=self.BG, fg=self.FG, bd=1, relief="groove")
        lf.pack(padx=14, pady=8, fill="both", expand=True)

        self.log_text = tk.Text(lf, height=8, bg=self.ENTRY_BG, fg=self.FG,
                                font=("Consolas", 9), wrap="word", bd=0,
                                insertbackground=self.FG, state="disabled")
        self.log_text.pack(padx=4, pady=4, fill="both", expand=True)

        # ── Footer ──
        tk.Label(self.root, text="F6 — Старт/Стоп  |  Настройки сохраняются автоматически",
                 font=("Segoe UI", 9), bg=self.BG, fg="#555").pack(pady=(0, 6))

    def _combo_row(self, parent, text, var, values, row):
        tk.Label(parent, text=text, font=("Segoe UI", 10),
                 bg=self.BG, fg=self.FG, anchor="w"
                 ).grid(row=row, column=0, sticky="w", padx=(10, 4), pady=5)
        ttk.Combobox(parent, textvariable=var, values=values,
                     width=6, state="readonly", font=("Segoe UI", 10)
                     ).grid(row=row, column=1, columnspan=2, sticky="e", padx=(4, 10), pady=5)

    def _entry_row(self, parent, text, var, row):
        tk.Label(parent, text=text, font=("Segoe UI", 10),
                 bg=self.BG, fg=self.FG, anchor="w"
                 ).grid(row=row, column=0, sticky="w", padx=(10, 4), pady=5)
        tk.Entry(parent, textvariable=var, width=8, font=("Segoe UI", 10),
                 bg=self.ENTRY_BG, fg=self.FG, insertbackground=self.FG,
                 bd=1, relief="solid"
                 ).grid(row=row, column=1, columnspan=2, sticky="e", padx=(4, 10), pady=5)

    def _xy_row(self, parent, text, var_x, var_y, row):
        tk.Label(parent, text=text, font=("Segoe UI", 10),
                 bg=self.BG, fg=self.FG, anchor="w"
                 ).grid(row=row, column=0, sticky="w", padx=(10, 4), pady=4)
        tk.Entry(parent, textvariable=var_x, width=6, font=("Segoe UI", 10),
                 bg=self.ENTRY_BG, fg=self.FG, insertbackground=self.FG,
                 bd=1, relief="solid"
                 ).grid(row=row, column=1, sticky="e", padx=(4, 2), pady=4)
        tk.Entry(parent, textvariable=var_y, width=6, font=("Segoe UI", 10),
                 bg=self.ENTRY_BG, fg=self.FG, insertbackground=self.FG,
                 bd=1, relief="solid"
                 ).grid(row=row, column=2, sticky="e", padx=(2, 10), pady=4)

    # -- Hotkey (F6) ---------------------------------------------------------

    def _setup_hotkey(self):
        def on_press(key):
            if key == Key.f6:
                self.root.after(0, self._toggle)
        self._listener = KeyboardListener(on_press=on_press)
        self._listener.daemon = True
        self._listener.start()

    # -- Toggle --------------------------------------------------------------

    def _toggle(self):
        if self.macro.running:
            self.macro.stop()
        else:
            self._save_config()
            self.macro.start()
        self.update_button_state()

    def update_button_state(self):
        def _update():
            if self.macro.running:
                self.btn.config(text="СТОП  (F6)", bg=self.BTN_STOP,
                                activebackground="#c0392b")
                self.status_var.set("Работает — сканирование QTE")
            else:
                self.btn.config(text="СТАРТ  (F6)", bg=self.BTN_START,
                                activebackground="#00a884")
                self.status_var.set("Остановлен")
                self.failsafe_var.set("")
        self.root.after(0, _update)

    def update_failsafe(self, value):
        def _update():
            self.failsafe_var.set(f"Failsafe: {value}")
        self.root.after(0, _update)

    # -- Logging -------------------------------------------------------------

    def log(self, msg):
        ts = time.strftime("%H:%M:%S")
        line = f"[{ts}] {msg}\n"
        def _append():
            self.log_text.config(state="normal")
            self.log_text.insert("end", line)
            self.log_text.see("end")
            # Keep log manageable — trim old lines
            line_count = int(self.log_text.index("end-1c").split(".")[0])
            if line_count > 200:
                self.log_text.delete("1.0", f"{line_count - 150}.0")
            self.log_text.config(state="disabled")
        self.root.after(0, _append)

    # -- Config persistence --------------------------------------------------

    def _save_config(self):
        data = {
            "food_slot": self.food_slot.get(),
            "rod_slot": self.rod_slot.get(),
            "eat_interval": self.eat_interval.get(),
            "afk_interval": self.afk_interval.get(),
            "a_x": self.a_x.get(), "a_y": self.a_y.get(),
            "s_x": self.s_x.get(), "s_y": self.s_y.get(),
            "d_x": self.d_x.get(), "d_y": self.d_y.get(),
            "region_size": self.region_size.get(),
        }
        save_config(data)

    # -- Run -----------------------------------------------------------------

    def run(self):
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()

    def _on_close(self):
        self._save_config()
        self.macro.stop()
        self._listener.stop()
        self.root.destroy()


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app = App()
    app.run()
