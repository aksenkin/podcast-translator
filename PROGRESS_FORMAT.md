# Progress Output Format for CLI Agents

All scripts in the podcast-translator pipeline output machine-readable progress for CLI agent monitoring.

## Format

All progress messages use prefixes followed by a colon:

- `STATUS:` - Step updates and progress information
- `HEARTBEAT:` - Regular heartbeat to show process is alive (every 10 seconds during long operations)
- `SUCCESS:` - Successful completion of a step
- `ERROR:` - Error or failure

## Example Output

```
STATUS: Downloading audio from YouTube...
STATUS: Downloaded audio: input/podcast_20260327_123456.mp3
STATUS: Starting transcription...
STATUS: Using cached model: small
HEARTBEAT: 15.3% | segments: 45 | Transcribing...
HEARTBEAT: 30.7% | segments: 90 | Transcribing...
HEARTBEAT: 46.0% | segments: 135 | Transcribing...
HEARTBEAT: 61.3% | segments: 180 | Transcribing...
HEARTBEAT: 76.7% | segments: 225 | Transcribing...
HEARTBEAT: 92.0% | segments: 270 | Transcribing...
SUCCESS: Transcription complete: 293 segments
STATUS: Preparing transcript for translation...
SUCCESS: Prepared for translation: translations/podcast_20260327_123456_ready.txt
STATUS: Text length: 15234 characters
STATUS: Translating to Russian (this may take a few minutes)...
HEARTBEAT: Translation in progress...
STATUS: Translation complete: 12456 words
STATUS: Starting TTS generation...
STATUS: Generating TTS for: translations/podcast_20260327_123456_ru_tts.txt
STATUS: Text length: 12456 characters
STATUS: Voice: ru-RU-DmitryNeural
STATUS: Split into 15 chunks
STATUS: Processing chunk 1/15 (6.7%)
HEARTBEAT: Chunk 1/15 done: 245.2 KB
STATUS: Processing chunk 2/15 (13.3%)
HEARTBEAT: Chunk 2/15 done: 198.7 KB
...
STATUS: Processing chunk 15/15 (100.0%)
HEARTBEAT: Chunk 15/15 done: 187.3 KB
STATUS: Generated 15 audio segments
STATUS: Merge list created: 15 files
STATUS: Running ffmpeg...
SUCCESS: Audio merged successfully: audio/podcast_20260327_123456.ru.mp3
STATUS: Final file size: 3521.4 KB
STATUS: Cleaning up temp files...
SUCCESS: Cleanup complete
SUCCESS: Pipeline complete
STATUS: Original audio: input/podcast_20260327_123456.mp3 (15.2 MB)
STATUS: Transcript: transcripts/podcast_20260327_123456.txt (293 segments)
STATUS: Translation (with timestamps): translations/podcast_20260327_123456_ru.txt (12456 words)
STATUS: Translation (TTS-ready): translations/podcast_20260327_123456_ru_tts.txt (12456 words)
STATUS: Russian audio: audio/podcast_20260327_123456.ru.mp3 (3521.4 KB)
STATUS: Audio duration: 14:32
```

## Parsing in CLI Agents

CLI agents can parse progress by checking for message prefixes:

```python
import sys

for line in sys.stdin:
    if line.startswith("STATUS:"):
        # Update progress display
        progress = line.split("STATUS:", 1)[1].strip()
    elif line.startswith("HEARTBEAT:"):
        # Process is alive, update progress bar
        heartbeat = line.split("HEARTBEAT:", 1)[1].strip()
    elif line.startswith("SUCCESS:"):
        # Step completed successfully
        success_msg = line.split("SUCCESS:", 1)[1].strip()
    elif line.startswith("ERROR:"):
        # Error occurred
        error_msg = line.split("ERROR:", 1)[1].strip()
        # Handle error
```

## Scripts with Progress Output

| Script | Progress Output |
|--------|-----------------|
| `transcribe_cached.py` | ✓ Full progress with heartbeats |
| `prepare_transcript.py` | ✓ STATUS/SUCCESS |
| `generate_tts.py` | ✓ Full progress with heartbeats per chunk |
| Translation (Claude) | ✓ STATUS before/after |

## Implementation Details

- All progress messages use `flush=True` to ensure immediate output
- Heartbeats are sent every 10 seconds during long operations
- Percentage is included where applicable
- File sizes in KB/MB for reference
- Segment/word counts for progress tracking
