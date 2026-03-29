# Podcast Translator

Автоматизированный pipeline для перевода подкастов с английского на русский язык с возможностью озвучивания.

## Возможности

- 🎥 Скачивание аудио с YouTube
- 🎤 Транскрибация с использованием faster-whisper (оптимизировано для CPU)
- 🌍 Перевод на русский язык с сохранением технических терминов
- 🔊 Генерация русской озвучки через Edge TTS
- 🤖 Автономный агент для Claude Code
- 🎙️ OpenClaw Skill для автоматического перевода

## Структура проекта

```
podcast-translator/
├── scripts/                    # Основные скрипты
│   ├── download_and_process.sh # Полный pipeline
│   ├── transcribe_cached.py    # Транскрибация (CPU-optimized)
│   ├── prepare_transcript.py   # Подготовка транскрипции
│   └── generate_tts.py         # Генерация TTS
├── agents/                     # Claude Code агенты
│   └── podcast-translator.md   # Автономный агент для перевода
├── skills/                     # Skills для разных платформ
│   ├── podcast-translator-skill/ # Claude skill для перевода
│   └── podcast-translator/      # OpenClaw skill (автоматический pipeline)
├── podcast-translator-skill.skill # Упакованный Claude skill
├── audio/                      # Сгенерированная озвучка
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

## Конфигурация

Все пути настроены в `scripts/download_and_process.sh`:
- `PROJECT_DIR="/home/clawd/work/podcast-translator"`
- `INPUT_DIR="$PROJECT_DIR/input"`
- `TRANSCRIPT_DIR="$PROJECT_DIR/transcripts"`
- `TRANSLATION_DIR="$PROJECT_DIR/translations"`
- `AUDIO_DIR="$PROJECT_DIR/audio"`

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

### 1. OpenClaw Skill (рекомендуется) 🎙️

Автоматический pipeline через OpenClaw skill. Просто отправь YouTube URL:

```
Переведи этот подкаст: https://www.youtube.com/watch?v=VIDEO_ID
```

Skill автоматически:
- Скачает аудио
- Транскрибирует
- Переведёт на русский
- Сгенерирует озвучку

**С выбором голоса:**
```
Переведи этот подкаст с женским голосом: https://www.youtube.com/watch?v=VIDEO_ID
```

Доступные голоса: Dmitry (мужской, по умолчанию), Svetlana (женский), Dariya (женский).

### 2. Claude Code Agent

Автономный агент для Claude Code расположен в `agents/podcast-translator.md`:

```
Используй podcast-translator агента для этого URL
```

Или просто:
```
Переведи этот подкаст: https://www.youtube.com/watch?v=VIDEO_ID
```

Агент спросит про голос и выполнит весь pipeline автономно.

### 3. Bash скрипт (полуавтоматический)

```bash
cd /home/clawd/work/podcast-translator
./scripts/download_and_process.sh "https://www.youtube.com/watch?v=VIDEO_ID"
```

Потребуется вручную перевести на шаге 4 используя podcast-translator skill.

### 4. Поэтапно (полный контроль)

**1. Скачать аудио**
```bash
yt-dlp -x --audio-format mp3 --audio-quality 0 -o input/podcast.mp3 "URL"
```

**2. Транскрибация**
```bash
python3 scripts/transcribe_cached.py input/podcast.mp3 transcripts/ small
```

**3. Подготовка перевода**
```bash
python3 scripts/prepare_transcript.py transcripts/podcast.txt translations/podcast_ready.txt
```

**4. Перевод** (с использованием skill или вручную)

Используй `podcast-translator` skill или переведи вручную.

**5. Генерация TTS**
```bash
# Голос по умолчанию (Dmitry - мужской)
python3 scripts/generate_tts.py translations/podcast_ru.txt audio/podcast.ru.mp3

# Женский голос (Svetlana)
python3 scripts/generate_tts.py translations/podcast_ru.txt audio/podcast.ru.mp3 ru-RU-SvetlanaNeural
```

## Формат файлов перевода

Pipeline создаёт два файла перевода:

**С таймкодами** (`{episode}_ru.txt`):
```
[00:00 - 00:05] Первый сегмент перевода
[00:05 - 00:10] Второй сегмент перевода
```

**Для TTS** (`{episode}_ru_tts.txt`):
```
Первый сегмент перевода. Второй сегмент перевода.
```

## Оптимизация для CPU

`transcribe_cached.py` оптимизирован для работы на Raspberry Pi ARM:
- `beam_size=1` (быстрее на CPU)
- `int8` квантизация
- Отключён VAD фильтр
- 4 CPU threads, 2 workers
- Прогресс-хартбит каждые 10 секунд

## Лицензия

MIT

## Интеграции

### OpenClaw Skill 🎙️

Автоматический skill для OpenClaw с полным pipeline:
- Распознаёт YouTube URLs и запросы на перевод
- Спавнит субагент для выполнения pipeline
- Поддерживает выбор голоса (Dmitry, Svetlana, Dariya)
- Возвращает результаты по готовности

Файл: `skills/podcast-translator/SKILL.md`

### Claude Code Agent

Автономный агент для Claude Code (`agents/podcast-translator.md`):
- Выполняет полный pipeline
- Поддерживает выбор голоса
- Возвращает детальную статистику

## Документация

- [AGENTS.md](AGENTS.md) - Документация по субагентам
- [VOICES.md](VOICES.md) - Сравнение голосов TTS
- [PROGRESS_FORMAT.md](PROGRESS_FORMAT.md) - Формат прогресс-вывода для CLI агентов

