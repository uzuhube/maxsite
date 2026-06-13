"""
AFK Fishing Macro for Deepwoken — Standalone Application
Автономное приложение для AFK рыбалки в Deepwoken с GUI.

Механика:
1. Заброс удочки (ЛКМ)
2. QTE мини-игра — буквы A, S, D подсвечиваются на экране
3. Зажимаем нужную клавишу + ЛКМ
4. Перезаброс после завершения
5. Периодически едим
"""

import json
import os
import struct
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk

from pynput.keyboard import Key, Listener as KeyboardListener

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

PIXEL_TOLERANCE = 90

# ---------------------------------------------------------------------------
# DirectInput scan codes (hardware-level — works with Roblox)
# ---------------------------------------------------------------------------
SC_A = 0x1E
SC_S = 0x1F
SC_D = 0x20
SC_1 = 0x02
SC_2 = 0x03
SC_3 = 0x04
SC_4 = 0x05
SC_5 = 0x06
SC_6 = 0x07
SC_7 = 0x08
SC_8 = 0x09
SC_9 = 0x0A
SC_0 = 0x0B

SLOT_SCANCODES = {
    "1": SC_1, "2": SC_2, "3": SC_3, "4": SC_4, "5": SC_5,
    "6": SC_6, "7": SC_7, "8": SC_8, "9": SC_9, "0": SC_0,
}


# ---------------------------------------------------------------------------
# Input backend — SendInput on Windows, pynput fallback elsewhere
# ---------------------------------------------------------------------------
def _is_windows():
    return sys.platform == "win32"


if _is_windows():
    import ctypes
    import ctypes.wintypes

    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32

    KEYEVENTF_SCANCODE = 0x0008
    KEYEVENTF_KEYUP = 0x0002
    INPUT_KEYBOARD = 1
    INPUT_MOUSE = 0
    MOUSEEVENTF_LEFTDOWN = 0x0002
    MOUSEEVENTF_LEFTUP = 0x0004

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", ctypes.c_ushort),
            ("wScan", ctypes.c_ushort),
            ("dwFlags", ctypes.c_ulong),
            ("time", ctypes.c_ulong),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", ctypes.c_long),
            ("dy", ctypes.c_long),
            ("mouseData", ctypes.c_ulong),
            ("dwFlags", ctypes.c_ulong),
            ("time", ctypes.c_ulong),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]

    class INPUT_UNION(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", ctypes.c_ulong), ("u", INPUT_UNION)]

    def _send_input(inp):
        user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))

    def key_down(scan_code):
        inp = INPUT(type=INPUT_KEYBOARD)
        inp.u.ki = KEYBDINPUT(wVk=0, wScan=scan_code,
                              dwFlags=KEYEVENTF_SCANCODE, time=0, dwExtraInfo=None)
        _send_input(inp)

    def key_up(scan_code):
        inp = INPUT(type=INPUT_KEYBOARD)
        inp.u.ki = KEYBDINPUT(wVk=0, wScan=scan_code,
                              dwFlags=KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP, time=0,
                              dwExtraInfo=None)
        _send_input(inp)

    def tap_key(scan_code, hold=0.05):
        key_down(scan_code)
        time.sleep(hold)
        key_up(scan_code)

    def mouse_left_down():
        inp = INPUT(type=INPUT_MOUSE)
        inp.u.mi = MOUSEINPUT(dx=0, dy=0, mouseData=0,
                              dwFlags=MOUSEEVENTF_LEFTDOWN, time=0, dwExtraInfo=None)
        _send_input(inp)

    def mouse_left_up():
        inp = INPUT(type=INPUT_MOUSE)
        inp.u.mi = MOUSEINPUT(dx=0, dy=0, mouseData=0,
                              dwFlags=MOUSEEVENTF_LEFTUP, time=0, dwExtraInfo=None)
        _send_input(inp)

    def mouse_left_click():
        mouse_left_down()
        time.sleep(0.02)
        mouse_left_up()

    # -- Screen capture (GDI) ------------------------------------------------

    def scan_region_for_white(x, y, w, h):
        hdc_screen = user32.GetDC(0)
        hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
        hbmp = gdi32.CreateCompatibleBitmap(hdc_screen, w, h)
        gdi32.SelectObject(hdc_mem, hbmp)
        gdi32.BitBlt(hdc_mem, 0, 0, w, h, hdc_screen, x, y, 0x00CC0020)

        bmi = struct.pack("LllHHLLllLL",
                          40,   # biSize
                          w,    # biWidth
                          -h,   # biHeight (top-down)
                          1,    # biPlanes
                          32,   # biBitCount
                          0, 0, 0, 0, 0, 0)
        buf = ctypes.create_string_buffer(w * h * 4)
        gdi32.GetDIBits(hdc_mem, hbmp, 0, h, buf, bmi, 0)

        gdi32.DeleteObject(hbmp)
        gdi32.DeleteDC(hdc_mem)
        user32.ReleaseDC(0, hdc_screen)

        tol = PIXEL_TOLERANCE
        raw = buf.raw
        for i in range(0, len(raw), 4):
            b, g, r = raw[i], raw[i + 1], raw[i + 2]
            if abs(r - 255) <= tol and abs(g - 255) <= tol and abs(b - 255) <= tol:
                return True
        return False

    def get_screen_size():
        return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)

else:
    # -- Fallback for non-Windows (pynput + mss) --
    from pynput.keyboard import Controller as _KC, KeyCode
    from pynput.mouse import Button, Controller as _MC

    _kb = _KC()
    _ms = _MC()

    _SCAN_TO_CHAR = {
        SC_A: "a", SC_S: "s", SC_D: "d",
        SC_1: "1", SC_2: "2", SC_3: "3", SC_4: "4", SC_5: "5",
        SC_6: "6", SC_7: "7", SC_8: "8", SC_9: "9", SC_0: "0",
    }

    def key_down(scan_code):
        ch = _SCAN_TO_CHAR.get(scan_code)
        if ch:
            _kb.press(KeyCode.from_char(ch))

    def key_up(scan_code):
        ch = _SCAN_TO_CHAR.get(scan_code)
        if ch:
            _kb.release(KeyCode.from_char(ch))

    def tap_key(scan_code, hold=0.05):
        key_down(scan_code)
        time.sleep(hold)
        key_up(scan_code)

    def mouse_left_down():
        _ms.press(Button.left)

    def mouse_left_up():
        _ms.release(Button.left)

    def mouse_left_click():
        _ms.click(Button.left)

    try:
        import mss as _mss_mod
        _sct = _mss_mod.mss()
    except ImportError:
        _sct = None

    def scan_region_for_white(x, y, w, h):
        if _sct is None:
            return False
        img = _sct.grab({"left": x, "top": y, "width": w, "height": h})
        tol = PIXEL_TOLERANCE
        px = img.raw
        for i in range(0, len(px), 4):
            b, g, r = px[i], px[i + 1], px[i + 2]
            if abs(r - 255) <= tol and abs(g - 255) <= tol and abs(b - 255) <= tol:
                return True
        return False

    def get_screen_size():
        try:
            return _sct.monitors[0]["width"], _sct.monitors[0]["height"]
        except Exception:
            return 1920, 1080


# ---------------------------------------------------------------------------
# Default QTE positions as screen-% (from AHK 1920x1080 defaults)
# ---------------------------------------------------------------------------
def default_qte_coords(screen_w, screen_h):
    """Calculate default QTE scan coords scaled to screen resolution."""
    return {
        "a_x": int(screen_w * 0.458),   # 880/1920
        "a_y": int(screen_h * 0.537),   # 580/1080
        "s_x": int(screen_w * 0.495),   # 950/1920
        "s_y": int(screen_h * 0.593),   # 640/1080
        "d_x": int(screen_w * 0.526),   # 1010/1920
        "d_y": int(screen_h * 0.532),   # 575/1080
        "region_size": max(20, int(screen_w * 0.013)),  # ~25px at 1920
    }


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
# Overlay — transparent draggable windows showing QTE scan regions
# ---------------------------------------------------------------------------
class QTEOverlay:
    """Three small semi-transparent windows (A, S, D) the user drags over QTE areas."""

    COLORS = {"A": "#ff4444", "S": "#44ff44", "D": "#4488ff"}

    def __init__(self, root, label, x, y, size, on_move):
        self.label = label
        self.on_move = on_move
        self.size = size

        self.win = tk.Toplevel(root)
        self.win.title(label)
        self.win.geometry(f"{size}x{size}+{x}+{y}")
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.attributes("-alpha", 0.45)
        self.win.configure(bg=self.COLORS[label])

        lbl = tk.Label(self.win, text=label, font=("Segoe UI", 12, "bold"),
                       fg="white", bg=self.COLORS[label])
        lbl.place(relx=0.5, rely=0.5, anchor="center")

        # Drag support
        self.win.bind("<Button-1>", self._start_drag)
        self.win.bind("<B1-Motion>", self._on_drag)
        lbl.bind("<Button-1>", self._start_drag)
        lbl.bind("<B1-Motion>", self._on_drag)

        self._drag_x = 0
        self._drag_y = 0

    def _start_drag(self, event):
        self._drag_x = event.x
        self._drag_y = event.y

    def _on_drag(self, event):
        x = self.win.winfo_x() + event.x - self._drag_x
        y = self.win.winfo_y() + event.y - self._drag_y
        self.win.geometry(f"+{x}+{y}")
        self.on_move(self.label, x, y)

    def get_pos(self):
        return self.win.winfo_x(), self.win.winfo_y()

    def update_size(self, size):
        self.size = size
        x, y = self.get_pos()
        self.win.geometry(f"{size}x{size}+{x}+{y}")

    def show(self):
        self.win.deiconify()

    def hide(self):
        self.win.withdraw()

    def destroy(self):
        self.win.destroy()


# ---------------------------------------------------------------------------
# Fishing Macro Engine
# ---------------------------------------------------------------------------
class FishingMacro:
    FAILSAFE_MAX = 25
    FAILSAFE_QTE = 3
    SCAN_INTERVAL = 0.08

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
        self._release_all()
        self.app.log("Макрос остановлен")

    def _release_all(self):
        for sc in (SC_A, SC_S, SC_D):
            try:
                key_up(sc)
            except Exception:
                pass
        try:
            mouse_left_up()
        except Exception:
            pass

    def _stopped(self):
        return self._stop_event.is_set()

    def _sleep(self, seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if self._stopped():
                return True
            time.sleep(min(0.05, end - time.monotonic()))
        return False

    def _eat(self):
        food_sc = SLOT_SCANCODES[self.app.food_slot.get()]
        rod_sc = SLOT_SCANCODES[self.app.rod_slot.get()]

        self.app.log("Переключение на еду...")
        self._release_all()
        if self._sleep(0.2):
            return

        tap_key(food_sc)
        if self._sleep(0.5):
            return

        mouse_left_click()
        self.app.log("Едим...")
        if self._sleep(3.0):
            return

        mouse_left_click()
        if self._sleep(3.0):
            return

        self.app.log("Возврат к удочке")
        tap_key(rod_sc)
        if self._sleep(1.0):
            return

        mouse_left_click()
        self.app.log("Перезаброс после еды")
        if self._sleep(0.1):
            return

    def _anti_afk(self):
        self.app.log("Анти-АФК движение")
        tap_key(SC_D, hold=0.12)
        if self._sleep(0.2):
            return
        tap_key(SC_A, hold=0.12)

    def _recast(self):
        self.app.log("Перезаброс удочки...")
        self._release_all()
        if self._sleep(0.25):
            return

        rod_sc = SLOT_SCANCODES[self.app.rod_slot.get()]
        tap_key(rod_sc)
        if self._sleep(1.0):
            return

        mouse_left_down()
        if self._sleep(0.02):
            return
        mouse_left_up()
        self.app.log("Удочка заброшена")

    def _get_regions(self):
        size = self.app.region_size.get()
        return {
            "a": (self.app.a_x.get(), self.app.a_y.get(), size, size),
            "s": (self.app.s_x.get(), self.app.s_y.get(), size, size),
            "d": (self.app.d_x.get(), self.app.d_y.get(), size, size),
        }

    def _scan_qte(self, regions):
        detected = False

        ax, ay, aw, ah = regions["a"]
        a_hit = scan_region_for_white(ax, ay, aw, ah)

        sx, sy, sw, sh = regions["s"]
        s_hit = scan_region_for_white(sx, sy, sw, sh)

        dx, dy, dw, dh = regions["d"]
        d_hit = scan_region_for_white(dx, dy, dw, dh)

        if a_hit:
            key_up(SC_S)
            key_up(SC_D)
            key_down(SC_A)
            mouse_left_down()
            detected = True
        else:
            key_up(SC_A)

        if s_hit:
            key_up(SC_A)
            key_up(SC_D)
            key_down(SC_S)
            mouse_left_click()
            detected = True
        elif not a_hit:
            key_up(SC_S)

        if d_hit:
            key_up(SC_A)
            key_up(SC_S)
            key_down(SC_D)
            mouse_left_down()
            detected = True
        elif not a_hit and not s_hit:
            key_up(SC_D)

        if not detected:
            mouse_left_up()

        return detected

    def _loop(self):
        eat_interval = self.app.eat_interval.get() * 60
        afk_interval = self.app.afk_interval.get()

        self.app.log("Старт через 3 сек — переключитесь в игру!")
        if self._sleep(3.0):
            self._running = False
            self.app.update_button_state()
            return

        rod_sc = SLOT_SCANCODES[self.app.rod_slot.get()]
        tap_key(rod_sc)
        if self._sleep(0.3):
            self._running = False
            self.app.update_button_state()
            return
        mouse_left_click()
        self.app.log("Удочка заброшена — сканирование QTE")

        failsafe = self.FAILSAFE_MAX
        last_eat = time.monotonic()
        last_afk = time.monotonic()
        scan_count = 0

        while not self._stopped():
            now = time.monotonic()

            if now - last_eat >= eat_interval:
                self._eat()
                last_eat = time.monotonic()
                failsafe = self.FAILSAFE_MAX
                if self._stopped():
                    break
                continue

            if now - last_afk >= afk_interval:
                self._anti_afk()
                last_afk = time.monotonic()
                if self._stopped():
                    break

            regions = self._get_regions()
            qte_found = self._scan_qte(regions)

            if qte_found:
                failsafe = self.FAILSAFE_QTE
                scan_count += 1
                if scan_count % 20 == 0:
                    self.app.log(f"QTE (скан #{scan_count})")
            else:
                scan_count += 1
                if scan_count % 10 == 0:
                    failsafe -= 1
                    self.app.update_failsafe(failsafe)

            if failsafe <= 0:
                self.app.log("Нет QTE — перезаброс")
                self._recast()
                failsafe = self.FAILSAFE_MAX
                if self._stopped():
                    break

            time.sleep(self.SCAN_INTERVAL)

        self._release_all()
        self._running = False
        self.app.update_button_state()


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
        self.root.geometry("460x700")
        self.root.resizable(False, False)
        self.root.configure(bg=self.BG)

        cfg = load_config()
        sw, sh = get_screen_size()
        defaults = default_qte_coords(sw, sh)

        self.food_slot = tk.StringVar(value=cfg.get("food_slot", "2"))
        self.rod_slot = tk.StringVar(value=cfg.get("rod_slot", "1"))
        self.eat_interval = tk.DoubleVar(value=cfg.get("eat_interval", 8.0))
        self.afk_interval = tk.DoubleVar(value=cfg.get("afk_interval", 30.0))

        self.a_x = tk.IntVar(value=cfg.get("a_x", defaults["a_x"]))
        self.a_y = tk.IntVar(value=cfg.get("a_y", defaults["a_y"]))
        self.s_x = tk.IntVar(value=cfg.get("s_x", defaults["s_x"]))
        self.s_y = tk.IntVar(value=cfg.get("s_y", defaults["s_y"]))
        self.d_x = tk.IntVar(value=cfg.get("d_x", defaults["d_x"]))
        self.d_y = tk.IntVar(value=cfg.get("d_y", defaults["d_y"]))
        self.region_size = tk.IntVar(value=cfg.get("region_size", defaults["region_size"]))

        self.macro = FishingMacro(self)
        self._overlays = []
        self._overlays_visible = False

        self._build_ui()
        self._setup_hotkey()

    def _build_ui(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TCombobox", fieldbackground=self.ENTRY_BG,
                        background=self.ENTRY_BG, foreground=self.FG)

        tk.Label(self.root, text="AFK Fishing Macro",
                 font=("Segoe UI", 20, "bold"),
                 bg=self.BG, fg=self.ACCENT).pack(pady=(14, 2))
        tk.Label(self.root, text="Deepwoken | QTE Auto-Fish | SendInput",
                 font=("Segoe UI", 10), bg=self.BG, fg="#888").pack(pady=(0, 8))

        # -- Slots & timers --
        sf = tk.LabelFrame(self.root, text=" Слоты и таймеры ",
                           font=("Segoe UI", 11, "bold"),
                           bg=self.BG, fg=self.FG, bd=1, relief="groove")
        sf.pack(padx=14, pady=4, fill="x")

        slot_vals = list(SLOT_SCANCODES.keys())
        self._combo_row(sf, "Слот еды (1-0):", self.food_slot, slot_vals, 0)
        self._combo_row(sf, "Слот удочки (1-0):", self.rod_slot, slot_vals, 1)
        self._entry_row(sf, "Еда каждые (мин):", self.eat_interval, 2)
        self._entry_row(sf, "Анти-АФК (сек):", self.afk_interval, 3)

        # -- QTE coordinates --
        qf = tk.LabelFrame(self.root, text=" Области сканирования QTE ",
                           font=("Segoe UI", 10, "bold"),
                           bg=self.BG, fg=self.FG, bd=1, relief="groove")
        qf.pack(padx=14, pady=4, fill="x")

        self._xy_row(qf, "A — X, Y:", self.a_x, self.a_y, 0, "#ff4444")
        self._xy_row(qf, "S — X, Y:", self.s_x, self.s_y, 1, "#44ff44")
        self._xy_row(qf, "D — X, Y:", self.d_x, self.d_y, 2, "#4488ff")
        self._entry_row(qf, "Размер (px):", self.region_size, 3)

        # Overlay toggle button
        self.overlay_btn = tk.Button(
            qf, text="Показать оверлей на экране",
            font=("Segoe UI", 9, "bold"), bg="#2d3a6a", fg="white",
            activebackground="#3d4a7a", relief="flat", bd=0, cursor="hand2",
            command=self._toggle_overlay,
        )
        self.overlay_btn.grid(row=4, column=0, columnspan=3,
                              padx=10, pady=(4, 8), sticky="ew")

        tk.Label(qf, text="Перетащите цветные окошки на QTE-зоны в игре",
                 font=("Segoe UI", 8), bg=self.BG, fg="#666",
                 wraplength=400).grid(row=5, column=0, columnspan=3, pady=(0, 6), padx=8)

        # -- Start / Stop --
        self.btn = tk.Button(
            self.root, text="СТАРТ  (F6)", font=("Segoe UI", 14, "bold"),
            bg=self.BTN_START, fg="white", activebackground="#00a884",
            relief="flat", bd=0, cursor="hand2", command=self._toggle,
        )
        self.btn.pack(padx=14, pady=10, fill="x", ipady=8)

        # -- Status --
        status_frame = tk.Frame(self.root, bg=self.BG)
        status_frame.pack(fill="x", padx=14)

        self.status_var = tk.StringVar(value="Остановлен")
        tk.Label(status_frame, textvariable=self.status_var,
                 font=("Segoe UI", 11), bg=self.BG, fg="#aaa").pack(side="left")

        self.failsafe_var = tk.StringVar(value="")
        tk.Label(status_frame, textvariable=self.failsafe_var,
                 font=("Segoe UI", 10), bg=self.BG, fg="#666").pack(side="right")

        # -- Log --
        lf = tk.LabelFrame(self.root, text=" Лог ", font=("Segoe UI", 10, "bold"),
                           bg=self.BG, fg=self.FG, bd=1, relief="groove")
        lf.pack(padx=14, pady=8, fill="both", expand=True)

        self.log_text = tk.Text(lf, height=8, bg=self.ENTRY_BG, fg=self.FG,
                                font=("Consolas", 9), wrap="word", bd=0,
                                insertbackground=self.FG, state="disabled")
        self.log_text.pack(padx=4, pady=4, fill="both", expand=True)

        # -- Footer --
        tk.Label(self.root,
                 text="F6 — Старт/Стоп  |  SendInput для надёжных нажатий",
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

    def _xy_row(self, parent, text, var_x, var_y, row, color="#eaeaea"):
        tk.Label(parent, text=text, font=("Segoe UI", 10, "bold"),
                 bg=self.BG, fg=color, anchor="w"
                 ).grid(row=row, column=0, sticky="w", padx=(10, 4), pady=4)
        tk.Entry(parent, textvariable=var_x, width=6, font=("Segoe UI", 10),
                 bg=self.ENTRY_BG, fg=self.FG, insertbackground=self.FG,
                 bd=1, relief="solid"
                 ).grid(row=row, column=1, sticky="e", padx=(4, 2), pady=4)
        tk.Entry(parent, textvariable=var_y, width=6, font=("Segoe UI", 10),
                 bg=self.ENTRY_BG, fg=self.FG, insertbackground=self.FG,
                 bd=1, relief="solid"
                 ).grid(row=row, column=2, sticky="e", padx=(2, 10), pady=4)

    # -- Overlay -------------------------------------------------------------

    def _toggle_overlay(self):
        if self._overlays_visible:
            self._hide_overlays()
        else:
            self._show_overlays()

    def _show_overlays(self):
        if self._overlays:
            for ov in self._overlays:
                ov.show()
        else:
            size = self.region_size.get()
            self._overlays = [
                QTEOverlay(self.root, "A", self.a_x.get(), self.a_y.get(),
                           size, self._overlay_moved),
                QTEOverlay(self.root, "S", self.s_x.get(), self.s_y.get(),
                           size, self._overlay_moved),
                QTEOverlay(self.root, "D", self.d_x.get(), self.d_y.get(),
                           size, self._overlay_moved),
            ]
        self._overlays_visible = True
        self.overlay_btn.config(text="Скрыть оверлей")

    def _hide_overlays(self):
        for ov in self._overlays:
            ov.hide()
        self._overlays_visible = False
        self.overlay_btn.config(text="Показать оверлей на экране")

    def _overlay_moved(self, label, x, y):
        if label == "A":
            self.a_x.set(x)
            self.a_y.set(y)
        elif label == "S":
            self.s_x.set(x)
            self.s_y.set(y)
        elif label == "D":
            self.d_x.set(x)
            self.d_y.set(y)

    # -- Hotkey --------------------------------------------------------------

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
            if self._overlays_visible:
                self._hide_overlays()
            self.macro.start()
        self.update_button_state()

    def update_button_state(self):
        def _update():
            if self.macro.running:
                self.btn.config(text="СТОП  (F6)", bg=self.BTN_STOP,
                                activebackground="#c0392b")
                self.status_var.set("Работает — QTE сканирование")
            else:
                self.btn.config(text="СТАРТ  (F6)", bg=self.BTN_START,
                                activebackground="#00a884")
                self.status_var.set("Остановлен")
                self.failsafe_var.set("")
        self.root.after(0, _update)

    def update_failsafe(self, value):
        self.root.after(0, lambda: self.failsafe_var.set(f"Failsafe: {value}"))

    def log(self, msg):
        ts = time.strftime("%H:%M:%S")
        line = f"[{ts}] {msg}\n"
        def _append():
            self.log_text.config(state="normal")
            self.log_text.insert("end", line)
            self.log_text.see("end")
            lc = int(self.log_text.index("end-1c").split(".")[0])
            if lc > 200:
                self.log_text.delete("1.0", f"{lc - 150}.0")
            self.log_text.config(state="disabled")
        self.root.after(0, _append)

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

    def run(self):
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()

    def _on_close(self):
        self._save_config()
        self.macro.stop()
        for ov in self._overlays:
            ov.destroy()
        self._listener.stop()
        self.root.destroy()


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app = App()
    app.run()
