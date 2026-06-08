# Заметки (Notes App)

Мобильное приложение для Android — менеджер заметок с локальной базой данных.

## Возможности

- Создание заметок с заголовком и содержанием
- Просмотр списка всех сохранённых заметок
- Просмотр отдельной заметки
- Редактирование существующих заметок
- Удаление заметок с подтверждением
- Анимированный экран загрузки (Lottie)
- Адаптивная иконка приложения

## Экраны

1. **Экран загрузки** — анимация Lottie с названием приложения
2. **Список заметок** — все сохранённые заметки с превью
3. **Добавление заметки** — форма ввода заголовка и содержания
4. **Просмотр/редактирование** — полное отображение заметки с возможностью редактирования и удаления

## Технологии

| Технология | Назначение |
|---|---|
| Kotlin | Язык программирования |
| Jetpack Compose | UI фреймворк |
| Room Database | Локальная база данных |
| Navigation Compose | Навигация между экранами |
| Lottie | Анимации |
| Material 3 | Дизайн-система |
| Coroutines + Flow | Асинхронность |

## Структура проекта

```
app/src/main/java/com/maxsite/notes/
├── data/
│   ├── Note.kt              — Entity (таблица заметок)
│   ├── NoteDao.kt           — Data Access Object
│   ├── NotesDatabase.kt     — Room Database
│   └── NotesRepository.kt   — Репозиторий
├── ui/
│   ├── navigation/
│   │   ├── Screen.kt        — Маршруты навигации
│   │   └── NavGraph.kt      — Граф навигации
│   ├── screens/
│   │   ├── SplashScreen.kt  — Экран загрузки
│   │   ├── NotesListScreen.kt — Список заметок
│   │   ├── AddNoteScreen.kt — Добавление заметки
│   │   ├── ViewNoteScreen.kt — Просмотр/редактирование
│   │   └── NotesViewModel.kt — ViewModel
│   └── theme/
│       ├── Color.kt         — Цветовая палитра
│       └── Theme.kt         — Тема приложения
├── MainActivity.kt
└── NotesApplication.kt
```

## Сборка

Требования:
- Android Studio Hedgehog (2023.1.1) или новее
- JDK 17
- Android SDK 34

```bash
./gradlew assembleDebug
```

## Установка

```bash
./gradlew installDebug
```
