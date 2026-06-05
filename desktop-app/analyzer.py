"""
Location Analyzer for GeoGuessr Solver.
Analyzes screenshots using OCR (optional) and visual heuristics.
Works WITHOUT Tesseract - OCR is optional, visual analysis always works.
"""

import re
from PIL import Image, ImageFilter, ImageEnhance, ImageStat

# Try to import pytesseract (optional)
try:
    import pytesseract

    TESSERACT_AVAILABLE = True
    try:
        pytesseract.get_tesseract_version()
    except Exception:
        TESSERACT_AVAILABLE = False
except ImportError:
    pytesseract = None
    TESSERACT_AVAILABLE = False


class LocationAnalyzer:
    def __init__(self):
        self.clues = []

        # Country indicators based on text/language
        self.language_patterns = {
            "Русский": {
                "pattern": r"[а-яёА-ЯЁ]{3,}",
                "country": "Россия",
            },
            "Японский": {
                "pattern": r"[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff]{2,}",
                "country": "Япония",
            },
            "Корейский": {
                "pattern": r"[\uac00-\ud7af]{2,}",
                "country": "Южная Корея",
            },
            "Тайский": {
                "pattern": r"[\u0e00-\u0e7f]{3,}",
                "country": "Таиланд",
            },
            "Арабский": {
                "pattern": r"[\u0600-\u06ff]{3,}",
                "country": "Ближний Восток",
            },
            "Иврит": {
                "pattern": r"[\u0590-\u05ff]{3,}",
                "country": "Израиль",
            },
            "Греческий": {
                "pattern": r"[\u0370-\u03ff]{3,}",
                "country": "Греция",
            },
        }

        # Specific text markers
        self.text_markers = {
            "STOP": "США/Канада/Австралия",
            "PARE": "Бразилия",
            "ARRET": "Канада (Квебек)",
            "ALTO": "Мексика",
            "СТОП": "Россия/Украина",
            "EXIT": "США",
            "SORTIE": "Франция/Канада",
            "AUSFAHRT": "Германия",
            "SALIDA": "Испания/Лат. Америка",
            "USCITA": "Италия",
        }

        # Domain/URL patterns
        self.domain_patterns = {
            r"\.ru\b": "Россия",
            r"\.br\b": "Бразилия",
            r"\.jp\b": "Япония",
            r"\.kr\b": "Южная Корея",
            r"\.de\b": "Германия",
            r"\.fr\b": "Франция",
            r"\.uk\b": "Великобритания",
            r"\.au\b": "Австралия",
            r"\.mx\b": "Мексика",
            r"\.pl\b": "Польша",
            r"\.tr\b": "Турция",
            r"\.se\b": "Швеция",
            r"\.no\b": "Норвегия",
        }

        # Phone number patterns
        self.phone_patterns = {
            r"\+7": "Россия",
            r"\+1": "США/Канада",
            r"\+44": "Великобритания",
            r"\+33": "Франция",
            r"\+49": "Германия",
            r"\+55": "Бразилия",
            r"\+52": "Мексика",
            r"\+61": "Австралия",
            r"\+91": "Индия",
            r"\+90": "Турция",
            r"\+34": "Испания",
            r"\+39": "Италия",
            r"\+380": "Украина",
        }

    def analyze(self, image: Image.Image) -> dict:
        """
        Analyze a screenshot and return location estimation.
        Always returns a result - even without OCR.
        """
        self.clues = []
        result = {
            "country": None,
            "region": None,
            "city": None,
            "confidence": 0,
            "clues": [],
            "lat": None,
            "lng": None,
        }

        # Step 1: Visual analysis (always works, no dependencies)
        visual_clues = self._analyze_visual_detailed(image)
        if visual_clues.get("country"):
            result["country"] = visual_clues["country"]
            result["confidence"] += visual_clues.get("confidence", 15)

        # Step 2: OCR (optional - only if Tesseract is installed)
        text = ""
        if TESSERACT_AVAILABLE:
            text = self._extract_text(image)

            if text:
                # Analyze text for language
                lang_result = self._detect_language(text)
                if lang_result:
                    result["country"] = lang_result
                    result["confidence"] += 30

                # Check text markers
                marker_result = self._check_text_markers(text)
                if marker_result:
                    if not result["country"]:
                        result["country"] = marker_result
                    result["confidence"] += 20

                # Check domains
                domain_result = self._check_domains(text)
                if domain_result:
                    result["country"] = domain_result
                    result["confidence"] += 40

                # Check phone numbers
                phone_result = self._check_phone_numbers(text)
                if phone_result:
                    if not result["country"]:
                        result["country"] = phone_result
                    result["confidence"] += 25
        else:
            self.clues.append("OCR не установлен (визуальный анализ)")

        # Step 3: Color-based region analysis
        color_result = self._analyze_colors(image)
        if color_result and not result["country"]:
            result["country"] = color_result
            result["confidence"] += 10

        # Step 4: Landscape type detection
        landscape = self._detect_landscape(image)
        if landscape:
            self.clues.append(landscape)
            result["confidence"] += 5

        # Ensure minimum confidence for visual-only results
        if result["country"] and result["confidence"] < 15:
            result["confidence"] = 15

        # Cap confidence
        result["confidence"] = min(result["confidence"], 95)
        result["clues"] = self.clues

        # Get approximate coordinates
        if result["country"]:
            coords = self._country_to_coords(result["country"])
            if coords:
                result["lat"] = coords[0]
                result["lng"] = coords[1]

        return result

    def _extract_text(self, image: Image.Image) -> str:
        """Extract text from image using OCR (if available)."""
        if not TESSERACT_AVAILABLE:
            return ""

        try:
            img = image.copy()

            # Resize for faster processing
            max_width = 1600
            if img.width > max_width:
                ratio = max_width / img.width
                img = img.resize(
                    (int(img.width * ratio), int(img.height * ratio)),
                    Image.LANCZOS,
                )

            # Enhance for OCR
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(1.8)
            img = img.filter(ImageFilter.SHARPEN)

            # Try with just english first (most reliable)
            try:
                text = pytesseract.image_to_string(img, config="--psm 11 --oem 3")
            except Exception:
                text = pytesseract.image_to_string(img)

            if text and text.strip():
                clean_text = text.strip()
                words = [w for w in clean_text.split() if len(w) > 1]
                if words:
                    preview = " ".join(words[:4])
                    self.clues.append(f"Текст: \"{preview}\"")
                return clean_text

        except Exception as e:
            self.clues.append(f"OCR ошибка: {type(e).__name__}")

        return ""

    def _detect_language(self, text: str) -> str | None:
        """Detect language from extracted text."""
        if not text:
            return None

        for lang_name, info in self.language_patterns.items():
            matches = re.findall(info["pattern"], text)
            if len(matches) >= 2:
                self.clues.append(f"Язык: {lang_name}")
                return info["country"]

        # Latin language detection
        latin_words = re.findall(r"[a-zA-ZáéíóúñüöäåæøÆØÅàèìòùâêîôû]+", text)
        if len(latin_words) >= 3:
            text_lower = " ".join(latin_words).lower()
            if any(w in text_lower for w in ["rua", "avenida", "praça", "estrada"]):
                self.clues.append("Язык: португальский")
                return "Бразилия"
            if any(w in text_lower for w in ["calle", "avenida", "plaza", "camino"]):
                self.clues.append("Язык: испанский")
                return "Испания/Лат. Америка"
            if any(w in text_lower for w in ["rue", "avenue", "place", "boulevard"]):
                self.clues.append("Язык: французский")
                return "Франция"
            if any(w in text_lower for w in ["straße", "platz", "weg", "straβe"]):
                self.clues.append("Язык: немецкий")
                return "Германия"
            if any(w in text_lower for w in ["jalan", "jl", "kabupaten"]):
                self.clues.append("Язык: индонезийский")
                return "Индонезия"
            if any(w in text_lower for w in ["road", "street", "highway", "drive"]):
                self.clues.append("Язык: английский")
                return "Англоязычная страна"

        return None

    def _check_text_markers(self, text: str) -> str | None:
        """Check for specific text markers."""
        if not text:
            return None

        text_upper = text.upper()
        for marker, country in self.text_markers.items():
            if marker in text_upper:
                self.clues.append(f"Знак: \"{marker}\" → {country}")
                return country

        return None

    def _check_domains(self, text: str) -> str | None:
        """Check for domain names in text."""
        if not text:
            return None

        for pattern, country in self.domain_patterns.items():
            if re.search(pattern, text, re.IGNORECASE):
                self.clues.append(f"Домен найден → {country}")
                return country

        return None

    def _check_phone_numbers(self, text: str) -> str | None:
        """Check for phone number patterns."""
        if not text:
            return None

        for pattern, country in self.phone_patterns.items():
            if re.search(re.escape(pattern), text):
                self.clues.append(f"Тел. код {pattern} → {country}")
                return country

        return None

    def _analyze_visual_detailed(self, image: Image.Image) -> dict:
        """
        Detailed visual analysis that works without OCR.
        Analyzes colors, vegetation, sky, road surface, etc.
        """
        result = {"country": None, "confidence": 0}
        width, height = image.size

        # Divide image into regions
        sky_region = image.crop((0, 0, width, height // 4))
        middle_region = image.crop((0, height // 4, width, height * 3 // 4))
        road_region = image.crop((width // 4, height * 3 // 4, width * 3 // 4, height))

        # --- Sky analysis ---
        sky_stat = ImageStat.Stat(sky_region)
        sky_r, sky_g, sky_b = sky_stat.mean[:3]

        if sky_b > 160 and sky_r < 150 and sky_g < 180:
            self.clues.append("Ясное голубое небо")
        elif sky_r > sky_b and sky_r > 150:
            self.clues.append("Закат/рассвет")
        elif all(c > 180 for c in [sky_r, sky_g, sky_b]):
            self.clues.append("Пасмурное небо (Сев. Европа/UK)")
            result["country"] = "Северная Европа"
            result["confidence"] = 10

        # --- Road/ground analysis ---
        road_stat = ImageStat.Stat(road_region)
        road_r, road_g, road_b = road_stat.mean[:3]

        if road_r > 120 and road_g < 80 and road_b < 80:
            self.clues.append("Красная почва (Африка/Бразилия/Австралия)")
            result["country"] = "Африка/Бразилия/Австралия"
            result["confidence"] = 15
        elif road_r > 140 and road_g > 90 and road_b < 110 and road_r > road_b + 40:
            self.clues.append("Песчаная дорога (Африка/Ближ. Восток)")
            result["country"] = "Африка/Ближний Восток"
            result["confidence"] = 12
        elif all(c < 60 for c in [road_r, road_g, road_b]):
            self.clues.append("Тёмный асфальт (развитая страна)")
        elif road_r > 160 and road_g > 160 and road_b > 160:
            self.clues.append("Бетон/светлое покрытие")

        # --- Vegetation analysis ---
        img_small = middle_region.resize((100, 75))
        pixels = list(img_small.getdata())
        total = len(pixels)

        green_count = sum(1 for r, g, b in pixels if g > r + 15 and g > b + 15 and g > 80)
        green_ratio = green_count / total

        brown_count = sum(1 for r, g, b in pixels if r > 100 and g > 50 and g < r and b < r - 30)
        brown_ratio = brown_count / total

        blue_count = sum(1 for r, g, b in pixels if b > 120 and b > r + 30 and b > g + 10)
        blue_ratio = blue_count / total

        white_count = sum(1 for r, g, b in pixels if r > 200 and g > 200 and b > 200)
        white_ratio = white_count / total

        if green_ratio > 0.35:
            self.clues.append(f"Густая зелень ({int(green_ratio*100)}%) — тропики/лес")
            if not result["country"]:
                result["country"] = "Тропики (ЮВ Азия/Лат. Америка)"
                result["confidence"] = 10
        elif green_ratio > 0.2:
            self.clues.append(f"Умеренная зелень ({int(green_ratio*100)}%)")
        elif green_ratio < 0.05:
            self.clues.append("Почти нет зелени")
            if brown_ratio > 0.2:
                self.clues.append("Засушливый регион")
                if not result["country"]:
                    result["country"] = "Пустыня/степь"
                    result["confidence"] = 10

        if white_ratio > 0.3:
            self.clues.append(f"Много белого ({int(white_ratio*100)}%) — снег/зима")
            if not result["country"]:
                result["country"] = "Северная страна (зима)"
                result["confidence"] = 10

        if blue_ratio > 0.15:
            self.clues.append("Водоём виден")

        # --- Overall brightness/contrast ---
        overall_stat = ImageStat.Stat(image)
        brightness = sum(overall_stat.mean[:3]) / 3

        if brightness > 170:
            self.clues.append("Яркая сцена (солнечно)")
        elif brightness < 80:
            self.clues.append("Тёмная сцена (ночь/пасмурно)")

        return result

    def _analyze_colors(self, image: Image.Image) -> str | None:
        """Additional color-based analysis for road markings."""
        width, height = image.size

        # Check road markings in lower portion
        road_area = image.crop((width // 4, height * 2 // 3, width * 3 // 4, height))
        road_small = road_area.resize((50, 30))
        pixels = list(road_small.getdata())

        # Yellow road markings -> USA, Canada, parts of Latin America
        yellow_count = sum(
            1 for r, g, b in pixels
            if r > 180 and g > 150 and b < 80
        )
        if yellow_count > 5:
            self.clues.append("Жёлтая разметка (Америка)")
            return "Северная/Южная Америка"

        # White dashed markings (most countries)
        white_line_count = sum(
            1 for r, g, b in pixels
            if r > 220 and g > 220 and b > 220
        )
        if white_line_count > 10:
            self.clues.append("Белая дорожная разметка")

        return None

    def _detect_landscape(self, image: Image.Image) -> str | None:
        """Detect landscape type."""
        width, height = image.size
        img_small = image.resize((100, 75))
        pixels = list(img_small.getdata())
        total = len(pixels)

        # Calculate color distributions
        very_green = sum(1 for r, g, b in pixels if g > 100 and g > r * 1.3 and g > b * 1.3)
        very_brown = sum(1 for r, g, b in pixels if r > 120 and 60 < g < r * 0.8 and b < 80)
        very_blue = sum(1 for r, g, b in pixels if b > 150 and b > r + 40)

        if very_green / total > 0.4:
            return "Ландшафт: густой лес/джунгли"
        elif very_brown / total > 0.3:
            return "Ландшафт: пустыня/саванна"
        elif very_blue / total > 0.3:
            return "Ландшафт: побережье/океан"

        return None

    def _country_to_coords(self, country: str) -> tuple | None:
        """Get approximate center coordinates for a country/region."""
        coords_map = {
            "Россия": (55.75, 37.62),
            "США": (39.83, -98.58),
            "Канада": (56.13, -106.35),
            "Бразилия": (-14.24, -51.93),
            "Япония": (36.20, 138.25),
            "Южная Корея": (35.91, 127.77),
            "Таиланд": (15.87, 100.99),
            "Великобритания": (55.38, -3.44),
            "Франция": (46.23, 2.21),
            "Германия": (51.17, 10.45),
            "Испания": (40.46, -3.75),
            "Италия": (41.87, 12.57),
            "Австралия": (-25.27, 133.78),
            "Мексика": (23.63, -102.55),
            "Аргентина": (-38.42, -63.62),
            "Индия": (20.59, 78.96),
            "Индонезия": (-0.79, 113.92),
            "Турция": (38.96, 35.24),
            "Польша": (51.92, 19.15),
            "Украина": (48.38, 31.17),
            "Израиль": (31.05, 34.85),
            "Греция": (39.07, 21.82),
            "Швеция": (60.13, 18.64),
            "Норвегия": (60.47, 8.47),
            "Северная Европа": (58.0, 14.0),
            "Африка/Бразилия/Австралия": (-15.0, 25.0),
            "Африка/Ближний Восток": (25.0, 35.0),
            "Тропики (ЮВ Азия/Лат. Америка)": (5.0, 105.0),
            "Пустыня/степь": (30.0, 45.0),
            "Северная страна (зима)": (62.0, 25.0),
            "Северная/Южная Америка": (25.0, -80.0),
            "Ближний Восток": (30.0, 40.0),
            "Англоязычная страна": (40.0, -3.0),
            "Испания/Лат. Америка": (20.0, -80.0),
            "США/Канада": (45.0, -90.0),
            "США/Канада/Австралия": (39.0, -98.0),
            "Россия/Украина": (52.0, 35.0),
            "Канада (Квебек)": (52.0, -73.0),
            "Франция/Канада": (47.0, 2.0),
        }

        # Try exact match first
        if country in coords_map:
            return coords_map[country]

        # Try partial match
        for key, value in coords_map.items():
            if key in country or country in key:
                return value

        return None
