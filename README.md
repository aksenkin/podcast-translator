# Podcast Translator

Automated pipeline for translating YouTube podcasts from English to Russian with Russian voiceover generation.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Read in other languages:** [Русский](README.ru.md)

## Features

- Download audio from YouTube
- Transcribe using faster-whisper (CPU-optimized, chunk-based for long videos)
- Translate to Russian while preserving technical terms
- Generate Russian voiceover via Edge TTS
- Autonomous agent for Claude Code
- OpenClaw Skill for automatic translation
- Queue system with cron-based processing

## Project Structure

```
podcast-translator/
├── scripts/                    # Core scripts
│   ├── chunk_audio.py          # Split long audio into chunks
│   ├── transcribe_cached.py   # Short video transcription (CPU-optimized)
│   ├── transcribe_chunk.py    # Chunk transcription (--all flag loads model once)
│   ├── assemble_chunks.py     # Assemble chunk transcripts (no chunk headers)
│   ├── prepare_transcript.py  # Transcript preparation for translation
│   ├── generate_tts.py        # TTS generation
│   ├── extract_tts_text.py   # Extract TTS text from translation
│   ├── download_and_process.sh # Full pipeline
│   └── log_helper.py          # Progress logging helpers
├── agents/                     # Claude Code agents
│   └── podcast-translator.md  # Autonomous translation agent
├── skills/                     # Skills for different platforms
│   ├── podcast-translator-skill/ # Claude translation skill
│   └── podcast-translator/      # OpenClaw skill (automatic pipeline)
├── podcast-translator-skill.skill # Packaged Claude skill
├── channel_monitor.py          # YouTube channel monitor
├── queue_manager.py            # Queue state management
├── run_pipeline.py             # Pipeline launcher with PID-lock
├── process-queue.py            # Queue processor (--translate-only fallback)
├── audio/                      # Generated voiceovers
├── chunks/                     # Audio chunks and transcripts
├── input/                      # Downloaded MP3 files
├── transcripts/                # Transcriptions (English)
└── translations/               # Translations (Russian)
```

## Dependencies

- Python 3.x
- faster-whisper
- edge-tts
- yt-dlp
- ffmpeg
- deno (optional, recommended for yt-dlp)

### Installation

**Python dependencies:**
```bash
pip install faster-whisper edge-tts yt-dlp --break-system-packages
```

**Deno (optional but recommended):**
```bash
curl -fsSL https://deno.land/install.sh | sh
```

After installation, restart your terminal or add Deno to PATH:
```bash
export PATH="$HOME/.deno/bin:$PATH"
```

## TTS Voices

### Available Voices

- **ru-RU-DmitryNeural** - Male voice (default)
- **ru-RU-SvetlanaNeural** - Female voice
- **ru-RU-DariyaNeural** - Female voice

### Usage

**Via CLI:**
```bash
# Default (Dmitry)
python3 scripts/generate_tts.py input.txt output.mp3

# Female voice (Svetlana)
python3 scripts/generate_tts.py input.txt output.mp3 ru-RU-SvetlanaNeural

# Female voice (Dariya)
python3 scripts/generate_tts.py input.txt output.mp3 ru-RU-DariyaNeural
```

**With agent/skill:**
```
Translate this podcast with a female voice: [URL]
```

See: [VOICES.md](VOICES.md)

## Usage Methods

### 1. OpenClaw Skill (Recommended)

Automatic pipeline via OpenClaw skill. Just send a YouTube URL:

```
Translate this podcast: https://www.youtube.com/watch?v=VIDEO_ID
```

The skill automatically:
- Downloads audio
- Transcribes (with chunking for long videos)
- Translates to Russian
- Generates voiceover

### 2. Claude Code Agent

Autonomous agent for Claude Code located at `agents/podcast-translator.md`:

```
Use the podcast-translator agent for this URL
```

### 3. Step-by-Step (Full Control)

**1. Download audio**
```bash
yt-dlp -x --audio-format mp3 --audio-quality 0 -o "input/{videoId}.mp3" "URL"
```

**2. Check duration and chunk if needed**
```bash
python3 scripts/chunk_audio.py "input/{videoId}.mp3"
```

If `chunking: true`, go to step 3a. If `chunking: false`, transcribe directly:
```bash
python3 scripts/transcribe_cached.py "input/{videoId}.mp3" transcripts/ small
```

**3a. Transcribe all chunks** (model loads once, processes sequentially):
```bash
python3 scripts/transcribe_chunk.py --all {videoId}
```

**3b. Assemble chunks into single transcript:**
```bash
python3 scripts/assemble_chunks.py {videoId}
```

**4. Prepare for translation**
```bash
python3 scripts/prepare_transcript.py "transcripts/{videoId}.txt" "translations/{videoId}_ready.txt"
```

**5. Translate** (using skill or manually)

**6. Generate TTS**
```bash
python3 scripts/generate_tts.py "translations/{videoId}_ru_tts.txt" "audio/{videoId}.ru.mp3"
```

## Chunk-Based Transcription

For videos longer than 5 minutes, the pipeline automatically splits audio into chunks:

1. `chunk_audio.py` splits audio into 5-minute chunks
2. `transcribe_chunk.py --all {videoId}` loads the whisper model once and transcribes all chunks sequentially
3. `assemble_chunks.py {videoId}` assembles chunk transcripts into a single file (without chunk headers)
4. Cleanup deletes chunk audio and transcript files

**Key features:**
- `--all` flag: loads model once (~2s from cache), processes all chunks without gaps
- PID-lock: prevents parallel transcription processes
- `os.nice(10)`: lowers CPU priority for background processing
- Model cache: loads from local HuggingFace cache in ~2 seconds

## CPU Optimization

All transcription scripts are optimized for Raspberry Pi ARM:
- `beam_size=1` (faster on CPU)
- `int8` quantization
- VAD filter disabled
- 4 CPU threads, 2 workers
- Progress heartbeat every 10 seconds
- `os.nice(10)` for background priority
- PID-lock to prevent parallel whisper processes

---

## Automated Queue Processing System

The podcast-translator includes a fully automated system for processing YouTube videos via OpenClaw cron jobs.

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                   Cron Job #1 (08:30 daily)                     │
│                YouTube Video Collector                          │
│                                                                 │
│  Check channels → Add new videos to queue                      │
│  Then trigger: python3 run_pipeline.py                          │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ↓
                    ┌──────────────┐
                    │   Queue      │
                    │   (JSON)     │
                    │              │
                    │ pending: 3   │
                    └──────────────┘
                           │
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│                Cron Job #2 (08:40 daily)                         │
│                  Queue Processor (agentTurn)                    │
│                                                                 │
│  For each video:                                                │
│  1. Get next pending video                                      │
│  2. Download audio (yt-dlp)                                     │
│  3. Chunk & transcribe (--all, model loads once)                │
│  4. Assemble chunks (no chunk headers)                          │
│  5. Prepare transcript                                          │
│  6. Translate EN→RU (LLM in-context)                           │
│  7. Generate TTS (edge-tts)                                     │
│  8. Send result via Telegram                                     │
│  9. Mark complete/failed, continue to next video                │
└─────────────────────────────────────────────────────────────────┘
```

### Components

#### 1. YouTube Video Collector (Cron Job #1)

**Schedule:** Daily at 08:30 (Europe/Minsk)
**Script:** `channel_monitor.py`

Monitors configured YouTube channels, adds new videos to queue, then triggers the queue processor via `run_pipeline.py`.

**Configuration:** `youtube-channels.json`

#### 2. Queue Processor (Cron Job #2)

**Schedule:** Daily at 08:40 (Europe/Minsk)
**Type:** `agentTurn` payload (LLM executes pipeline steps via exec)
**Agent:** `main` (with `podcast-translator` skill loaded)
**Timeout:** 2 hours (7200s)

Uses OpenClaw's `agentTurn` to execute the pipeline. The agent receives a detailed payload describing each step and executes them sequentially. On failure, marks the video as failed and continues to the next video.

**Key features:**
- `--all` flag for chunk transcription (model loads once)
- No chunk headers in assembled transcripts
- PID-lock prevents concurrent transcription
- Stale video watchdog returns stuck processing videos to pending
- `{SKILL_DIR}` auto-substituted by OpenClaw for skill directory path
- Telegram delivery for success/failure notifications

#### 3. Queue Manager

**Script:** `queue_manager.py`

**Commands:**
```bash
python3 queue_manager.py add VIDEO_ID "Title" "Channel"    # Add video
python3 queue_manager.py next                               # Get next pending
python3 queue_manager.py status                             # Show queue stats
python3 queue_manager.py complete VIDEO_ID                  # Mark done
python3 queue_manager.py fail VIDEO_ID "Error message"     # Mark failed
python3 queue_manager.py reset-stale                        # Return stuck videos to pending
```

**Stale video watchdog:** `reset-stale` checks if a video has been in "processing" state for more than 30 minutes with no live transcription process. If so, it returns the video to pending.

#### 4. Pipeline Launcher

**Script:** `run_pipeline.py`

Triggers the queue-processor cron job with PID-lock concurrency control. Prevents concurrent runs. Looks up the cron job by name (`queue-processor`) instead of hardcoded ID.

```bash
python3 run_pipeline.py              # Trigger queue-processor
python3 run_pipeline.py --status     # Check if pipeline is running
python3 run_pipeline.py --force      # Force run even if lock exists
```

### OpenClaw Skill Configuration

The `podcast-translator` skill is loaded via the `openclaw-workspace` source (direct path, not symlink). To add it to an agent:

```json
{
  "id": "main",
  "name": "main",
  "skills": ["podcast-translator"]
}
```

**Important:** Do not create a symlink from `~/.openclaw/skills/podcast-translator` to `~/.openclaw/workspace/skills/podcast-translator`. OpenClaw's gateway will reject symlinks that resolve outside their configured root (`symlink-escape` security check). The skill is automatically discoverable via the `openclaw-workspace` source.

### Cron Job Configuration

Cron jobs are configured in `~/.openclaw/cron/jobs.json` with `agentTurn` payload type.

**Queue Processor job** (key fields):
- `agentId`: `"main"`
- `sessionTarget`: `"isolated"`
- `schedule`: `"40 8 * * *"` (daily at 08:40)
- `timeoutSeconds`: 7200
- Payload contains detailed step-by-step pipeline instructions

**YouTube Collector job** (key fields):
- `sessionTarget`: `"main"`
- `schedule`: `"30 8 * * *"` (daily at 08:30)
- After collecting videos, triggers `run_pipeline.py` to start processing

### Daily Workflow

**08:30** - YouTube Video Collector runs
- Checks configured YouTube channels
- Adds new videos to queue
- Triggers queue processor

**08:40** - Queue Processor runs
- Processes all pending videos sequentially
- Downloads, transcribes (with chunking), translates, generates TTS
- Sends Telegram notification for each video (success or failure)
- Sends final summary

### Monitoring

**Check queue status:**
```bash
python3 queue_manager.py status
```

**Check pipeline lock:**
```bash
python3 run_pipeline.py --status
```

**View video processing logs:**
```bash
ls -lt logs/
cat logs/{videoId}.log
```

**View transcription logs:**
```bash
cat logs/{videoId}.log | grep TRANSCRIBE
```

### Manual Testing

**Test YouTube Video Collector:**
```bash
cd /home/clawd/.openclaw/workspace/skills/podcast-translator
python3 channel_monitor.py --videos-per-channel 3
```

**Test Queue Processor:**
```bash
python3 run_pipeline.py
```

**Add video manually:**
```bash
python3 queue_manager.py add VIDEO_ID "Title" "Channel"
```

**Reset stuck videos:**
```bash
python3 queue_manager.py reset-stale
```

---

## License

MIT

## Documentation

- [AGENTS.md](AGENTS.md) - Subagent documentation
- [VOICES.md](VOICES.md) - TTS voice comparison
- [PROGRESS_FORMAT.md](PROGRESS_FORMAT.md) - Progress output format for CLI agents
- [CLAUDE.md](CLAUDE.md) - Claude Code project instructions