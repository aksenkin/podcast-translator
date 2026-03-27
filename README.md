# Podcast Translator

Автоматизированный pipeline для перевода подкастов с английского на русский язык с возможностью озвучивания.

## Возможности

- 🎥 Скачивание аудио с YouTube
- 🎤 Транскрибация с использованием faster-whisper (оптимизировано для CPU)
- 🌍 Перевод на русский язык с сохранением технических терминов
- 🔊 Генерация русской озвучки через Edge TTS

## Структура проекта

```
podcast-translator/
├── scripts/                    # Основные скрипты
│   ├── download_and_process.sh # Полный pipeline
│   ├── transcribe_cached.py    # Транскрибация (CPU-optimized)
│   ├── prepare_transcript.py   # Подготовка транскрипции
│   └── generate_tts.py         # Генерация TTS
├── skills/                     # Claude Skills
│   └── podcast-translator-skill/ # Skill для перевода
├── podcast-translator-skill.skill # Упакованный skill
├── audio/                      # Сгенерированная озвучка
├── input/                      # Скачанные MP3 файлы
├── transcripts/                # Транскрибация (английский)
└── translations/               # Переводы (русский)
```

## Использование

### Полный pipeline (bash скрипт)

```bash
cd /home/clawd/work/podcast-translator
./scripts/download_and_process.sh "https://www.youtube.com/watch?v=VIDEO_ID"
```

### Поэтапно (вручную)

1. **Скачать аудио**
   ```bash
   yt-dlp -x --audio-format mp3 --audio-quality 0 -o input/podcast.mp3 "URL"
   ```

2. **Транскрибация**
   ```bash
   python3 scripts/transcribe_cached.py input/podcast.mp3 transcripts/ small
   ```

3. **Подготовка перевода**
   ```bash
   python3 scripts/prepare_transcript.py transcripts/podcast.txt translations/podcast_ready.txt
   ```

4. **Перевод** (с использованием skill или вручную)
   ```bash
   # Использовать podcast-translator skill
   # Или перевести вручную
   ```

5. **Генерация TTS**
   ```bash
   python3 scripts/generate_tts.py translations/podcast_ru.txt audio/podcast.ru.mp3
   ```

## Зависимости

- Python 3.x
- faster-whisper
- edge-tts
- yt-dlp
- ffmpeg

## Установка зависимостей

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

## Способы использования

### 1. Автономный субагент (рекомендуется)

Субагент установлен в `~/.claude/agents/podcast-translator.md`

Просто попроси:
```
Переведи этот подкаст: https://www.youtube.com/watch?v=VIDEO_ID
```

Или явно укажи:
```
Используй podcast-translator агента для этого URL
```

Субагент выполнит весь pipeline автоматически и вернёт результаты.

### 2. Bash скрипт (полуавтоматический)

```bash
cd /home/clawd/work/podcast-translator
./scripts/download_and_process.sh "https://www.youtube.com/watch?v=VIDEO_ID"
```

Тебё понадобится вручную перевести на шаге 4 используя podcast-translator skill.

### 3. Поэтапно (полный контроль)

См. ниже "Поэтапное использование".

## Skill для перевода

Проект включает в себя `podcast-translator-skill` для автоматического перевода:

- Читает файлы `{episode}_ready.txt` с таймкодами
- Переводит на русский, сохраняя технические термины
- Убирает таймкоды и метаданные
- Создаёт чистый текст для TTS

## Оптимизация для CPU

`transcribe_cached.py` оптимизирован для работы на Raspberry Pi ARM:
- `beam_size=1` (быстрее на CPU)
- `int8` квантизация
- Отключён VAD фильтр
- 4 CPU threads, 2 workers
- Прогресс-хартбит каждые 10 секунд

## Лицензия

MIT

## Документация

- [AGENTS.md](AGENTS.md) - Документация по субагентам

