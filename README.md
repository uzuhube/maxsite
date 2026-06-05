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
Python-приложение с двумя режимами работы.

**Proxy Mode (рекомендуется) — 100% точность:**
- 🎯 Перехват запросов к Google Maps через локальный прокси
- 🌍 Показывает точный город/страну в прозрачном оверлее
- 🗺️ Ссылка на Google Maps
- 🔄 Автоматическое обновление при смене раунда

**Visual Mode (fallback) — без прокси:**
- 📷 Захват экрана по горячей клавише (Ctrl+Shift+G)
- 🔤 OCR распознавание текста (опционально)
- 🎨 Визуальный анализ (цвет почвы, растительность, разметка)
- 🌐 Определение языка, доменов, телефонных кодов

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

### Desktop App — Proxy Mode (для Steam, 100% точность)

Перехватывает сетевые запросы GeoGuessr к Google Maps и извлекает точные координаты.

**Требования:**
- Python 3.10+
- mitmproxy (`pip install mitmproxy`)

**Быстрый старт (Windows):**
```
1. Дважды кликните start_solver.bat
2. При первом запуске установите сертификат mitmproxy:
   - Откройте http://mitm.it в браузере
   - Скачайте и установите сертификат для Windows
3. Запустите GeoGuessr в Steam — координаты появятся в оверлее
```

**Ручная установка:**
```bash
pip install mitmproxy requests Pillow pynput
cd desktop-app
python proxy_solver.py
```

**Настройка прокси вручную:**
- Windows: Параметры → Сеть → Прокси → Вкл → `127.0.0.1:8082`
- Или bat-файл сделает это автоматически

### Desktop App — Visual Mode (без прокси, менее точно)

Анализирует скриншоты через OCR и визуальные эвристики. Не требует настройки прокси, но точность значительно ниже.

**Установка:**
```bash
pip install Pillow pynput mss requests
cd desktop-app
python main.py
```

**Опционально для OCR (лучшая точность):**
```bash
pip install pytesseract
# + Tesseract: https://github.com/UB-Mannheim/tesseract/wiki (Windows)
# + sudo apt install tesseract-ocr (Linux)
```

---

## Использование

### Browser Extension (Chrome/Firefox)
1. Установите расширение (см. выше)
2. Откройте игру на [geoguessr.com](https://www.geoguessr.com)
3. Координаты и город/страна отображаются автоматически в оверлее

### Desktop — Proxy Mode (рекомендуется для Steam)
1. Запустите `start_solver.bat` (или `python proxy_solver.py`)
2. Настройте прокси (bat делает это автоматически)
3. Откройте GeoGuessr в Steam
4. Оверлей покажет точный город/страну поверх игры
5. ПКМ на оверлее — закрыть, ЛКМ — перетащить

### Desktop — Visual Mode (fallback)
1. Запустите `python main.py`
2. Нажмите **Ctrl+Shift+G** или кнопку "Start"
3. Результат появится в оверлее поверх игры

---

## Как это работает

### Chrome Extension
- Перехватывает XHR/Fetch запросы к Google Maps API
- Парсит ответы для извлечения координат
- Пытается напрямую обратиться к Google Maps Panorama объекту
- Отображает координаты в оверлее на странице

### Desktop — Proxy Mode (рекомендуется)
- Запускает локальный HTTPS-прокси (mitmproxy) на порту 8082
- Перехватывает запросы GeoGuessr к Google Maps API
- Извлекает точные координаты из ответов
- Обратное геокодирование → показывает город/страну
- **100% точность** — те же данные, что браузерное расширение

### Desktop — Visual Mode (fallback)
Анализирует скриншот по нескольким параметрам:

| Метод | Точность | Описание |
|-------|----------|----------|
| OCR + язык | Средняя | Определяет язык текста на вывесках |
| Текстовые маркеры | Средняя | STOP/PARE/ALTO, названия улиц |
| Домены | Высокая | .ru, .br, .jp на вывесках |
| Визуальный анализ | Низкая | Цвет почвы, растительность, разметка |

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
│   ├── proxy_solver.py     # Proxy Mode (100% точность)
│   ├── proxy_addon.py      # mitmproxy addon
│   ├── start_solver.bat    # Авто-запуск для Windows
│   ├── main.py             # Visual Mode (fallback)
│   ├── capture.py
│   ├── analyzer.py
│   ├── overlay.py
│   └── requirements.txt
└── README.md
```

---

## Лицензия

MIT
