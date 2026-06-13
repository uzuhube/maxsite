"""
AFK Fishing Macro - Standalone Application
Автономное приложение для AFK рыбалки с GUI.
"""

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

# Slot key mapping: display label -> pynput KeyCode
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


# ---------------------------------------------------------------------------
# Helper: press and release a key
# ---------------------------------------------------------------------------
def tap_key(key, hold: float = 0.05):
    """Press a key, hold briefly, release."""
    keyboard.press(key)
    time.sleep(hold)
    keyboard.release(key)


def right_click():
    """Perform a right-click."""
    mouse.click(Button.right)


def left_click():
    """Perform a left-click."""
    mouse.click(Button.left)


# ---------------------------------------------------------------------------
# Macro engine
# ---------------------------------------------------------------------------
class FishingMacro:
    """Core macro logic running in a background thread."""

    def __init__(self, app: "App"):
        self.app = app
        self._running = False
        self._thread = None
        self._stop_event = threading.Event()

    # -- public API ----------------------------------------------------------

    @property
    def running(self) -> bool:
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
        self.app.log("Макрос остановлен")

    # -- internal ------------------------------------------------------------

    def _wait(self, seconds: float) -> bool:
        """Sleep in small increments; return True if stop was requested."""
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if self._stop_event.is_set():
                return True
            time.sleep(0.25)
        return False

    def _eat(self):
        """Switch to food slot, eat, switch back to rod."""
        food_key = SLOT_KEYS[self.app.food_slot.get()]
        rod_key = SLOT_KEYS[self.app.rod_slot.get()]

        self.app.log("Переключение на еду...")
        tap_key(food_key)
        if self._wait(0.4):
            return

        # Right-click to eat
        right_click()
        self.app.log("Едим...")
        if self._wait(3.0):
            return

        # Switch back to fishing rod
        self.app.log("Возврат к удочке")
        tap_key(rod_key)
        if self._wait(0.5):
            return

        # Re-cast
        right_click()
        if self._wait(0.3):
            return

    def _anti_afk(self):
        """Tiny side-to-side movement."""
        self.app.log("Анти-АФК движение")
        tap_key(KeyCode.from_char("d"), hold=0.15)
        if self._wait(0.3):
            return
        tap_key(KeyCode.from_char("a"), hold=0.15)

    def _recast(self):
        """Re-cast the fishing rod."""
        self.app.log("Ре-каст удочки")
        right_click()

    def _loop(self):
        eat_interval = self.app.eat_interval.get() * 60  # minutes -> seconds
        afk_interval = self.app.afk_interval.get()       # seconds
        recast_interval = self.app.recast_interval.get()  # seconds

        # Initial delay so user can switch to game window
        self.app.log("Старт через 3 секунды — переключитесь в игру!")
        if self._wait(3.0):
            return

        # Equip rod at start
        rod_key = SLOT_KEYS[self.app.rod_slot.get()]
        tap_key(rod_key)
        if self._wait(0.3):
            return
        right_click()  # initial cast

        last_eat = time.monotonic()
        last_afk = time.monotonic()
        last_recast = time.monotonic()

        while not self._stop_event.is_set():
            now = time.monotonic()

            # Eating check
            if now - last_eat >= eat_interval:
                self._eat()
                last_eat = time.monotonic()
                last_recast = time.monotonic()  # eating re-casts automatically
                if self._stop_event.is_set():
                    break
                continue

            # Anti-AFK check
            if now - last_afk >= afk_interval:
                self._anti_afk()
                last_afk = time.monotonic()
                if self._stop_event.is_set():
                    break

            # Re-cast check
            if now - last_recast >= recast_interval:
                self._recast()
                last_recast = time.monotonic()
                if self._stop_event.is_set():
                    break

            # Small sleep to avoid busy-wait
            if self._wait(0.5):
                break

        self._running = False
        self.app.update_button_state()


# ---------------------------------------------------------------------------
# GUI Application
# ---------------------------------------------------------------------------
class App:
    """Tkinter-based GUI."""

    BG = "#1a1a2e"
    FG = "#eaeaea"
    ACCENT = "#e94560"
    ACCENT2 = "#0f3460"
    ENTRY_BG = "#16213e"
    BTN_START = "#00b894"
    BTN_STOP = "#d63031"

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("AFK Fishing Macro")
        self.root.geometry("420x620")
        self.root.resizable(False, False)
        self.root.configure(bg=self.BG)

        # Variables
        self.food_slot = tk.StringVar(value="2")
        self.rod_slot = tk.StringVar(value="1")
        self.eat_interval = tk.DoubleVar(value=8.0)   # minutes
        self.afk_interval = tk.DoubleVar(value=30.0)   # seconds
        self.recast_interval = tk.DoubleVar(value=25.0) # seconds

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
        title = tk.Label(self.root, text="🎣 AFK Fishing Macro",
                         font=("Segoe UI", 20, "bold"),
                         bg=self.BG, fg=self.ACCENT)
        title.pack(pady=(18, 4))

        subtitle = tk.Label(self.root, text="Автономное приложение для AFK рыбалки",
                            font=("Segoe UI", 10), bg=self.BG, fg="#888")
        subtitle.pack(pady=(0, 12))

        # -- Settings frame --
        sf = tk.LabelFrame(self.root, text=" Настройки ", font=("Segoe UI", 11, "bold"),
                           bg=self.BG, fg=self.FG, bd=1, relief="groove",
                           highlightbackground="#333", highlightthickness=1)
        sf.pack(padx=16, pady=6, fill="x")

        slot_values = list(SLOT_KEYS.keys())

        self._add_combo_row(sf, "Слот еды (1-0):", self.food_slot, slot_values, 0)
        self._add_combo_row(sf, "Слот удочки (1-0):", self.rod_slot, slot_values, 1)
        self._add_entry_row(sf, "Интервал еды (мин):", self.eat_interval, 2)
        self._add_entry_row(sf, "Анти-АФК (сек):", self.afk_interval, 3)
        self._add_entry_row(sf, "Ре-каст (сек):", self.recast_interval, 4)

        # -- Start / Stop button --
        self.btn = tk.Button(
            self.root, text="▶  СТАРТ  (F6)", font=("Segoe UI", 14, "bold"),
            bg=self.BTN_START, fg="white", activebackground="#00a884",
            relief="flat", bd=0, cursor="hand2",
            command=self._toggle,
        )
        self.btn.pack(padx=16, pady=14, fill="x", ipady=8)

        # -- Status --
        self.status_var = tk.StringVar(value="Остановлен")
        status_lbl = tk.Label(self.root, textvariable=self.status_var,
                              font=("Segoe UI", 11), bg=self.BG, fg="#aaa")
        status_lbl.pack()

        # -- Log --
        log_frame = tk.LabelFrame(self.root, text=" Лог ", font=("Segoe UI", 10, "bold"),
                                  bg=self.BG, fg=self.FG, bd=1, relief="groove",
                                  highlightbackground="#333", highlightthickness=1)
        log_frame.pack(padx=16, pady=10, fill="both", expand=True)

        self.log_text = tk.Text(log_frame, height=10, bg=self.ENTRY_BG, fg=self.FG,
                                font=("Consolas", 9), wrap="word", bd=0,
                                insertbackground=self.FG, state="disabled")
        self.log_text.pack(padx=4, pady=4, fill="both", expand=True)

        # -- Footer --
        footer = tk.Label(self.root, text="F6 — Старт/Стоп    |    Закройте окно для выхода",
                          font=("Segoe UI", 9), bg=self.BG, fg="#555")
        footer.pack(pady=(0, 8))

    def _add_combo_row(self, parent, label_text, var, values, row):
        lbl = tk.Label(parent, text=label_text, font=("Segoe UI", 10),
                       bg=self.BG, fg=self.FG, anchor="w")
        lbl.grid(row=row, column=0, sticky="w", padx=(12, 6), pady=6)

        combo = ttk.Combobox(parent, textvariable=var, values=values,
                             width=6, state="readonly", font=("Segoe UI", 10))
        combo.grid(row=row, column=1, sticky="e", padx=(6, 12), pady=6)

    def _add_entry_row(self, parent, label_text, var, row):
        lbl = tk.Label(parent, text=label_text, font=("Segoe UI", 10),
                       bg=self.BG, fg=self.FG, anchor="w")
        lbl.grid(row=row, column=0, sticky="w", padx=(12, 6), pady=6)

        entry = tk.Entry(parent, textvariable=var, width=8,
                         font=("Segoe UI", 10), bg=self.ENTRY_BG, fg=self.FG,
                         insertbackground=self.FG, bd=1, relief="solid")
        entry.grid(row=row, column=1, sticky="e", padx=(6, 12), pady=6)

    # -- Hotkey (F6) ---------------------------------------------------------

    def _setup_hotkey(self):
        def on_press(key):
            if key == Key.f6:
                self.root.after(0, self._toggle)

        self._listener = KeyboardListener(on_press=on_press)
        self._listener.daemon = True
        self._listener.start()

    # -- Toggle start/stop ---------------------------------------------------

    def _toggle(self):
        if self.macro.running:
            self.macro.stop()
        else:
            self.macro.start()
        self.update_button_state()

    def update_button_state(self):
        def _update():
            if self.macro.running:
                self.btn.config(text="⏹  СТОП  (F6)", bg=self.BTN_STOP,
                                activebackground="#c0392b")
                self.status_var.set("🟢 Работает")
            else:
                self.btn.config(text="▶  СТАРТ  (F6)", bg=self.BTN_START,
                                activebackground="#00a884")
                self.status_var.set("Остановлен")
        self.root.after(0, _update)

    # -- Logging -------------------------------------------------------------

    def log(self, msg: str):
        timestamp = time.strftime("%H:%M:%S")
        line = f"[{timestamp}] {msg}\n"

        def _append():
            self.log_text.config(state="normal")
            self.log_text.insert("end", line)
            self.log_text.see("end")
            self.log_text.config(state="disabled")

        self.root.after(0, _append)

    # -- Run -----------------------------------------------------------------

    def run(self):
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()

    def _on_close(self):
        self.macro.stop()
        self._listener.stop()
        self.root.destroy()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app = App()
    app.run()
