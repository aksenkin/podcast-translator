# Hybrid Pipeline: Podcast Translator Queue Processor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the fragile `sessions_spawn`-based queue processor with a reliable `agentTurn` pipeline where the `work` agent executes the full podcast translation pipeline via `exec` calls and LLM translation in-context.

**Architecture:** Cron job triggers `agentTurn` on the embedded `work` agent. The agent processes all pending videos sequentially — downloading, transcribing, preparing, translating (LLM in-context, GoogleTranslator fallback), generating TTS, reporting to Telegram, and updating queue state. A Python launcher script with PID-lock prevents concurrent runs.

**Tech Stack:** Python 3, yt-dlp, faster-whisper, edge-tts, deep_translator (GoogleTranslator), OpenClaw CLI (cron edit, message send)

---

## File Structure

| File | Responsibility |
|------|---------------|
| `run_pipeline.py` | PID-lock launcher — triggers cron job, prevents concurrent runs |
| `process-queue.py` | **Modified** — add `--translate-only` flag for GoogleTranslator fallback |
| `queue_manager.py` | Queue state management (unchanged) |
| `scripts/transcribe_cached.py` | Whisper transcription (unchanged) |
| `scripts/prepare_transcript.py` | Strip timestamps (unchanged) |
| `scripts/extract_tts_text.py` | Extract TTS-ready text (unchanged) |
| `scripts/generate_tts.py` | Edge-TTS audio generation (unchanged) |

---

### Task 1: Add `--translate-only` flag to `process-queue.py`

**Files:**
- Modify: `/home/clawd/.openclaw/workspace/skills/podcast-translator/process-queue.py:327-357`
- Test: manual CLI test

The `work` agent needs a fallback when LLM translation fails. This flag lets the agent call `python3 process-queue.py --translate-only <videoId>` to translate a single video using GoogleTranslator.

- [ ] **Step 1: Add `translate_only` method to `QueueProcessor`**

Add a new method after `process_next_video()` (after line 289) that translates a single video by ID using GoogleTranslator:

```python
def translate_only(self, video_id):
    """Translate a single video using GoogleTranslator (fallback for LLM).

    Args:
        video_id: YouTube video ID to translate

    Returns:
        Dict with translation result
    """
    queue = self.qm._load_queue()

    # Find the ready file for this video
    # Check both timestamped and simple naming patterns
    ready_files = list((self.skill_dir / "translations").glob(f"*{video_id}*_ready.txt"))
    if not ready_files:
        # Try finding any ready file that was recently created
        ready_files = sorted((self.skill_dir / "translations").glob("*_ready.txt"), key=lambda f: f.stat().st_mtime, reverse=True)

    if not ready_files:
        return {"success": False, "error": f"No ready file found for {video_id}"}

    ready_file = ready_files[0]
    print(f"STATUS: Translating {ready_file.name} via GoogleTranslator")

    try:
        transcript_content = ready_file.read_text(encoding='utf-8')
        translator = GoogleTranslator(source='en', target='ru')

        translation_lines = []
        for line in transcript_content.split("\n"):
            if line.strip():
                if line.startswith("[") and "]" in line:
                    timestamp_end = line.index("]") + 1
                    timestamp = line[:timestamp_end]
                    text = line[timestamp_end:].strip()
                    if text:
                        try:
                            translated_text = translator.translate(text)
                            translation_lines.append(f"{timestamp} {translated_text}")
                        except Exception:
                            translation_lines.append(f"{timestamp} {text}")
                else:
                    translation_lines.append(line)

        # Write translation file
        translation_file = ready_file.parent / ready_file.name.replace("_ready.txt", "_ru.txt")
        translation_file.write_text("\n".join(translation_lines), encoding='utf-8')
        print(f"SUCCESS: Translation saved: {translation_file.name}")

        # Extract TTS text
        tts_file = ready_file.parent / ready_file.name.replace("_ready.txt", "_ru_tts.txt")
        extract_result = subprocess.run(
            ["python3", str(self.skill_dir / "scripts" / "extract_tts_text.py"),
             str(translation_file), str(tts_file)],
            capture_output=True, text=True, timeout=60
        )
        if extract_result.returncode != 0:
            return {"success": False, "error": f"Extract TTS failed: {extract_result.stderr}"}

        return {"success": True, "translation": str(translation_file), "tts_text": str(tts_file)}

    except Exception as e:
        return {"success": False, "error": str(e)}
```

- [ ] **Step 2: Update `main()` to handle `--translate-only` flag**

Replace the `main()` function (lines 328-357) with:

```python
def main():
    """Main entry point."""
    processor = QueueProcessor()

    # Check for --translate-only flag
    if "--translate-only" in sys.argv:
        idx = sys.argv.index("--translate-only")
        if idx + 1 >= len(sys.argv):
            print("Error: --translate-only requires a video ID")
            sys.exit(1)
        video_id = sys.argv[idx + 1]
        result = processor.translate_only(video_id)
        if result["success"]:
            print(f"✅ Translation complete: {result.get('translation', '')}")
        else:
            print(f"❌ Translation failed: {result.get('error', '')}")
            sys.exit(1)
        return

    # YouTube channels to monitor
    channels = [
        {
            "url": "https://www.youtube.com/@AIDailyBrief/videos",
            "name": "AIDailyBrief"
        },
        {
            "url": "https://www.youtube.com/@mreflow/videos",
            "name": "mreflow"
        }
    ]

    # Run one complete cycle
    result = processor.run_once(channels)

    if result["success"]:
        if "video" in result:
            print(f"\n✅ Completed: {result['video']['title']}")
        else:
            print(f"\n✅ {result['message']}")
    else:
        print(f"\n❌ Failed: {result['error']}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Test the --translate-only flag**

Run: `python3 /home/clawd/.openclaw/workspace/skills/podcast-translator/process-queue.py --translate-only test123`
Expected: Error message about "No ready file found for test123" (no matching file exists, but the flag is recognized)

- [ ] **Step 4: Commit**

```bash
cd /home/clawd/.openclaw/workspace/skills/podcast-translator
git add process-queue.py
git commit -m "feat: add --translate-only flag to process-queue.py for GoogleTranslator fallback"
```

---

### Task 2: Create `run_pipeline.py` launcher with PID-lock

**Files:**
- Create: `/home/clawd/.openclaw/workspace/skills/podcast-translator/run_pipeline.py`

This script prevents concurrent pipeline runs using a PID-lock file. It triggers the queue-processor cron job via `openclaw cron run`.

- [ ] **Step 1: Create the launcher script**

```python
#!/usr/bin/env python3
"""
Podcast Pipeline Launcher with PID-lock concurrency control.

Prevents concurrent runs of the queue-processor cron job.
Can be called manually or from other cron jobs (e.g., youtube-collector).

Usage:
    python3 run_pipeline.py              # Trigger queue-processor cron job
    python3 run_pipeline.py --status     # Check if pipeline is running
    python3 run_pipeline.py --force      # Force run even if lock exists
"""

import atexit
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

LOCK_FILE = "/tmp/podcast-queue.lock"
CRON_JOB_ID = "a79e58b0-f9bd-4911-86a7-44c01a1ae572"
TIMEOUT_SECONDS = 1800  # 30 minutes


def read_lock():
    """Read PID from lock file. Returns PID or None."""
    try:
        if os.path.exists(LOCK_FILE):
            content = Path(LOCK_FILE).read_text().strip()
            if content.isdigit():
                return int(content)
    except (OSError, ValueError):
        pass
    return None


def is_pid_alive(pid):
    """Check if a process with given PID is alive."""
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def acquire_lock(force=False):
    """Acquire the pipeline lock. Returns True if lock acquired."""
    existing_pid = read_lock()

    if existing_pid is not None:
        if not force and is_pid_alive(existing_pid):
            print(f"STATUS: Pipeline already running (PID {existing_pid})")
            return False
        else:
            # Stale lock or force — clean it up
            print(f"STATUS: Removing stale lock (PID {existing_pid})")
            release_lock()

    # Write our PID
    Path(LOCK_FILE).write_text(str(os.getpid()))
    return True


def release_lock():
    """Release the pipeline lock."""
    try:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
    except OSError:
        pass


def handle_timeout(signum, frame):
    """Handle timeout signal."""
    print("ERROR: Pipeline timed out after 30 minutes")
    release_lock()
    sys.exit(2)


def run_pipeline():
    """Trigger the queue-processor cron job."""
    print(f"STATUS: Starting pipeline at {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"STATUS: Cron job ID: {CRON_JOB_ID}")

    try:
        result = subprocess.run(
            ["openclaw", "cron", "run", CRON_JOB_ID],
            timeout=TIMEOUT_SECONDS,
            capture_output=False
        )

        if result.returncode == 0:
            print(f"SUCCESS: Pipeline completed")
        else:
            print(f"ERROR: Pipeline exited with code {result.returncode}")

        return result.returncode

    except subprocess.TimeoutExpired:
        print("ERROR: Pipeline timed out after 30 minutes")
        return 2
    except Exception as e:
        print(f"ERROR: Pipeline failed: {e}")
        return 1


def show_status():
    """Show current pipeline lock status."""
    pid = read_lock()
    if pid is not None and is_pid_alive(pid):
        print(f"Pipeline is RUNNING (PID {pid})")
        return 0
    elif pid is not None:
        print(f"Pipeline lock is STALE (PID {pid} is dead)")
        return 1
    else:
        print("Pipeline is NOT running")
        return 0


def main():
    # Register cleanup
    atexit.register(release_lock)

    # Handle SIGTERM
    signal.signal(signal.SIGTERM, lambda s, f: (release_lock(), sys.exit(130)))

    # Parse args
    force = "--force" in sys.argv
    if "--status" in sys.argv:
        sys.exit(show_status())

    # Acquire lock
    if not acquire_lock(force=force):
        sys.exit(0)

    # Run pipeline
    exit_code = run_pipeline()

    # Release lock (also done by atexit, but explicit is better)
    release_lock()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Make the script executable**

Run: `chmod +x /home/clawd/.openclaw/workspace/skills/podcast-translator/run_pipeline.py`

- [ ] **Step 3: Test lock acquisition and status**

Run:
```bash
python3 /home/clawd/.openclaw/workspace/skills/podcast-translator/run_pipeline.py --status
```
Expected: `Pipeline is NOT running`

Then test stale lock detection:
```bash
echo "99999" > /tmp/podcast-queue.lock
python3 /home/clawd/.openclaw/workspace/skills/podcast-translator/run_pipeline.py --status
```
Expected: `Pipeline lock is STALE (PID 99999 is dead)`

Clean up:
```bash
rm -f /tmp/podcast-queue.lock
```

- [ ] **Step 4: Commit**

```bash
cd /home/clawd/.openclaw/workspace/skills/podcast-translator
git add run_pipeline.py
git commit -m "feat: add run_pipeline.py launcher with PID-lock concurrency control"
```

---

### Task 3: Update queue-processor cron job payload

**Files:**
- Modify: `/home/clawd/.openclaw/cron/jobs.json:108-143`

Replace the current queue-processor cron job payload (which uses `sessions_spawn`) with an `agentTurn` payload that instructs the `work` agent to run the full pipeline via `exec`. Also update `timeoutSeconds` from 600 to 1800.

- [ ] **Step 1: Write the new agentTurn payload message**

This is the message the `work` agent will receive. It must be complete and self-contained:

```
## Podcast Translation Queue Processor

Process all pending videos from the YouTube translation queue.

Working directory: /home/clawd/.openclaw/workspace/skills/podcast-translator

CRITICAL RULES:
- Do NOT install any software
- Do NOT use sessions_spawn
- Process ALL pending videos sequentially
- On any step failure: mark video as failed and continue to next video
- Send Telegram report after EACH video (success or failure)
- Stop processing if 25 minutes have elapsed since start

### Pipeline per video:

1. Get next video:
   Run: `python3 queue_manager.py next --json`
   If response is `{"empty": true}` → send final summary and STOP

2. Download audio:
   Run: `yt-dlp -x --audio-format mp3 --audio-quality 0 -o "input/{videoId}.mp3" "https://www.youtube.com/watch?v={videoId}"`
   On failure: `python3 queue_manager.py fail {videoId} "Download failed"` → next video

3. Transcribe:
   Run: `python3 scripts/transcribe_cached.py "input/{videoId}.mp3" transcripts/ small`
   On failure: `python3 queue_manager.py fail {videoId} "Transcription failed"` → next video

4. Prepare for translation:
   Run: `python3 scripts/prepare_transcript.py "transcripts/{videoId}.txt" "translations/{videoId}_ready.txt"`
   On failure: `python3 queue_manager.py fail {videoId} "Prepare failed"` → next video

5. Translate EN→RU (LLM in-context):
   - Read the prepared transcript file from `translations/{videoId}_ready.txt`
   - Translate to Russian, preserving technical terms in English (OpenAI, GPU, API, etc.)
   - Remove unspeakable characters (Chinese, Japanese, Korean, emoji, special symbols)
   - Write clean Russian text (no timestamps) to `translations/{videoId}_ru_tts.txt`
   - If translation is too long or fails: fall back to GoogleTranslator by running
     `python3 process-queue.py --translate-only {videoId}`

6. Generate TTS:
   Run: `python3 scripts/generate_tts.py "translations/{videoId}_ru_tts.txt" "audio/{videoId}.ru.mp3"`
   On failure: `python3 queue_manager.py fail {videoId} "TTS failed"` → next video

7. Report success:
   Run: `openclaw message send --channel telegram --target 49621692 --message "✅ {title} — перевод завершён"`

8. Mark complete:
   Run: `python3 queue_manager.py complete {videoId}`

9. Go to step 1 (next video)

### Error handling:
On ANY step failure:
   Run: `openclaw message send --channel telegram --target 49621692 --message "❌ {title} — {error}"`
   Then continue to next video

### Final summary:
After processing all videos (or 25 min elapsed):
   Run: `openclaw message send --channel telegram --target 49621692 --message "📊 Очередь: {completed} готово, {failed} ошибок, {remaining} осталось"`
```

- [ ] **Step 2: Update the cron job via `openclaw cron edit`**

Run:
```bash
openclaw cron edit a79e58b0-f9bd-4911-86a7-44c01a1ae572 \
  --name "queue-processor" \
  --description "Queue Processor - agentTurn pipeline (no sessions_spawn)" \
  --timeout-seconds 1800 \
  --message '## Podcast Translation Queue Processor

Process all pending videos from the YouTube translation queue.

Working directory: /home/clawd/.openclaw/workspace/skills/podcast-translator

CRITICAL RULES:
- Do NOT install any software
- Do NOT use sessions_spawn
- Process ALL pending videos sequentially
- On any step failure: mark video as failed and continue to next video
- Send Telegram report after EACH video (success or failure)
- Stop processing if 25 minutes have elapsed since start

### Pipeline per video:

1. Get next video:
   Run: `python3 queue_manager.py next --json`
   If response is `{"empty": true}` -> send final summary and STOP

2. Download audio:
   Run: `yt-dlp -x --audio-format mp3 --audio-quality 0 -o "input/{videoId}.mp3" "https://www.youtube.com/watch?v={videoId}"`
   On failure: `python3 queue_manager.py fail {videoId} "Download failed"` -> next video

3. Transcribe:
   Run: `python3 scripts/transcribe_cached.py "input/{videoId}.mp3" transcripts/ small`
   On failure: `python3 queue_manager.py fail {videoId} "Transcription failed"` -> next video

4. Prepare for translation:
   Run: `python3 scripts/prepare_transcript.py "transcripts/{videoId}.txt" "translations/{videoId}_ready.txt"`
   On failure: `python3 queue_manager.py fail {videoId} "Prepare failed"` -> next video

5. Translate EN->RU (LLM in-context):
   - Read the prepared transcript file from `translations/{videoId}_ready.txt`
   - Translate to Russian, preserving technical terms in English (OpenAI, GPU, API, etc.)
   - Remove unspeakable characters (Chinese, Japanese, Korean, emoji, special symbols)
   - Write clean Russian text (no timestamps) to `translations/{videoId}_ru_tts.txt`
   - If translation is too long or fails: fall back to GoogleTranslator by running
     `python3 process-queue.py --translate-only {videoId}`

6. Generate TTS:
   Run: `python3 scripts/generate_tts.py "translations/{videoId}_ru_tts.txt" "audio/{videoId}.ru.mp3"`
   On failure: `python3 queue_manager.py fail {videoId} "TTS failed"` -> next video

7. Report success:
   Run: `openclaw message send --channel telegram --target 49621692 --message "Done: {title}"`

8. Mark complete:
   Run: `python3 queue_manager.py complete {videoId}`

9. Go to step 1 (next video)

### Error handling:
On ANY step failure:
   Run: `openclaw message send --channel telegram --target 49621692 --message "Failed: {title} - {error}"`
   Then continue to next video

### Final summary:
After processing all videos (or 25 min elapsed):
   Run: `openclaw message send --channel telegram --target 49621692 --message "Queue: {completed} done, {failed} failed, {remaining} remaining"'
```

- [ ] **Step 3: Verify the cron job was updated**

Run: `openclaw cron list`
Expected: queue-processor shows `timeoutSeconds: 1800` and the new description.

- [ ] **Step 4: Commit**

Since cron/jobs.json is managed by OpenClaw gateway (not in git), just verify the update took effect. No git commit needed for this step.

---

### Task 4: Update youtube-collector to cascade via `run_pipeline.py`

**Files:**
- Modify: `/home/clawd/.openclaw/cron/jobs.json:144-167` (youtube-collector job)

The youtube-collector currently uses `sessions_spawn` to trigger the queue processor. Replace it with a call to `run_pipeline.py`.

- [ ] **Step 1: Update youtube-collector cron job**

The youtube-collector's `sessions_spawn` call in its message should be replaced with an `exec` call to `run_pipeline.py`. Update via `openclaw cron edit`:

```bash
openclaw cron edit b15718ab-2323-465d-bb22-53c0b555b3dc \
  --message '## YouTube Video Collector

Execute the channel monitor script to check YouTube channels for new videos.

CRITICAL: Do NOT install any software.

### Step 1: Run channel monitor

cd /home/clawd/.openclaw/workspace/skills/podcast-translator
python3 channel_monitor.py --videos-per-channel 3 --json-output

### Step 2: If videos were added, start pipeline

If the channel monitor added any videos (added > 0), start the queue processor:

python3 /home/clawd/.openclaw/workspace/skills/podcast-translator/run_pipeline.py

This triggers the queue-processor cron job with PID-lock concurrency control.
If a pipeline is already running, the launcher will exit silently.

Report results: {"checked": 2, "added": X, "skipped": Y, "errors": 0}'
```

- [ ] **Step 2: Verify the update**

Run: `openclaw cron list`
Expected: youtube-collector shows updated message without `sessions_spawn`.

---

### Task 5: End-to-end dry run test

**Files:**
- No file changes — testing only

Verify the full pipeline works with a manual trigger, no actual videos to process.

- [ ] **Step 1: Verify queue is empty**

Run: `python3 /home/clawd/.openclaw/workspace/skills/podcast-translator/queue_manager.py status`
Expected: `Pending: 0, Processing: 0`

- [ ] **Step 2: Run the pipeline manually**

Run: `openclaw cron run a79e58b0-f9bd-4911-86a7-44c01a1ae572`
Expected: The `work` agent starts, checks queue, finds it empty, sends "Queue empty" summary to Telegram, finishes.

- [ ] **Step 3: Test the launcher**

Run: `python3 /home/clawd/.openclaw/workspace/skills/podcast-translator/run_pipeline.py --status`
Expected: `Pipeline is NOT running`

Run: `python3 /home/clawd/.openclaw/workspace/skills/podcast-translator/run_pipeline.py`
Expected: Lock acquired, cron job triggered, pipeline runs (empty queue → quick finish), lock released.

- [ ] **Step 4: Test concurrent invocation protection**

Terminal 1:
```bash
echo $$ > /tmp/podcast-queue.lock
python3 /home/clawd/.openclaw/workspace/skills/podcast-translator/run_pipeline.py --status
```
Expected: `Pipeline is RUNNING (PID <$$>)`

Terminal 2:
```bash
python3 /home/clawd/.openclaw/workspace/skills/podcast-translator/run_pipeline.py
```
Expected: `Pipeline already running (PID ...)` and exit.

Clean up: `rm -f /tmp/podcast-queue.lock`

- [ ] **Step 5: Verify Telegram delivery**

Check Telegram for the "Queue: 0 done, 0 failed, 0 remaining" summary message from the `work` agent.

---

### Task 6: Add a test video and verify full pipeline

**Files:**
- No file changes — integration testing only

Add a short video to the queue and verify the entire pipeline runs end-to-end.

- [ ] **Step 1: Add a test video to the queue**

```bash
cd /home/clawd/.openclaw/workspace/skills/podcast-translator
python3 queue_manager.py add dQw4w9WgXcQ "Rick Astley - Never Gonna Give You Up" "RickAstleyYT"
```

- [ ] **Step 2: Trigger the pipeline**

```bash
openclaw cron run a79e58b0-f9bd-4911-86a7-44c01a1ae572
```

- [ ] **Step 3: Monitor progress**

Watch for Telegram messages:
1. Download complete
2. Transcription complete
3. Translation complete
4. TTS generation complete
5. Final summary

- [ ] **Step 4: Verify output files exist**

```bash
cd /home/clawd/.openclaw/workspace/skills/podcast-translator
ls -la input/dQw4w9WgXcQ* transcripts/dQw4w9WgXcQ* translations/dQw4w9WgXcQ* audio/dQw4w9WgXcQ*
```

Expected: MP3 input, .txt transcript, _ru_tts.txt translation, .ru.mp3 TTS output.

- [ ] **Step 5: Verify queue state**

```bash
python3 queue_manager.py status
```

Expected: `Pending: 0, Completed: 1` (or 2 if previous tests counted)

- [ ] **Step 6: Clean up test data (optional)**

```bash
rm -f input/dQw4w9WgXcQ.mp3 transcripts/dQw4w9WgXcQ.txt translations/dQw4w9WgXcQ_* audio/dQw4w9WgXcQ.ru.mp3
```

---

## Self-Review

### 1. Spec coverage

| Spec requirement | Task |
|-----------------|------|
| `agentTurn` instead of `sessions_spawn` | Task 3 |
| Python launcher with PID-lock | Task 2 |
| `--translate-only` GoogleTranslator fallback | Task 1 |
| `timeoutSeconds: 1800` | Task 3 |
| Sequential processing of all videos | Task 3 (payload) |
| LLM translation in-context | Task 3 (payload step 5) |
| Telegram reporting after each video | Task 3 (payload steps 7, error handling) |
| Final summary to Telegram | Task 3 (payload) |
| Concurrency control (no `maxConcurrent` change) | Task 2 |
| youtube-collector cascading | Task 4 |

### 2. Placeholder scan

No TBDs, TODOs, or vague instructions. All code blocks contain complete implementations.

### 3. Type consistency

- `QueueProcessor.translate_only()` returns `dict` with `success`, `error`, `translation`, `tts_text` keys — consistent with existing `process_next_video()` return format.
- `run_pipeline.py` uses `sys.exit()` codes: 0 (success/already-running), 1 (error), 2 (timeout) — consistent across functions.
- `queue_manager.py` CLI interface unchanged — `next --json`, `complete`, `fail` all use existing signatures.