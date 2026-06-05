# 🌍 GeoGuessr Solver

Автоматическое распознавание места для GeoGuessr. Работает как в **браузере**, так и в **Steam** приложении. Без AI API — все анализы выполняются локально.

## Компоненты

### 1. Browser Extension (Chrome / Firefox)
Извлекает координаты напрямую из Google Maps API объектов на странице GeoGuessr.
Поддерживает **Chrome** и **Firefox**.

**Возможности:**
- 🎯 100% точное определение координат (извлечение из API)
- 🗺️ Ссылка на Google Maps
- 📍 Оверлей с координатами прямо на странице
- 🔄 Автоматическое обновление при смене раунда
- 📋 Копирование координат в буфер обмена
- 🌐 Обратное геокодирование (показывает страну/город)

### 2. Desktop App (Steam / Любое приложение)
Python-приложение для анализа экрана с помощью OCR и визуальных эвристик.

**Возможности:**
- 📷 Захват экрана по горячей клавише (Ctrl+Shift+G)
- 🔤 OCR распознавание текста (вывески, знаки, номера)
- 🌐 Определение языка → страна
- 🛑 Анализ дорожных знаков и маркеров
- 📞 Распознавание телефонных кодов
- 🌐 Поиск доменных имен
- 🎨 Анализ визуальных особенностей (цвет почвы, растительность)
- 🚗 Определение стороны движения

---

## Установка

### Chrome

1. Откройте `chrome://extensions/` в Chrome
2. Включите "Режим разработчика" (Developer mode)
3. Нажмите "Загрузить распакованное расширение" (Load unpacked)
4. Выберите папку `chrome-extension/`
5. Откройте GeoGuessr — расширение начнёт работать автоматически

### Firefox

1. Откройте `about:debugging#/runtime/this-firefox` в Firefox
2. Нажмите "Загрузить временное дополнение" (Load Temporary Add-on)
3. Выберите файл `firefox-extension/manifest.json`
4. Откройте GeoGuessr — расширение начнёт работать автоматически

> **Для постоянной установки:** упакуйте `firefox-extension/` в `.xpi` файл:
> ```bash
> cd firefox-extension && zip -r ../geoguessr-solver.xpi * && cd ..
> ```
> Затем установите через `about:addons` → "Установить дополнение из файла"

### Desktop App (для Steam)

**Требования:**
- Python 3.10+
- Tesseract OCR

**Linux:**
```bash
sudo apt-get install tesseract-ocr tesseract-ocr-rus tesseract-ocr-jpn tesseract-ocr-kor
cd desktop-app
pip install -r requirements.txt
python main.py
```

**Windows:**
```bash
# Установите Tesseract: https://github.com/UB-Mannheim/tesseract/wiki
# Добавьте в PATH

cd desktop-app
pip install -r requirements.txt
python main.py
```

**macOS:**
```bash
brew install tesseract tesseract-lang
cd desktop-app
pip install -r requirements.txt
python main.py
```

---

## Использование

### Chrome Extension
1. Установите расширение
2. Откройте игру на [geoguessr.com](https://www.geoguessr.com)
3. Координаты будут отображаться автоматически в оверлее и в popup расширения

### Desktop App
1. Запустите `python main.py`
2. Откройте GeoGuessr (Steam или браузер)
3. Нажмите **Ctrl+Shift+G** или кнопку "Scan Now"
4. Результат появится в окне приложения

---

## Как это работает

### Chrome Extension
- Перехватывает XHR/Fetch запросы к Google Maps API
- Парсит ответы для извлечения координат
- Пытается напрямую обратиться к Google Maps Panorama объекту
- Отображает координаты в оверлее на странице

### Desktop App
Анализирует скриншот по нескольким параметрам:

| Метод | Точность | Описание |
|-------|----------|----------|
| OCR + язык | Высокая | Определяет язык текста на вывесках |
| Текстовые маркеры | Высокая | STOP/PARE/ALTO, названия улиц |
| Домены | Очень высокая | .ru, .br, .jp на вывесках |
| Телефоны | Высокая | Код страны +7, +1, +44 |
| Визуальные | Низкая | Цвет почвы, растительность |

---

## Структура проекта

```
geoguessr-solver/
├── chrome-extension/       # Chrome расширение (Manifest V3)
│   ├── manifest.json
│   ├── content.js
│   ├── background.js
│   ├── popup.html / popup.js
│   └── icons/
├── firefox-extension/      # Firefox расширение (Manifest V2)
│   ├── manifest.json
│   ├── content.js
│   ├── background.js
│   ├── popup.html / popup.js
│   └── icons/
├── desktop-app/            # Python приложение (Steam)
│   ├── main.py
│   ├── capture.py
│   ├── analyzer.py
│   ├── overlay.py
│   └── requirements.txt
└── README.md
```

---

## Лицензия

MIT
