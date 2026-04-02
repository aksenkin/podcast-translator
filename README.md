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
