"""
Screen capture module for GeoGuessr Solver.
Captures the screen (or specific window) for analysis.
Works on Windows, Linux (X11/Wayland), and macOS.
Creates a new mss instance per capture to avoid threading issues on Windows.
"""

from PIL import Image


class ScreenCapture:
    def __init__(self):
        self._error = None

    def _grab(self, region=None, monitor_num=1):
        """
        Grab screen using a fresh mss instance (avoids Windows BitBlt threading issues).
        """
        try:
            import mss
            with mss.mss() as sct:
                if region:
                    screenshot = sct.grab(region)
                else:
                    monitor = sct.monitors[monitor_num]
                    screenshot = sct.grab(monitor)
                img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
                return img
        except Exception as e:
            raise RuntimeError(
                f"Захват экрана недоступен: {e}\n"
                "Убедитесь, что приложение запущено на рабочем столе."
            )

    def grab_screen(self, monitor_num=1):
        """
        Capture the primary monitor screen.
        Returns a PIL Image.
        """
        return self._grab(monitor_num=monitor_num)

    def grab_region(self, left, top, width, height):
        """
        Capture a specific region of the screen.
        Returns a PIL Image.
        """
        region = {"left": left, "top": top, "width": width, "height": height}
        return self._grab(region=region)

    def grab_center(self, width=1280, height=720):
        """
        Capture the center of the screen.
        Returns a PIL Image.
        """
        import mss
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            screen_w = monitor["width"]
            screen_h = monitor["height"]

        left = (screen_w - width) // 2
        top = (screen_h - height) // 2
        return self.grab_region(left, top, width, height)
