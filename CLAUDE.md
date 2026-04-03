# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Automated pipeline for translating YouTube podcasts from English to Russian with Russian voiceover generation. The project consists of Python scripts for audio processing, a Claude skill for translation, and a subagent for autonomous execution.

## Architecture

The pipeline follows a 5-stage process:

1. **Download** (`yt-dlp`) - Extract MP3 audio from YouTube URLs
2. **Transcribe** (`faster-whisper`) - Generate English transcript with timestamps
3. **Prepare** (`prepare_transcript.py`) - Format transcript for translation
4. **Translate** (Claude/skill) - Translate to Russian, preserving timestamps and technical terms
5. **Generate TTS** (`edge-tts`) - Create Russian voiceover audio

### Key Components

- **scripts/transcribe_cached.py** - CPU-optimized transcription using faster-whisper with int8 quantization
- **scripts/prepare_transcript.py** - Removes timestamps from transcript for TTS generation
- **scripts/generate_tts.py** - Async TTS generation with chunking and FFmpeg merge
- **scripts/download_and_process.sh** - Full pipeline orchestration
- **skills/podcast-translator-skill/** - Claude skill for EN→RU translation with timestamp preservation

### Directory Structure

```
input/          # Downloaded MP3 files
transcripts/    # English transcripts with timestamps
translations/   # Russian translations (with/without timestamps)
audio/          # Final Russian TTS audio files
```

## Common Commands

### Full Pipeline (semi-automatic)
```bash
./scripts/download_and_process.sh "https://www.youtube.com/watch?v=VIDEO_ID"
```
Note: Requires manual translation step (press Enter after translating).

### Individual Steps

**Download audio:**
```bash
yt-dlp -x --audio-format mp3 --audio-quality 0 -o input/podcast.mp3 "URL"
```

**Transcribe (CPU-optimized, cached model):**
```bash
python3 scripts/transcribe_cached.py input/podcast.mp3 transcripts/ small
```

**Prepare for translation:**
```bash
python3 scripts/prepare_transcript.py transcripts/podcast.txt translations/podcast_ready.txt
```

**Generate TTS (default male voice - Dmitry):**
```bash
python3 scripts/generate_tts.py translations/podcast_ru_tts.txt audio/podcast.ru.mp3
```

**Generate TTS (female voice - Svetlana):**
```bash
python3 scripts/generate_tts.py translations/podcast_ru_tts.txt audio/podcast.ru.mp3 ru-RU-SvetlanaNeural
```

### Dependencies
```bash
pip install faster-whisper edge-tts yt-dlp --break-system-packages
```

## Progress Output Format

All scripts output machine-readable progress for CLI agent monitoring:
- `STATUS:` - Step updates
- `HEARTBEAT:` - Liveliness indicator every 10s during long operations
- `SUCCESS:` - Completion confirmation
- `ERROR:` - Failure indication

See PROGRESS_FORMAT.md for detailed specification.

## TTS Voice Options

- **ru-RU-DmitryNeural** - Male voice (default)
- **ru-RU-SvetlanaNeural** - Female voice

See VOICES.md for voice comparisons and usage examples.

## Translation Skill

The `podcast-translator` skill handles EN→RU translation:
- Reads transcript files from `transcripts/`
- Creates TTS-ready output:
  - `{episode}_ru_tts.txt` - clean Russian text without timestamps
- Preserves technical terms in English (OpenAI, GPU, API, etc.)
- Removes all unspeakable characters (Chinese, Japanese, Korean, etc.)

See skills/podcast-translator-skill/SKILL.md for translation guidelines.

## Subagent

Autonomous subagent at `~/.claude/agents/podcast-translator.md` executes the full pipeline. Usage:
```
Переведи этот подкаст: https://www.youtube.com/watch?v=VIDEO_ID
```

## CPU Optimization

`transcribe_cached.py` is optimized for Raspberry Pi ARM:
- `beam_size=1` for faster CPU inference
- `int8` quantization
- 4 CPU threads, 2 workers
- Disabled VAD filter for speed
- Explicit cache directory for HuggingFace models
