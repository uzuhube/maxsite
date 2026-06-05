"""
mitmproxy addon that intercepts GeoGuessr/Google Maps API requests
and extracts coordinates from the traffic.

This is the core interceptor - it runs inside mitmproxy and captures
lat/lng from Street View API responses.
"""

import re
import json
import os

# File where we write coordinates for the overlay to read
COORDS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".coords.json")


class GeoGuessrInterceptor:
    """mitmproxy addon that captures coordinates from Google Maps API traffic."""

    def __init__(self):
        self.last_coords = None
        self.target_urls = [
            "maps.googleapis.com",
            "cbk0.google.com",
            "cbk1.google.com",
            "streetviewpixels",
            "geo0.ggpht.com",
            "geo1.ggpht.com",
            "geo2.ggpht.com",
            "geo3.ggpht.com",
            "GeoPhotoService",
            "SingleImageSearch",
        ]

    def response(self, flow):
        """Called for every HTTP response passing through the proxy."""
        url = flow.request.pretty_url

        # Check if this is a Maps/StreetView related request
        if not any(target in url for target in self.target_urls):
            return

        # Try to extract coordinates from the response
        try:
            content = flow.response.get_text()
            if content:
                coords = self._extract_coords(content, url)
                if coords:
                    self._save_coords(coords, url)
        except Exception:
            pass

        # Also check URL parameters for coordinates
        coords_from_url = self._extract_coords_from_url(url)
        if coords_from_url:
            self._save_coords(coords_from_url, url)

    def _extract_coords(self, text, url):
        """Extract coordinates from response body."""
        if not text:
            return None

        # Pattern 1: [[null,null,lat,lng]]
        match = re.search(r'\[\[null,null,(-?\d+\.\d+),(-?\d+\.\d+)\]', text)
        if match:
            return self._validate(float(match.group(1)), float(match.group(2)))

        # Pattern 2: JSON with lat/lng
        match = re.search(r'"lat"\s*:\s*(-?\d+\.\d+).*?"lng"\s*:\s*(-?\d+\.\d+)', text)
        if match:
            return self._validate(float(match.group(1)), float(match.group(2)))

        # Pattern 3: Array format [lat, lng]
        matches = re.findall(r'\[(-?\d+\.\d{4,}),(-?\d+\.\d{4,})\]', text)
        for m in matches:
            coords = self._validate(float(m[0]), float(m[1]))
            if coords:
                return coords

        # Pattern 4: Comma-separated in response
        numbers = re.findall(r'(-?\d+\.\d{5,})', text)
        if len(numbers) >= 2:
            for i in range(len(numbers) - 1):
                lat = float(numbers[i])
                lng = float(numbers[i + 1])
                coords = self._validate(lat, lng)
                if coords:
                    return coords

        return None

    def _extract_coords_from_url(self, url):
        """Extract coordinates from URL parameters."""
        # Pattern: @lat,lng or !3dlat!4dlng or ll=lat,lng
        patterns = [
            r'@(-?\d+\.\d+),(-?\d+\.\d+)',
            r'!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)',
            r'll=(-?\d+\.\d+),(-?\d+\.\d+)',
            r'center=(-?\d+\.\d+),(-?\d+\.\d+)',
            r'pano.*?(-?\d+\.\d{5,}).*?(-?\d+\.\d{5,})',
        ]

        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return self._validate(float(match.group(1)), float(match.group(2)))

        return None

    def _validate(self, lat, lng):
        """Validate coordinates are within valid range."""
        if -90 <= lat <= 90 and -180 <= lng <= 180 and lat != 0 and lng != 0:
            # Check they're different from last coords (avoid duplicates)
            if self.last_coords:
                if (abs(lat - self.last_coords[0]) < 0.0001 and
                        abs(lng - self.last_coords[1]) < 0.0001):
                    return None
            return (lat, lng)
        return None

    def _save_coords(self, coords, source_url):
        """Save coordinates to file for overlay to read."""
        self.last_coords = coords
        data = {
            "lat": coords[0],
            "lng": coords[1],
            "source": source_url[:100],
        }

        try:
            with open(COORDS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f)
        except Exception:
            pass


# mitmproxy entry point
addons = [GeoGuessrInterceptor()]
