"""
Location Analyzer for GeoGuessr Solver.
Analyzes screenshots using OCR and visual heuristics to determine location.
No AI/API required - uses local processing only.
"""

import re
from PIL import Image, ImageFilter, ImageEnhance

try:
    import pytesseract
except ImportError:
    pytesseract = None


class LocationAnalyzer:
    def __init__(self):
        self.clues = []

        # Country indicators based on text/language
        self.language_patterns = {
            "ru": {
                "pattern": r"[а-яёА-ЯЁ]{3,}",
                "country": "Россия",
                "countries": ["Россия", "Украина", "Беларусь", "Казахстан"],
            },
            "ja": {
                "pattern": r"[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff]{2,}",
                "country": "Япония",
                "countries": ["Япония"],
            },
            "ko": {
                "pattern": r"[\uac00-\ud7af]{2,}",
                "country": "Южная Корея",
                "countries": ["Южная Корея"],
            },
            "th": {
                "pattern": r"[\u0e00-\u0e7f]{3,}",
                "country": "Таиланд",
                "countries": ["Таиланд"],
            },
            "ar": {
                "pattern": r"[\u0600-\u06ff]{3,}",
                "country": "Ближний Восток",
                "countries": ["ОАЭ", "Саудовская Аравия", "Иордания", "Египет"],
            },
            "he": {
                "pattern": r"[\u0590-\u05ff]{3,}",
                "country": "Израиль",
                "countries": ["Израиль"],
            },
            "el": {
                "pattern": r"[\u0370-\u03ff]{3,}",
                "country": "Греция",
                "countries": ["Греция", "Кипр"],
            },
            "zh": {
                "pattern": r"[\u4e00-\u9fff]{3,}",
                "country": "Китай/Тайвань",
                "countries": ["Китай", "Тайвань"],
            },
        }

        # Road sign color patterns (dominant colors in specific regions)
        self.sign_colors = {
            "green_white": ["США", "Бразилия", "Мексика"],
            "blue_white": ["Европа", "Австралия"],
            "brown": ["Национальные парки"],
            "yellow_black": ["Австралия", "Новая Зеландия"],
        }

        # Domain/URL patterns on signs
        self.domain_patterns = {
            r"\.ru\b": "Россия",
            r"\.br\b": "Бразилия",
            r"\.jp\b": "Япония",
            r"\.kr\b": "Южная Корея",
            r"\.de\b": "Германия",
            r"\.fr\b": "Франция",
            r"\.it\b": "Италия",
            r"\.es\b": "Испания",
            r"\.uk\b": "Великобритания",
            r"\.au\b": "Австралия",
            r"\.co\.za\b": "ЮАР",
            r"\.mx\b": "Мексика",
            r"\.ar\b": "Аргентина",
            r"\.cl\b": "Чили",
            r"\.pl\b": "Польша",
            r"\.tr\b": "Турция",
            r"\.id\b": "Индонезия",
            r"\.ph\b": "Филиппины",
            r"\.in\b": "Индия",
            r"\.ng\b": "Нигерия",
            r"\.ke\b": "Кения",
            r"\.se\b": "Швеция",
            r"\.no\b": "Норвегия",
            r"\.fi\b": "Финляндия",
            r"\.dk\b": "Дания",
        }

        # Specific text markers
        self.text_markers = {
            "STOP": ["США", "Канада", "Австралия"],
            "PARE": ["Бразилия", "Португалия"],
            "ARRET": ["Канада (Квебек)", "Франция"],
            "ALTO": ["Мексика", "Испания"],
            "СТОП": ["Россия", "Украина"],
            "km/h": ["Метрическая система (не США)"],
            "mph": ["США", "Великобритания"],
            "EXIT": ["США"],
            "SORTIE": ["Франция", "Канада"],
            "AUSFAHRT": ["Германия", "Австрия"],
            "SALIDA": ["Испания", "Латинская Америка"],
            "USCITA": ["Италия"],
            "Jl.": ["Индонезия"],
            "Rua": ["Бразилия", "Португалия"],
            "Calle": ["Испания", "Латинская Америка"],
            "Rue": ["Франция", "Канада"],
            "Straße": ["Германия", "Австрия"],
            "ул.": ["Россия"],
            "вул.": ["Украина"],
            "Carretera": ["Мексика", "Испания"],
            "Route Nationale": ["Франция"],
            "Bundesstraße": ["Германия"],
            "Highway": ["США", "Канада", "Австралия"],
            "Motorway": ["Великобритания", "Австралия"],
        }

        # Phone number patterns
        self.phone_patterns = {
            r"\+7\s": "Россия",
            r"\+1\s": "США/Канада",
            r"\+44\s": "Великобритания",
            r"\+33\s": "Франция",
            r"\+49\s": "Германия",
            r"\+81\s": "Япония",
            r"\+82\s": "Южная Корея",
            r"\+55\s": "Бразилия",
            r"\+52\s": "Мексика",
            r"\+61\s": "Австралия",
            r"\+91\s": "Индия",
            r"\+90\s": "Турция",
            r"\+34\s": "Испания",
            r"\+39\s": "Италия",
            r"\+380\s": "Украина",
        }

    def analyze(self, image: Image.Image) -> dict:
        """
        Analyze a screenshot and return location estimation.
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

        # Step 1: OCR - Extract text from image
        text = self._extract_text(image)

        # Step 2: Analyze text for language
        lang_result = self._detect_language(text)
        if lang_result:
            result["country"] = lang_result
            result["confidence"] += 30

        # Step 3: Check for specific text markers
        marker_result = self._check_text_markers(text)
        if marker_result:
            if not result["country"]:
                result["country"] = marker_result
            result["confidence"] += 20

        # Step 4: Check for domain names
        domain_result = self._check_domains(text)
        if domain_result:
            result["country"] = domain_result
            result["confidence"] += 40

        # Step 5: Check phone numbers
        phone_result = self._check_phone_numbers(text)
        if phone_result:
            if not result["country"]:
                result["country"] = phone_result
            result["confidence"] += 25

        # Step 6: Analyze visual features
        visual_result = self._analyze_visual(image)
        if visual_result:
            self.clues.extend(visual_result)
            result["confidence"] += 10

        # Step 7: Driving side detection
        driving_side = self._detect_driving_side(image)
        if driving_side:
            self.clues.append(f"Движение: {driving_side}")
            result["confidence"] += 5

        # Cap confidence
        result["confidence"] = min(result["confidence"], 95)
        result["clues"] = self.clues

        # Try to get approximate coordinates for the country
        if result["country"]:
            coords = self._country_to_coords(result["country"])
            if coords:
                result["lat"] = coords[0]
                result["lng"] = coords[1]

        return result

    def _extract_text(self, image: Image.Image) -> str:
        """Extract text from image using OCR."""
        if pytesseract is None:
            self.clues.append("OCR недоступен (установите pytesseract)")
            return ""

        try:
            # Preprocess for better OCR
            # Resize for better recognition
            img = image.copy()
            if img.width > 2000:
                ratio = 2000 / img.width
                img = img.resize(
                    (int(img.width * ratio), int(img.height * ratio)),
                    Image.LANCZOS,
                )

            # Enhance contrast
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(1.5)

            # Sharpen
            img = img.filter(ImageFilter.SHARPEN)

            # Run OCR with multiple languages
            text = pytesseract.image_to_string(
                img, lang="eng+rus+jpn+kor+chi_sim+ara", config="--psm 11"
            )

            if text.strip():
                # Show first few detected words as clue
                words = text.strip().split()[:5]
                self.clues.append(f"Текст: {' '.join(words)}...")

            return text

        except Exception as e:
            self.clues.append(f"OCR ошибка: {str(e)[:50]}")
            return ""

    def _detect_language(self, text: str) -> str | None:
        """Detect language from extracted text."""
        if not text:
            return None

        for lang_code, info in self.language_patterns.items():
            matches = re.findall(info["pattern"], text)
            if len(matches) >= 2:
                self.clues.append(f"Язык: {lang_code} ({len(matches)} совпадений)")
                return info["country"]

        # Check for Latin-based languages by word patterns
        latin_text = re.findall(r"[a-zA-ZáéíóúñüöäåæøÆØÅ]+", text)
        if latin_text:
            text_lower = " ".join(latin_text).lower()
            if any(w in text_lower for w in ["rua", "avenida", "praça"]):
                self.clues.append("Язык: португальский")
                return "Бразилия"
            if any(w in text_lower for w in ["calle", "avenida", "plaza"]):
                self.clues.append("Язык: испанский")
                return "Испания/Латинская Америка"
            if any(w in text_lower for w in ["rue", "avenue", "place", "boulevard"]):
                self.clues.append("Язык: французский")
                return "Франция"
            if any(w in text_lower for w in ["straße", "platz", "weg"]):
                self.clues.append("Язык: немецкий")
                return "Германия"

        return None

    def _check_text_markers(self, text: str) -> str | None:
        """Check for specific text markers that indicate countries."""
        if not text:
            return None

        for marker, countries in self.text_markers.items():
            if marker.lower() in text.lower():
                self.clues.append(f"Маркер: '{marker}' → {countries[0]}")
                return countries[0]

        return None

    def _check_domains(self, text: str) -> str | None:
        """Check for domain names in text."""
        if not text:
            return None

        for pattern, country in self.domain_patterns.items():
            if re.search(pattern, text, re.IGNORECASE):
                self.clues.append(f"Домен: {pattern} → {country}")
                return country

        return None

    def _check_phone_numbers(self, text: str) -> str | None:
        """Check for phone number patterns."""
        if not text:
            return None

        for pattern, country in self.phone_patterns.items():
            if re.search(pattern, text):
                self.clues.append(f"Телефон: {pattern.strip()} → {country}")
                return country

        return None

    def _analyze_visual(self, image: Image.Image) -> list:
        """Analyze visual features of the image."""
        clues = []

        # Analyze dominant colors in specific regions
        # Top portion (sky) - can indicate hemisphere/climate
        width, height = image.size
        sky_region = image.crop((0, 0, width, height // 4))
        road_region = image.crop((0, height * 3 // 4, width, height))

        # Sky color analysis
        sky_colors = sky_region.resize((1, 1)).getpixel((0, 0))
        if sky_colors[2] > 180 and sky_colors[0] < 150:
            clues.append("Ясное небо (тропики/лето)")

        # Road color analysis
        road_colors = road_region.resize((1, 1)).getpixel((0, 0))
        if road_colors[0] > 100 and road_colors[1] < 80 and road_colors[2] < 80:
            clues.append("Красная почва (Африка/Бразилия/Австралия)")
        elif all(c > 150 for c in road_colors):
            clues.append("Светлая дорога (бетон)")
        elif all(c < 80 for c in road_colors):
            clues.append("Тёмный асфальт")

        # Vegetation analysis (green in image)
        img_array = list(image.getdata())
        green_pixels = sum(
            1 for r, g, b in img_array if g > r + 20 and g > b + 20 and g > 100
        )
        green_ratio = green_pixels / len(img_array)

        if green_ratio > 0.3:
            clues.append("Много зелени (тропики/лес)")
        elif green_ratio < 0.05:
            clues.append("Мало зелени (пустыня/зима/город)")

        return clues

    def _detect_driving_side(self, image: Image.Image) -> str | None:
        """
        Try to detect driving side (left/right) from the image.
        This is a heuristic based on road position in the image.
        """
        # This is a simplified heuristic
        # In practice, detecting driving side requires more sophisticated analysis
        width, height = image.size

        # Look at the bottom center of the image for road markings
        # If road lines are more to the left -> right-hand driving
        # If road lines are more to the right -> left-hand driving
        road_strip = image.crop((0, height * 2 // 3, width, height))

        # Convert to grayscale and look for white/yellow lines
        road_gray = road_strip.convert("L")

        # Simple check: look for bright horizontal bands (road markings)
        left_half = road_gray.crop((0, 0, road_gray.width // 2, road_gray.height))
        right_half = road_gray.crop(
            (road_gray.width // 2, 0, road_gray.width, road_gray.height)
        )

        left_brightness = sum(left_half.getdata()) / (
            left_half.width * left_half.height
        )
        right_brightness = sum(right_half.getdata()) / (
            right_half.width * right_half.height
        )

        # This is very heuristic and may not be accurate
        # Just providing it as additional context
        if abs(left_brightness - right_brightness) > 20:
            if left_brightness > right_brightness:
                return "правостороннее (UK/JP/AU/IN)"
            else:
                return "левостороннее (большинство стран)"

        return None

    def _country_to_coords(self, country: str) -> tuple | None:
        """Get approximate center coordinates for a country."""
        coords_map = {
            "Россия": (55.7558, 37.6173),
            "США": (39.8283, -98.5795),
            "Канада": (56.1304, -106.3468),
            "Бразилия": (-14.2350, -51.9253),
            "Япония": (36.2048, 138.2529),
            "Южная Корея": (35.9078, 127.7669),
            "Таиланд": (15.8700, 100.9925),
            "Великобритания": (55.3781, -3.4360),
            "Франция": (46.2276, 2.2137),
            "Германия": (51.1657, 10.4515),
            "Испания": (40.4637, -3.7492),
            "Италия": (41.8719, 12.5674),
            "Австралия": (-25.2744, 133.7751),
            "Мексика": (23.6345, -102.5528),
            "Аргентина": (-38.4161, -63.6167),
            "Чили": (-35.6751, -71.5430),
            "Индия": (20.5937, 78.9629),
            "Индонезия": (-0.7893, 113.9213),
            "Турция": (38.9637, 35.2433),
            "Польша": (51.9194, 19.1451),
            "Украина": (48.3794, 31.1656),
            "Израиль": (31.0461, 34.8516),
            "Греция": (39.0742, 21.8243),
            "ЮАР": (-30.5595, 22.9375),
            "Нигерия": (9.0820, 8.6753),
            "Кения": (-0.0236, 37.9062),
            "Швеция": (60.1282, 18.6435),
            "Норвегия": (60.4720, 8.4689),
            "Финляндия": (61.9241, 25.7482),
            "Дания": (56.2639, 9.5018),
            "Китай/Тайвань": (35.8617, 104.1954),
            "Филиппины": (12.8797, 121.7740),
            "Испания/Латинская Америка": (40.4637, -3.7492),
            "Канада (Квебек)": (52.9399, -73.5491),
        }

        for key, value in coords_map.items():
            if key in country or country in key:
                return value

        return None
