---
name: podcast-translator
description: "Translate YouTube podcasts from English to Russian with TTS generation. Downloads audio, transcribes, translates, and generates Russian voiceover. Use when user sends a YouTube URL and asks to translate/translate to Russian/create Russian voiceover. Supports voice selection (Dmitry, Svetlana, Dariya). Works completely offline after download."
metadata:
  {
    "openclaw":
      {
        "emoji": "🎙️",
        "requires": { "bins": ["yt-dlp", "python3"] }
      }
  }
---

# Podcast Translator

**Automatic English to Russian podcast translation with voiceover.**

Drop a YouTube link — get Russian translation + voiceover.

## Quick Start

When user asks to translate a podcast or sends a YouTube URL:

1. Detect voice preference from user message
2. Execute the full pipeline (see steps below)
3. Report results

**Voice Detection:**
- Default: `ru-RU-DmitryNeural` (male)
- "женский голос" / "female" / "Svetlana" → `ru-RU-SvetlanaNeural`
- "Dariya" / "Дарья" → `ru-RU-DariyaNeural`

## Pipeline

All commands run from `{SKILL_DIR}`.

### Step 1: Download Audio

```bash
cd {SKILL_DIR}
yt-dlp -x --audio-format mp3 --audio-quality 0 -o "input/podcast_$(date +%Y%m%d_%H%M%S).mp3" "{youtube_url}"
```

Note the downloaded filename. Set `INPUT_FILE` to the full path.

### Step 2: Transcribe (with chunking for long videos)

Check duration and chunk if needed:

```bash
python3 {SKILL_DIR}/scripts/chunk_audio.py "$INPUT_FILE"
```

**If output has `"chunking": true`:** Audio is long, chunks created.

```bash
python3 {SKILL_DIR}/scripts/transcribe_chunk.py --all {videoId}
```

Then assemble chunks:

```bash
python3 {SKILL_DIR}/scripts/assemble_chunks.py {videoId}
```

**If output has `"chunking": false`:** Audio is short, transcribe directly.

```bash
python3 {SKILL_DIR}/scripts/transcribe_cached.py "$INPUT_FILE" {SKILL_DIR}/transcripts/ small
```

Output: `transcripts/{name}.txt`

### Step 3: Prepare for Translation

```bash
python3 {SKILL_DIR}/scripts/prepare_transcript.py "{SKILL_DIR}/transcripts/{name}.txt" "{SKILL_DIR}/translations/{name}_ready.txt"
```

### Step 4: Translate EN→RU (LLM in-context)

Read `{SKILL_DIR}/translations/{name}_ready.txt` and translate to Russian:

- Write clean Russian text directly to `{SKILL_DIR}/translations/{name}_ru_tts.txt`
- Do NOT include timestamps
- Do NOT include chunk markers like `[chunk N/M]` or `[часть N/M]`
- Preserve technical terms in English: OpenAI, GPU, API, etc.
- Remove unspeakable characters: emoji, Chinese/Japanese/Korean, special symbols
- Write natural flowing Russian text with proper punctuation for TTS

Do NOT create a separate `_ru.txt` file with timestamps. Write directly to `_ru_tts.txt`.

If translation is too long for one pass, split into parts and append to the same `_ru_tts.txt` file.

### Step 5: Generate TTS

```bash
python3 {SKILL_DIR}/scripts/generate_tts.py "{SKILL_DIR}/translations/{name}_ru_tts.txt" "{SKILL_DIR}/audio/{name}.ru.mp3" "{voice}"
```

### Step 6: Create Manifest

```bash
MANIFEST_FILE="{SKILL_DIR}/translations/{name}_manifest.txt"
cat > "$MANIFEST_FILE" << 'EOF'
===OPENCLAW_OUTPUTS_COMPLETE===
translation:translations/{name}_ru_tts.txt
audio:audio/{name}.ru.mp3
transcript:transcripts/{name}.txt
base_dir:{SKILL_DIR}
===OPENCLAW_OUTPUTS_END===
EOF
```

### Report

```
🎙️ Подкаст готов!

Что получилось:
• Оригинал: ~{duration} минут ({title})
• Перевод: {words} слов
• Русская озвучка: ~{tts_duration}, голос {voice_name}

Файлы:
• Текст для озвучки: translations/{name}_ru_tts.txt
• 🎧 Аудио: audio/{name}.ru.mp3 ({size} MB)
```

## Project Structure

```
{SKILL_DIR}/
├── scripts/
│   ├── chunk_audio.py          # Split long audio into chunks
│   ├── transcribe_cached.py    # Short video transcription
│   ├── transcribe_chunk.py     # Chunk transcription (--all flag)
│   ├── assemble_chunks.py     # Assemble chunks (no chunk headers)
│   ├── prepare_transcript.py  # Prepare for translation
│   ├── generate_tts.py        # TTS with chunking + ffmpeg merge
│   ├── extract_tts_text.py   # Extract TTS text from translation
│   └── log_helper.py          # Progress logging helpers
├── input/                      # Downloaded MP3 files
├── transcripts/                # English transcripts
├── translations/               # Russian translations
└── audio/                       # Generated Russian audio
```

## Translation Rules

- Write directly to `_ru_tts.txt` — clean Russian text, no timestamps
- Remove ALL bracket markers: `[chunk N/M]`, `[часть N/M]`, `[MM:SS - MM:SS]`
- Keep technical terms in English: OpenAI, GPU, API, etc.
- Remove unspeakable characters: emoji, CJK, special symbols
- Natural flowing Russian prose with proper sentence boundaries

## Error Handling

If any step fails:
- Report which step failed
- Show error message
- Mark video as failed in queue (if using queue system)