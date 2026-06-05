"""
Screen capture module for GeoGuessr Solver.
Captures the screen (or specific window) for analysis.
"""

import mss
from PIL import Image


class ScreenCapture:
    def __init__(self):
        self.sct = mss.mss()

    def grab_screen(self, monitor_num=1):
        """
        Capture the primary monitor screen.
        Returns a PIL Image.
        """
        monitor = self.sct.monitors[monitor_num]
        screenshot = self.sct.grab(monitor)
        img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
        return img

    def grab_region(self, left, top, width, height):
        """
        Capture a specific region of the screen.
        Returns a PIL Image.
        """
        region = {"left": left, "top": top, "width": width, "height": height}
        screenshot = self.sct.grab(region)
        img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
        return img

    def grab_center(self, width=1280, height=720):
        """
        Capture the center of the screen (where GeoGuessr typically shows the street view).
        Returns a PIL Image.
        """
        monitor = self.sct.monitors[1]
        screen_w = monitor["width"]
        screen_h = monitor["height"]

        left = (screen_w - width) // 2
        top = (screen_h - height) // 2

        return self.grab_region(left, top, width, height)
