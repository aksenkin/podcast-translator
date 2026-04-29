# Podcast Translator

Автоматизированный pipeline для перевода подкастов с английского на русский язык с возможностью озвучивания.

**Читать на других языках:** [English](README.md)

## Возможности

- Скачивание аудио с YouTube
- Транскрибация с использованием faster-whisper (оптимизировано для CPU, чанки для длинных видео)
- Перевод на русский язык с сохранением технических терминов
- Генерация русской озвучки через Edge TTS
- Автономный агент для Claude Code
- OpenClaw Skill для автоматического перевода
- Система очереди с cron-обработкой

## Структура проекта

```
podcast-translator/
├── scripts/                    # Основные скрипты
│   ├── chunk_audio.py          # Разделение длинного аудио на чанки
│   ├── transcribe_cached.py   # Транскрибация коротких видео (CPU-optimized)
│   ├── transcribe_chunk.py    # Транскрибация чанков (--all загружает модель один раз)
│   ├── assemble_chunks.py     # Сборка чанков в один транскрипт (без заголовков чанков)
│   ├── prepare_transcript.py  # Подготовка транскрипции для перевода
│   ├── generate_tts.py        # Генерация TTS
│   ├── extract_tts_text.py   # Извлечение TTS текста из перевода
│   ├── download_and_process.sh # Полный pipeline
│   └── log_helper.py          # Вспомогательные функции логирования
├── agents/                     # Claude Code агенты
│   └── podcast-translator.md  # Автономный агент для перевода
├── skills/                     # Skills для разных платформ
│   ├── podcast-translator-skill/ # Claude skill для перевода
│   └── podcast-translator/      # OpenClaw skill (автоматический pipeline)
├── podcast-translator-skill.skill # Упакованный Claude skill
├── channel_monitor.py          # Мониторинг YouTube каналов
├── queue_manager.py            # Управление очередью
├── run_pipeline.py             # Запуск pipeline с PID-lock
├── process-queue.py            # Обработчик очереди (--translate-only fallback)
├── audio/                      # Сгенерированная озвучка
├── chunks/                     # Аудио чанки и транскрипты
├── input/                      # Скачанные MP3 файлы
├── transcripts/                # Транскрибация (английский)
└── translations/               # Переводы (русский)
```

## Зависимости

- Python 3.x
- faster-whisper
- edge-tts
- yt-dlp
- ffmpeg

### Установка

```bash
pip install faster-whisper edge-tts yt-dlp --break-system-packages
```

## Голоса для TTS

### Доступные голоса

- **ru-RU-DmitryNeural** - Мужской голос (по умолчанию)
- **ru-RU-SvetlanaNeural** - Женский голос
- **ru-RU-DariyaNeural** - Женский голос

### Использование

**Через CLI:**
```bash
# По умолчанию (Dmitry)
python3 scripts/generate_tts.py input.txt output.mp3

# Женский голос (Svetlana)
python3 scripts/generate_tts.py input.txt output.mp3 ru-RU-SvetlanaNeural

# Женский голос (Dariya)
python3 scripts/generate_tts.py input.txt output.mp3 ru-RU-DariyaNeural
```

**С агентом/skill:**
```
Переведи этот подкаст с женским голосом: [URL]
```

Подробнее: [VOICES.md](VOICES.md)

## Способы использования

### 1. OpenClaw Skill (рекомендуется)

Автоматический pipeline через OpenClaw skill. Просто отправь YouTube URL:

```
Переведи этот подкаст: https://www.youtube.com/watch?v=VIDEO_ID
```

Skill автоматически:
- Скачает аудио
- Транскрибирует (с чанкингом для длинных видео)
- Переведёт на русский
- Сгенерирует озвучку

### 2. Claude Code Agent

Автономный агент для Claude Code расположен в `agents/podcast-translator.md`:

```
Используй podcast-translator агента для этого URL
```

### 3. Поэтапно (полный контроль)

**1. Скачать аудио**
```bash
yt-dlp -x --audio-format mp3 --audio-quality 0 -o "input/{videoId}.mp3" "URL"
```

**2. Проверить длительность и разбить на чанки**
```bash
python3 scripts/chunk_audio.py "input/{videoId}.mp3"
```

Если `chunking: true`, перейти к шагу 3a. Если `chunking: false`, транскрибировать напрямую:
```bash
python3 scripts/transcribe_cached.py "input/{videoId}.mp3" transcripts/ small
```

**3a. Транскрибировать все чанки** (модель загружается один раз):
```bash
python3 scripts/transcribe_chunk.py --all {videoId}
```

**3b. Собрать чанки в один транскрипт:**
```bash
python3 scripts/assemble_chunks.py {videoId}
```

**4. Подготовка перевода**
```bash
python3 scripts/prepare_transcript.py "transcripts/{videoId}.txt" "translations/{videoId}_ready.txt"
```

**5. Перевод** (с использованием skill или вручную)

**6. Генерация TTS**
```bash
python3 scripts/generate_tts.py "translations/{videoId}_ru_tts.txt" "audio/{videoId}.ru.mp3"
```

## Чанковая транскрибация

Для видео длиннее 5 минут pipeline автоматически разбивает аудио на чанки:

1. `chunk_audio.py` разбивает аудио на 5-минутные чанки
2. `transcribe_chunk.py --all {videoId}` загружает модель whisper один раз и транскрибирует все чанки последовательно
3. `assemble_chunks.py {videoId}` собирает чанки в один транскрипт (без заголовков чанков)
4. Очистка удаляет аудио чанки и файлы транскриптов

**Ключевые особенности:**
- Флаг `--all`: загружает модель один раз (~2с из кэша), обрабатывает все чанки без пауз
- PID-lock: предотвращает параллельную транскрибацию
- `os.nice(10)`: снижает приоритет CPU для фоновой обработки
- Кэш модели: загрузка из локального кэша HuggingFace за ~2 секунды

## Оптимизация для CPU

Все скрипты транскрибации оптимизированы для Raspberry Pi ARM:
- `beam_size=1` (быстрее на CPU)
- `int8` квантизация
- Отключён VAD фильтр
- 4 CPU threads, 2 workers
- Прогресс-хартбит каждые 10 секунд
- `os.nice(10)` для фонового приоритета
- PID-lock для предотвращения параллельных процессов whisper

---

## Автоматизированная система очереди

Podcast-translator включает полностью автоматизированную систему обработки видео через cron задачи OpenClaw.

### Обзор архитектуры

```
┌─────────────────────────────────────────────────────────────────┐
│                Cron Задача #1 (08:30 ежедневно)               │
│                Мониторинг YouTube каналов                      │
│                                                                 │
│  Проверка каналов → Добавление новых видео в очередь            │
│  Затем запуск: python3 run_pipeline.py                          │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ↓
                    ┌──────────────┐
                    │   Очередь    │
                    │   (JSON)     │
                    │              │
                    │ pending: 3   │
                    └──────────────┘
                           │
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│                Cron Задача #2 (08:40 ежедневно)                 │
│                Обработчик очереди (agentTurn)                   │
│                                                                 │
│  Для каждого видео:                                             │
│  1. Получить следующее видео из очереди                         │
│  2. Скачать аудио (yt-dlp)                                      │
│  3. Разбить на чанки и транскрибировать (--all)                 │
│  4. Собрать чанки (без заголовков чанков)                      │
│  5. Подготовить транскрипт                                      │
│  6. Перевести EN→RU (LLM in-context)                           │
│  7. Сгенерировать TTS (edge-tts)                                │
│  8. Отправить результат в Telegram                               │
│  9. Пометить как завершённое/ошибку, перейти к следующему        │
└─────────────────────────────────────────────────────────────────┘
```

### Компоненты

#### 1. Мониторинг YouTube каналов (Cron #1)

**Расписание:** Ежедневно в 08:30 (Europe/Minsk)
**Скрипт:** `channel_monitor.py`

Проверяет настроенные YouTube каналы, добавляет новые видео в очередь, затем запускает обработчик очереди через `run_pipeline.py`.

#### 2. Обработчик очереди (Cron #2)

**Расписание:** Ежедневно в 08:40 (Europe/Minsk)
**Тип:** `agentTurn` payload (LLM выполняет шаги pipeline через exec)
**Агент:** `main` (с загруженным skill `podcast-translator`)
**Таймаут:** 2 часа (7200с)

Использует OpenClaw `agentTurn` для выполнения pipeline. Агент получает подробный payload с описанием каждого шага и выполняет их последовательно. При ошибке помечает видео как failed и переходит к следующему.

**Ключевые особенности:**
- Флаг `--all` для чанковой транскрибации (модель загружается один раз)
- Нет заголовков чанков в собранном транскрипте
- PID-lock предотвращает параллельную транскрибацию
- Stale video watchdog возвращает застрявшие видео в pending
- `{SKILL_DIR}` автоматически подставляется OpenClaw
- Telegram уведомления для каждого видео (успех или ошибка)

#### 3. Менеджер очереди

**Скрипт:** `queue_manager.py`

**Команды:**
```bash
python3 queue_manager.py add VIDEO_ID "Название" "Канал"  # Добавить видео
python3 queue_manager.py next                               # Следующее видео
python3 queue_manager.py status                             # Статистика очереди
python3 queue_manager.py complete VIDEO_ID                  # Пометить завершённым
python3 queue_manager.py fail VIDEO_ID "Ошибка"             # Пометить ошибкой
python3 queue_manager.py reset-stale                        # Вернуть застрявшие видео
```

**Stale video watchdog:** `reset-stale` проверяет, находится ли видео в состоянии "processing" более 30 минут без живого процесса транскрибации. Если да, возвращает видео в pending.

#### 4. Запускатор pipeline

**Скрипт:** `run_pipeline.py`

Запускает cron задачу queue-processor с PID-lock контролем параллелизма. Ищет cron задачу по имени (`queue-processor`) вместо захардкоженного ID.

```bash
python3 run_pipeline.py              # Запустить queue-processor
python3 run_pipeline.py --status     # Проверить, запущен ли pipeline
python3 run_pipeline.py --force      # Принудительный запуск
```

### Конфигурация OpenClaw Skill

Skill `podcast-translator` загружается через источник `openclaw-workspace` (прямой путь, не symlink). Для добавления в агент:

```json
{
  "id": "main",
  "name": "main",
  "skills": ["podcast-translator"]
}
```

**Важно:** Не создавайте symlink из `~/.openclaw/skills/podcast-translator` в `~/.openclaw/workspace/skills/podcast-translator`. OpenClaw gateway отклонит symlink, указывающий за пределы корневой директории (`symlink-escape`). Skill автоматически обнаруживается через источник `openclaw-workspace`.

### Ежедневный рабочий процесс

**08:30** - Мониторинг YouTube каналов
- Проверка настроенных каналов
- Добавление новых видео в очередь
- Запуск обработчика очереди

**08:40** - Обработчик очереди
- Обработка всех pending видео последовательно
- Скачивание, транскрибация (с чанкингом), перевод, генерация TTS
- Отправка Telegram уведомлений для каждого видео
- Отправка итоговой сводки

### Мониторинг

**Статистика очереди:**
```bash
python3 queue_manager.py status
```

**Проверка блокировки pipeline:**
```bash
python3 run_pipeline.py --status
```

**Логи обработки видео:**
```bash
ls -lt logs/
cat logs/{videoId}.log
```

**Логи транскрибации:**
```bash
cat logs/{videoId}.log | grep TRANSCRIBE
```

### Ручное тестирование

**Тест мониторинга каналов:**
```bash
cd /home/clawd/.openclaw/workspace/skills/podcast-translator
python3 channel_monitor.py --videos-per-channel 3
```

**Тест обработчика очереди:**
```bash
python3 run_pipeline.py
```

**Добавить видео вручную:**
```bash
python3 queue_manager.py add VIDEO_ID "Название" "Канал"
```

**Сбросить застрявшие видео:**
```bash
python3 queue_manager.py reset-stale
```

---

## Лицензия

MIT

## Документация

- [AGENTS.md](AGENTS.md) - Документация по субагентам
- [VOICES.md](VOICES.md) - Сравнение голосов TTS
- [PROGRESS_FORMAT.md](PROGRESS_FORMAT.md) - Формат прогресс-вывода для CLI агентов
- [CLAUDE.md](CLAUDE.md) - Инструкции для Claude Code