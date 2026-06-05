"""
Screen capture module for GeoGuessr Solver.
Captures the screen (or specific window) for analysis.
Works on Windows, Linux (X11/Wayland), and macOS.
"""

from PIL import Image


class ScreenCapture:
    def __init__(self):
        self._sct = None
        self._error = None

    def _get_mss(self):
        """Lazy-init mss to avoid import-time crash if display is missing."""
        if self._sct is None and self._error is None:
            try:
                import mss
                self._sct = mss.mss()
            except Exception as e:
                self._error = str(e)
        if self._error:
            raise RuntimeError(
                f"Захват экрана недоступен: {self._error}\n"
                "Убедитесь, что приложение запущено на рабочем столе."
            )
        return self._sct

    def grab_screen(self, monitor_num=1):
        """
        Capture the primary monitor screen.
        Returns a PIL Image.
        """
        sct = self._get_mss()
        monitor = sct.monitors[monitor_num]
        screenshot = sct.grab(monitor)
        img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
        return img

    def grab_region(self, left, top, width, height):
        """
        Capture a specific region of the screen.
        Returns a PIL Image.
        """
        sct = self._get_mss()
        region = {"left": left, "top": top, "width": width, "height": height}
        screenshot = sct.grab(region)
        img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
        return img

    def grab_center(self, width=1280, height=720):
        """
        Capture the center of the screen (where GeoGuessr typically shows the street view).
        Returns a PIL Image.
        """
        sct = self._get_mss()
        monitor = sct.monitors[1]
        screen_w = monitor["width"]
        screen_h = monitor["height"]

        left = (screen_w - width) // 2
        top = (screen_h - height) // 2

        return self.grab_region(left, top, width, height)
