# Podcast Translator

Automated pipeline for translating YouTube podcasts from English to Russian with Russian voiceover generation.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Read in other languages:** [Русский](README.ru.md)

## Features

- 🎥 Download audio from YouTube
- 🎤 Transcribe using faster-whisper (CPU-optimized)
- 🌍 Translate to Russian while preserving technical terms
- 🔊 Generate Russian voiceover via Edge TTS
- 🤖 Autonomous agent for Claude Code
- 🎙️ OpenClaw Skill for automatic translation

## Project Structure

```
podcast-translator/
├── scripts/                    # Core scripts
│   ├── download_and_process.sh # Full pipeline
│   ├── transcribe_cached.py    # Transcription (CPU-optimized)
│   ├── prepare_transcript.py   # Transcript preparation
│   └── generate_tts.py         # TTS generation
├── agents/                     # Claude Code agents
│   └── podcast-translator.md   # Autonomous translation agent
├── skills/                     # Skills for different platforms
│   ├── podcast-translator-skill/ # Claude translation skill
│   └── podcast-translator/      # OpenClaw skill (automatic pipeline)
├── podcast-translator-skill.skill # Packaged Claude skill
├── audio/                      # Generated voiceovers
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

### Installation

```bash
pip install faster-whisper edge-tts yt-dlp --break-system-packages
```

## Configuration

All paths are configured in `scripts/download_and_process.sh` with flexible options:

**Default directory:** `~/podcast-translator`

**Specify custom directory:**
- Via parameter: `./scripts/download_and_process.sh --destination-dir /path/to/project URL`
- Via environment variable: `PODCAST_TRANSLATOR_DIR=/path/to/project`
- Interactive prompt (if not specified)

**Directory structure:**
- `INPUT_DIR="$PROJECT_DIR/input"`
- `TRANSCRIPT_DIR="$PROJECT_DIR/transcripts"`
- `TRANSLATION_DIR="$PROJECT_DIR/translations"`
- `AUDIO_DIR="$PROJECT_DIR/audio"`

## OpenClaw Permissions

If using OpenClaw and constantly getting approval prompts for podcast-translator scripts, configure execApprovals:

### Quick Setup

```bash
openclaw approvals set --file podcast-translator-exec-approvals.json
```

### Manual Configuration

Create or update `~/.openclaw/exec-approvals.json`:

```json
{
  "version": 1,
  "defaults": {
    "security": "allowlist"
  },
  "agents": {
    "podcast-translator": {
      "allowlist": [
        {
          "pattern": "python3 *",
          "commandText": "Python scripts for podcast translation"
        },
        {
          "pattern": "yt-dlp *",
          "commandText": "YouTube audio download"
        },
        {
          "pattern": "edge-tts *",
          "commandText": "Edge TTS generation"
        },
        {
          "pattern": "ffmpeg *",
          "commandText": "Audio processing"
        }
      ]
    }
  }
}
```

### Verify Configuration

```bash
openclaw approvals get
```

Expected output:
```
Defaults: security=allowlist
Agents: 1 (podcast-translator)
Allowlist: 4 entries
```

**Security Note**: This configuration only allows specific commands for the podcast-translator agent, not system-wide.

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

### 1. OpenClaw Skill (Recommended) 🎙️

Automatic pipeline via OpenClaw skill. Just send a YouTube URL:

```
Translate this podcast: https://www.youtube.com/watch?v=VIDEO_ID
```

The skill automatically:
- Downloads audio
- Transcribes
- Translates to Russian
- Generates voiceover

**With voice selection:**
```
Translate this podcast with a female voice: https://www.youtube.com/watch?v=VIDEO_ID
```

Available voices: Dmitry (male, default), Svetlana (female), Dariya (female).

### 2. Claude Code Agent

Autonomous agent for Claude Code located at `agents/podcast-translator.md`:

```
Use the podcast-translator agent for this URL
```

Or simply:
```
Translate this podcast: https://www.youtube.com/watch?v=VIDEO_ID
```

The agent will ask about voice preference and execute the entire pipeline autonomously.

### 3. Bash Script (Semi-automatic)

```bash
cd /home/clawd/work/podcast-translator
./scripts/download_and_process.sh "https://www.youtube.com/watch?v=VIDEO_ID"
```

You'll need to manually translate at step 4 using the podcast-translator skill.

**With custom directory:**
```bash
./scripts/download_and_process.sh --destination-dir /custom/path "URL"
```

### 4. Step-by-Step (Full Control)

**1. Download audio**
```bash
yt-dlp -x --audio-format mp3 --audio-quality 0 -o input/podcast.mp3 "URL"
```

**2. Transcribe**
```bash
python3 scripts/transcribe_cached.py input/podcast.mp3 transcripts/ small
```

**3. Prepare for translation**
```bash
python3 scripts/prepare_transcript.py transcripts/podcast.txt translations/podcast_ready.txt
```

**4. Translate** (using skill or manually)

Use the `podcast-translator` skill or translate manually.

**5. Generate TTS**
```bash
# Default voice (Dmitry - male)
python3 scripts/generate_tts.py translations/podcast_ru.txt audio/podcast.ru.mp3

# Female voice (Svetlana)
python3 scripts/generate_tts.py translations/podcast_ru.txt audio/podcast.ru.mp3 ru-RU-SvetlanaNeural
```

## Translation File Format

The pipeline creates two translation files:

**With timestamps** (`{episode}_ru.txt`):
```
[00:00 - 00:05] First translation segment
[00:05 - 00:10] Second translation segment
```

**For TTS** (`{episode}_ru_tts.txt`):
```
First translation segment. Second translation segment.
```

## CPU Optimization

`transcribe_cached.py` is optimized for Raspberry Pi ARM:
- `beam_size=1` (faster on CPU)
- `int8` quantization
- VAD filter disabled
- 4 CPU threads, 2 workers
- Progress heartbeat every 10 seconds

## License

MIT

## Integrations

### OpenClaw Skill 🎙️

Automatic skill for OpenClaw with full pipeline:
- Recognizes YouTube URLs and translation requests
- Spawns subagent to execute pipeline
- Supports voice selection (Dmitry, Svetlana, Dariya)
- Returns results when ready

File: `skills/podcast-translator/SKILL.md`

### Claude Code Agent

Autonomous agent for Claude Code (`agents/podcast-translator.md`):
- Executes full pipeline
- Supports voice selection
- Returns detailed statistics

## Documentation

- [AGENTS.md](AGENTS.md) - Subagent documentation
- [VOICES.md](VOICES.md) - TTS voice comparison
- [PROGRESS_FORMAT.md](PROGRESS_FORMAT.md) - Progress output format for CLI agents

---

## Automated Queue Processing System 🤖

The podcast-translator now includes a fully automated system for processing YouTube videos via cron jobs and OpenClaw subagents.

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                   Cron Job #1 (08:30 daily)                     │
│                YouTube Video Collector                          │
│                                                                  │
│  ✅ Check channels → ✅ Add new videos to queue                 │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ↓
                    ┌──────────────┐
                    │   Queue      │
                    │   (JSON)     │
                    │              │
                    │ pending: 14  │
                    └──────────────┘
                           │
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│                Cron Job #2 (08:40-18:40)                        │
│                  Queue Processor                                │
│                  Every 2 hours                                 │
│                                                                  │
│  ✅ Get video → ✅ Spawn subagent → ✅ Send MP3 to Telegram     │
└─────────────────────────────────────────────────────────────────┘
```

### Components

#### 1. YouTube Video Collector (Cron Job #1)

**Schedule:** Daily at 08:30 Europe/Minsk
**Script:** `channel_monitor.py`

```bash
# Cron job executes:
python3 channel_monitor.py --videos-per-channel 3 --json-output
```

**Functionality:**
- Monitors configured YouTube channels (AIDailyBrief, mreflow)
- Uses `yt-dlp` to fetch latest videos from each channel
- Adds new videos to `youtube-queue.json`
- Skips duplicates automatically
- Returns statistics: checked/added/skipped videos

**Configuration:** `/home/clawd/.openclaw/workspace/youtube-channels.json`
```json
{
  "channels": [
    {"name": "AIDailyBrief", "url": "https://www.youtube.com/@AIDailyBrief"},
    {"name": "mreflow", "url": "https://www.youtube.com/@mreflow"}
  ]
}
```

#### 2. Queue Processor (Cron Job #2)

**Schedule:** Every 2 hours (08:40, 10:40, 12:40, 14:40, 16:40, 18:40)
**Script:** `queue_processor.py`

```bash
# Cron job executes:
python3 queue_processor.py --max-videos 2
```

**Functionality:**
- Processes up to 2 videos per run
- Clears old completed entries from queue
- Checks time window (only 08:30-20:00)
- Spawns OpenClaw subagent for each video
- Reads manifest to find generated MP3 files
- Sends MP3 files to Telegram with metadata
- Marks videos as completed or failed

**Time Window Protection:**
- Skips processing if before 08:30 or after 20:00
- Just shows queue status and exits gracefully

#### 3. Queue Manager

**Script:** `queue_manager.py`

**Queue Structure:** `youtube-queue.json`
```json
{
  "pending": [...],      // Videos waiting to be processed
  "processing": null,    // Currently processing video
  "completed": [...],    // Successfully processed videos
  "failed": []           // Failed videos with error messages
}
```

**Methods:**
- `add_videos()` - Add videos to queue (skip duplicates)
- `get_next_video()` - Get next pending video
- `mark_processing()` - Mark video as processing
- `mark_completed()` - Mark video as completed
- `mark_failed()` - Mark video as failed
- `clear_all_completed()` - Remove all completed entries
- `get_status()` - Get queue statistics

#### 4. OpenClaw Subagent

**Skill:** `SKILL.md` (podcast-translator)

**Pipeline Steps:**
1. **Download Audio** - `yt-dlp` extracts MP3 from YouTube
2. **Transcribe** - `faster-whisper` transcribes to English
3. **Prepare** - Format transcript for translation
4. **Translate** - Translate to Russian (preserves timestamps)
5. **Extract TTS Text** - Remove timestamps for TTS generation
6. **Generate TTS** - Edge TTS creates Russian voiceover **with MP3 metadata**
7. **Create Manifest** - Output manifest for file delivery

**MP3 Metadata:**
- **Title:** YouTube video title
- **Artist:** Channel name
- Added via ffmpeg metadata tags

**Manifest File:** `translations/{basename}_manifest.txt`
```
===OPENCLAW_OUTPUTS_COMPLETE===
translation:translations/{basename}_ru.txt
tts_text:translations/{basename}__ru_tts.txt
audio:audio/{basename}.ru.mp3
transcript:transcripts/{basename}.txt
base_dir:$SKILL_DIR
===OPENCLAW_OUTPUTS_END===
```

#### 5. Telegram Delivery

**Method:** `queue_processor.py:send_to_telegram()`

**Functionality:**
- Sends MP3 file via OpenClaw Telegram integration
- Includes message with video title, channel, and file size
- Uses `openclaw message send --channel telegram --media <file>`
- 5-minute timeout for large files
- Returns delivery status and message ID

**Message Format:**
```
🎙️ {Video Title}

📺 Channel: {Channel Name}
🆔 Video ID: {Video ID}
📊 Size: {X} MB

🔗 Original: https://www.youtube.com/watch?v={Video ID}
```

### Directory Structure

```
/home/clawd/.openclaw/workspace/
├── youtube-channels.json              # Channel configuration
├── youtube-queue.json                 # Queue state
└── skills/podcast-translator/
    ├── SKILL.md                       # OpenClaw skill definition
    ├── channel_monitor.py             # YouTube Video Collector
    ├── queue_processor.py             # Queue Processor
    ├── queue_manager.py               # Queue state management
    ├── scripts/
    │   ├── generate_tts.py            # TTS with MP3 metadata
    │   ├── transcribe_cached.py       # Transcription
    │   ├── prepare_transcript.py      # Transcript preparation
    │   └── extract_tts_text.py        # TTS text extraction
    ├── audio/                         # Generated MP3 files
    ├── input/                         # Downloaded audio
    ├── transcripts/                   # English transcriptions
    └── translations/                  # Russian translations
```

### OpenClaw Setup

**Symlink:**
```bash
/home/clawd/.openclaw/skills/podcast-translator →
  /home/clawd/.openclaw/workspace/skills/podcast-translator
```

**Cron Jobs:**
```bash
# List all cron jobs
openclaw cron list

# View specific job
openclaw cron runs --id <job-id>

# Run job manually
openclaw cron run <job-id>
```

### Daily Workflow

**08:30** - YouTube Video Collector runs
- Checks 2 channels (AIDailyBrief, mreflow)
- Adds ~15 new videos to queue
- Skips duplicates

**08:40, 10:40, 12:40, 14:40, 16:40, 18:40** - Queue Processor runs
- Processes 2 videos per run
- 12 videos processed per day (6 runs × 2 videos)
- Each video: ~2 hours (download → transcribe → translate → TTS)
- MP3 files sent to Telegram automatically

**After 20:00** - Processing stops
- Queue Processor checks time window
- Only shows queue status, no processing

### Monitoring

**Check queue status:**
```bash
python3 /home/clawd/.openclaw/workspace/skills/podcast-translator/queue_manager.py status
```

**View cron job runs:**
```bash
openclaw cron runs --id <job-id>
```

**Check logs:**
```bash
openclaw logs --tail 50 | grep "queue-processor\|youtube-collector"
```

### Configuration Files

**Cron Job #1 (YouTube Video Collector):**
```bash
openclaw cron add --name "youtube-collector" \
  --cron "30 8 * * *" \
  --tz "Europe/Minsk" \
  --description "YouTube Video Collector" \
  --session isolated \
  --timeout-seconds 900 \
  --no-deliver \
  --message "cd /home/clawd/.openclaw/workspace/skills/podcast-translator && python3 channel_monitor.py --videos-per-channel 3 --json-output"
```

**Cron Job #2 (Queue Processor):**
```bash
openclaw cron add --name "queue-processor" \
  --cron "40 8,10,12,14,16,18 * * *" \
  --tz "Europe/Minsk" \
  --description "Queue Processor - Process 2 videos every 2 hours (08:40-18:40)" \
  --session isolated \
  --timeout-seconds 14400 \
  --no-deliver \
  --message "cd /home/clawd/.openclaw/workspace/skills/podcast-translator && python3 queue_processor.py --max-videos 2"
```

### Manual Testing

**Test YouTube Video Collector:**
```bash
cd /home/clawd/.openclaw/workspace/skills/podcast-translator
python3 channel_monitor.py --videos-per-channel 3
```

**Test Queue Processor:**
```bash
python3 queue_processor.py --max-videos 1
```

**Add video manually:**
```bash
python3 queue_manager.py add VIDEO_ID "Title" "Channel"
```

### Troubleshooting

**Cron job not running:**
- Check schedule: `openclaw cron list`
- Verify timezone: Europe/Minsk
- Check job status: `openclaw cron runs --id <job-id>`

**Subagent spawn failing:**
- Check skill symlink: `ls -la /home/clawd/.openclaw/skills/podcast-translator`
- Verify execApprovals: `openclaw approvals get`
- Check SKILL.md exists

**MP3 not sent to Telegram:**
- Check `send_to_telegram()` method in `queue_processor.py`
- Verify OpenClaw Telegram integration
- Check file permissions

**Queue not processing:**
- Check time window (08:30-20:00)
- Verify queue has pending videos
- Check `youtube-queue.json` format

### Performance

**Processing Time:**
- Video download: ~2 minutes
- Transcription: ~20 minutes (CPU-optimized)
- Translation: ~30 minutes (AI)
- TTS generation: ~5 minutes
- **Total per video:** ~1 hour (actual time depends on video length)

**Daily Capacity:**
- 6 cron job runs × 2 videos = 12 videos/day
- Queue clears accumulated videos in ~1-2 days

---

**The automated system runs 24/7, processing YouTube videos without manual intervention!** 🚀
