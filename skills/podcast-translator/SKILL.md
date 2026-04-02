---
name: podcast-translator
description: "Translate YouTube podcasts from English to Russian with TTS generation. Downloads audio, transcribes, translates preserving timestamps, and generates Russian voiceover. Use when user sends a YouTube URL and asks to translate/translate to Russian/create Russian voiceover. Supports voice selection (Dmitry, Svetlana, Dariya). Works completely offline after download."
metadata:
  {
    "openclaw":
      {
        "emoji": "🎙️",
        "requires": { "bins": ["yt-dlp", "python3"] }
      }
  }
---

# Podcast Translator 🎙️

**Automatic English → Russian podcast translation with voiceover.**

Drop a YouTube link → get Russian translation + voiceover.

## Quick Start

When user asks to translate a podcast or sends a YouTube URL with translation request:

1. Detect voice preference from user message (if specified)
2. Spawn sub-agent with the full pipeline task
3. Reply: "🎙️ Processing podcast — I'll let you know when it's ready!"
4. Continue conversation (don't wait!)

**Voice Detection (automatic):**
- Default: `ru-RU-DmitryNeural` (male voice)
- "женский голос" / "female" / "Svetlana" / "Светлана" → `ru-RU-SvetlanaNeural`
- "Dariya" / "Дарья" → `ru-RU-DariyaNeural`
- No voice specified → use default (Dmitry)

## Full Workflow (Single Sub-Agent)

```python
sessions_spawn(
    task=f"""
## Podcast Translator: Process {youtube_url}

⚠️ CRITICAL: Do NOT install any software.
No pip, brew, curl, venv, or binary downloads.
If a tool is missing, STOP and report what's needed.

⚠️ CRITICAL: Print progress at each step in machine-readable format:
- STATUS: Step description
- HEARTBEAT: Progress updates
- SUCCESS: Step completed
- ERROR: Step failed

Run the COMPLETE pipeline — do not stop until all steps are done.

### Configuration
- PROJECT_DIR="{SKILL_DIR}"  # Auto-detected: points to skill installation directory
- Voice: {voice}  # "ru-RU-DmitryNeural", "ru-RU-SvetlanaNeural", or "ru-RU-DariyaNeural"

### Step 1: Download Audio
```bash
cd "$PROJECT_DIR"
echo "STATUS: Downloading audio from YouTube..."
yt-dlp -x --audio-format mp3 --audio-quality 0 \\
  -o "input/podcast_$(date +%Y%m%d_%H%M%S).mp3" \\
  "{youtube_url}"
```
Get the downloaded filename and note it.
Print: `STATUS: Downloaded audio: {filename}`

### Step 2: Transcribe to English
```bash
echo "STATUS: Starting transcription..."
python3 $PROJECT_DIR/scripts/transcribe_cached.py \\
  "$INPUT_FILE" \\
  "$PROJECT_DIR/transcripts/" \\
  small
```
Output: `transcripts/{name}.txt`
Print: `STATUS: Transcription complete: {segments} segments`

### Step 3: Prepare for Translation
```bash
echo "STATUS: Preparing transcript for translation..."
python3 $PROJECT_DIR/skills/podcast-translator/scripts/prepare_transcript.py \\
  "$TRANSCRIPT_FILE" \\
  "$PROJECT_DIR/translations/{basename}_ready.txt"
```
Output: `translations/{basename}_ready.txt`
Print: `STATUS: Prepared for translation`

### Step 4: Translate to Russian (TOKEN EFFICIENT)
```bash
echo "STATUS: Translating to Russian (this may take a few minutes)..."
echo "HEARTBEAT: Translation in progress..."
```

Read the prepared file and create ONE translation file:

**translations/{basename}_ru.txt** (with timestamps):
- Preserve all timestamps: `[00:00 - 00:05]`
- Format: `[timestamp] English text` → `[timestamp] Russian translation`
- Translate to Russian, keep technical terms in English (OpenAI, Anthropic, API, GPU, etc.)
- Remove metadata headers
- Each timestamped segment on its own line

Print: `STATUS: Translation complete: {word_count} words`

### Step 4.5: Extract TTS Text (SCRIPT - saves tokens!)
```bash
echo "STATUS: Extracting TTS text from translation..."
python3 $PROJECT_DIR/skills/podcast-translator/scripts/extract_tts_text.py \\
  "$PROJECT_DIR/translations/{basename}_ru.txt" \\
  "$PROJECT_DIR/translations/{basename}_ru_tts.txt"
```
Output: `translations/{basename}_ru_tts.txt` (clean Russian text, no timestamps)
Print: `SUCCESS: TTS text extracted`

### Step 5: Generate Russian TTS
```bash
echo "STATUS: Starting TTS generation..."
python3 $PROJECT_DIR/skills/podcast-translator/scripts/generate_tts.py \\
  "$PROJECT_DIR/translations/{basename}_ru_tts.txt" \\
  "$PROJECT_DIR/audio/{basename}.ru.mp3" \\
  "{voice}"
```
Output: `audio/{basename}.ru.mp3`
Print: `SUCCESS: TTS generation complete`

### Step 6: Create Output Manifest (CRITICAL for file delivery)

⚠️ CRITICAL: Create manifest file so main agent can find and send the files

```bash
MANIFEST_FILE="$PROJECT_DIR/translations/{basename}_manifest.txt"

cat > "$MANIFEST_FILE" << 'EOF'
===OPENCLAW_OUTPUTS_COMPLETE===
translation:translations/{basename}_ru.txt
tts_text:translations/{basename}_ru_tts.txt
audio:audio/{basename}.ru.mp3
transcript:transcripts/{basename}.txt
base_dir:$PROJECT_DIR
===OPENCLAW_OUTPUTS_END===
EOF

echo "===MANIFEST:$MANIFEST_FILE==="
```

### Report

Print in machine-readable format:
```
SUCCESS: Pipeline complete
STATUS: Original audio: input/{name}.mp3 ({size} MB)
STATUS: Transcript: transcripts/{name}.txt ({segments} segments)
STATUS: Translation (with timestamps): translations/{name}_ru.txt ({words} words)
STATUS: Translation (TTS-ready): translations/{name}_ru_tts.txt ({words} words)
STATUS: Russian audio: audio/{name}.ru.mp3 ({size} MB)
STATUS: Audio duration: {duration}
```

Provide summary in natural language:
1. What was processed
2. Files created with full paths
3. Statistics: audio duration, word count, file sizes
""",
    label="podcast-translator",
    runTimeoutSeconds=1800,
    cleanup="keep"
)
```

**After spawning, reply immediately:**
> 🎙️ Processing podcast — I'll let you know when it's ready!

Then continue the conversation. The sub-agent notification announces completion.

## Voice Selection

Available Russian voices:

| Voice | ID | Gender |
|-------|----|----|
| Dmitry | `ru-RU-DmitryNeural` | Male (default) |
| Svetlana | `ru-RU-SvetlanaNeural` | Female |
| Dariya | `ru-RU-DariyaNeural` | Female |

**Usage examples:**
- "Translate this podcast with female voice" → Use `ru-RU-SvetlanaNeural`
- "Translate with Dmitry" → Use `ru-RU-DmitryNeural`
- "Переведи этот подкаст" → Use default (`ru-RU-DmitryNeural`)
- "Озвучь женским голосом" → Use `ru-RU-SvetlanaNeural`

## Project Structure

```
/home/clawd/work/podcast-translator/
├── scripts/
│   ├── transcribe_cached.py    # Faster-whisper transcription
│   ├── prepare_transcript.py   # Prepare for translation
│   └── generate_tts.py         # Edge TTS generation
├── input/                       # Downloaded MP3 files
├── transcripts/                 # English transcripts
├── translations/                # Russian translations
└── audio/                       # Generated Russian audio
```

## Dependencies

**Required:**
- Python 3.x
- faster-whisper (transcription)
- edge-tts (TTS)
- yt-dlp (YouTube download)
- ffmpeg (audio processing)

**Install:**
```bash
pip install faster-whisper edge-tts yt-dlp --break-system-packages
```

## CPU Optimization

`transcribe_cached.py` is optimized for Raspberry Pi ARM:
- `beam_size=1` (faster on CPU)
- `int8` quantization
- 4 CPU threads, 2 workers
- Progress heartbeat every 10 seconds

## Translation Rules

- **Preserve timestamps** in `{basename}_ru.txt`
- **Remove timestamps** for TTS in `{basename}_ru_tts.txt`
- **Keep technical terms in English**: OpenAI, Anthropic, API, GPU, etc.
- **Remove artifacts**: Chinese characters, English fragments
- **Natural Russian prose**: flowing paragraphs
- **No metadata headers**: only translated content

## Output Files

1. **`{basename}_ru.txt`** — With timestamps for reference
   ```
   [00:00 - 00:05] Сегодня в подкасте обсуждаем OpenAI
   [00:05 - 00:10] и новые достижения в области ИИ
   ```

2. **`{basename}_ru_tts.txt`** — Without timestamps for TTS
   ```
   Сегодня в подкасте обсуждаем OpenAI и новые достижения в области ИИ.
   ```

3. **`{basename}.ru.mp3`** — Generated Russian audio

## Error Handling

If any step fails:
- Report which step failed
- Show error message
- Suggest next steps

Common errors:
- Missing dependencies → Install with pip
- Invalid URL → Check YouTube URL format
- Download failed → Check network connection
- Transcription timeout → Increase timeout for long audio
- TTS generation failed → Check Edge TTS installation

## Tips

- For long podcasts (>60 min), increase timeout to 3600s
- Dmitry voice works well for technical content
- Svetlana/Dariya voices work well for educational content
- Timestamps preserved for creating aligned transcripts or subtitles
- TTS generation takes time for long transcripts
