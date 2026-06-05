# 🌍 GeoGuessr Solver

Автоматическое определение места для GeoGuessr. Работает в **браузере** (Chrome/Firefox) и **Steam**. Без AI — все данные извлекаются напрямую из игры.

## Компоненты

### 1. Desktop App — CDP Mode (Steam, рекомендуется)
Подключается к Steam через Chrome DevTools Protocol и читает сетевой трафик игры напрямую. **Без прокси, без инъекций, без расширений.**

- 🎯 **100% точность** — координаты из Google Maps API
- 🌍 Показывает город/страну в прозрачном оверлее поверх игры
- 🗺️ Ссылка на Google Maps
- 🔄 Автоматическое обновление при смене раунда
- 🪶 Лёгкий (~6 KB), без тяжёлых зависимостей

### 2. Browser Extension (Chrome / Firefox)
Извлекает координаты напрямую из Google Maps API на странице GeoGuessr.

- 🎯 100% точное определение координат
- 📍 Оверлей прямо на странице
- 🌐 Обратное геокодирование (город/страна)

### 3. Другие режимы (fallback)
- **Proxy Mode** — через mitmproxy, если CDP недоступен
- **Visual Mode** — анализ скриншотов (низкая точность, без интернета)

---

## Быстрый старт (Steam)

### 1. Настрой Steam
GeoGuessr → ПКМ → Свойства → Параметры запуска:
```
--remote-debugging-port=34788 --remote-allow-origins=*
```

### 2. Установи зависимости
```bash
pip install websocket-client requests Pillow
```

### 3. Запусти
```bash
python desktop-app/cdp_solver.py
```
Или на Windows: двойной клик на `desktop-app/start_cdp.bat`

### 4. Играй!
Оверлей автоматически покажет город/страну когда начнётся раунд.

**Управление оверлеем:**
- ЛКМ — перетащить
- ПКМ — закрыть
- Клик на "Открыть Google Maps" — откроет точку на карте

---

## Установка расширений (браузер)

### Chrome
1. `chrome://extensions/` → Режим разработчика → Загрузить распакованное
2. Выберите папку `chrome-extension/`
3. Откройте GeoGuessr — координаты появятся автоматически

### Firefox
1. `about:debugging#/runtime/this-firefox`
2. "Загрузить временное дополнение" → выберите `firefox-extension/manifest.json`
3. Откройте GeoGuessr

---

## Как это работает

### CDP Mode (Steam)
```
Steam (GeoGuessr)      GeoSolver
       │                    │
       │ ◄── CDP WebSocket ─┤  Подключается к порту 34788
       │                    │
       │  Network.enable    │  Мониторит сетевой трафик
       │ ──────────────────►│
       │                    │
       │  Maps RPC response │  Ловит ответы Google Maps API
       │ ──────────────────►│
       │                    │
       │                    │  Извлекает panorama ID
       │                    │
       │  Runtime.evaluate  │  Резолвит pano → lat/lng
       │ ◄──────────────────│  через StreetViewService
       │                    │
       │                    │  Показывает город/страну
       │                    │  в оверлее
```

Тот же подход, что использует [GeoHelper](https://github.com/wiktorekdev/geohelper), но реализован на Python с собственным визуалом.

### Browser Extension
- Перехватывает XHR/Fetch запросы к Google Maps API
- Парсит ответы для извлечения координат
- Оверлей прямо на странице GeoGuessr

---

## Структура проекта

```
geoguessr-solver/
├── desktop-app/
│   ├── cdp_solver.py       # CDP Mode — основной (Steam)
│   ├── start_cdp.bat       # Запуск на Windows
│   ├── proxy_solver.py     # Proxy Mode (альтернатива)
│   ├── proxy_addon.py      # mitmproxy addon
│   ├── start_solver.bat    # Proxy Mode запуск
│   ├── main.py             # Visual Mode (fallback)
│   ├── capture.py
│   ├── analyzer.py
│   ├── overlay.py
│   └── requirements.txt
├── chrome-extension/       # Chrome (Manifest V3)
│   ├── manifest.json
│   ├── content.js
│   ├── background.js
│   ├── popup.html / popup.js
│   └── icons/
├── firefox-extension/      # Firefox (Manifest V2)
│   ├── manifest.json
│   ├── content.js
│   ├── background.js
│   ├── popup.html / popup.js
│   └── icons/
└── README.md
```

---

## FAQ

**Q: Это безопасно?**
A: Да. Приложение не модифицирует игру, не инъектирует DLL, не меняет память. Оно просто читает сетевой трафик через стандартный отладочный интерфейс Chromium.

**Q: Будет ли бан?**
A: Инструмент для практики и обучения. Использование в ранкед/соревновательных режимах нарушает ToS GeoGuessr.

**Q: Не работает подключение?**
A: Убедитесь, что в параметрах запуска Steam **оба** флага:
```
--remote-debugging-port=34788 --remote-allow-origins=*
```
Порт 34788 выбран чтобы не конфликтовать с Chrome/VS Code (которые используют 9222).

---

## Лицензия

MIT
