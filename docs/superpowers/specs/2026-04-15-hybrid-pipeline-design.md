# Hybrid Pipeline: Podcast Translator Queue Processor

**Date:** 2026-04-15  
**Status:** Approved (pending implementation)

## Problem

The podcast-translator cron job uses `sessions_spawn` to create subagents for processing YouTube videos from a queue. This approach fails frequently because:

1. Subagent announce relies on WebSocket delivery with a 120-second gateway timeout
2. The spawned ACP process consumes significant memory on a Raspberry Pi (7.7GB RAM)
3. Gateway restarts or model errors cause cascading subagent failures
4. No effective timeout control — `runTimeoutSeconds` exists but the announce mechanism itself is fragile

## Design

### Approach: Embedded agentTurn + exec

Replace `sessions_spawn` with `agentTurn` on an embedded agent (`work`). The agent executes the entire pipeline in a single turn, calling Python scripts via `exec` tool and performing LLM translation in-context.

**Why this approach:**
- `agentTurn` runs inside the gateway process (no subprocess, no WebSocket announce)
- Single-turn execution is inherently more reliable than spawn-and-announce
- The `work` agent is embedded (not ACP), so no external process dependency
- LLM translation benefits from full context awareness (terminology, tone consistency)

### Architecture

```
Cron trigger (every 2 hours)
    │
    ▼
Cron job (agentTurn on "work" agent, timeout 1800s)
    │
    ▼
Work agent executes pipeline via exec:
    │
    ├─ python3 queue_manager.py next  ──►  get next pending video
    │   │
    │   ├─ yt-dlp                      ──►  download MP3
    │   ├─ python3 transcribe_cached.py──►  whisper transcription
    │   ├─ python3 prepare_transcript.py─►  format for translation
    │   ├─ LLM translate (in-context)    ──►  EN→RU (fallback: GoogleTranslator)
    │   ├─ python3 extract_tts_text.py  ──►  strip timestamps for TTS
    │   ├─ python3 generate_tts.py      ──►  edge-tts Russian voiceover
    │   ├─ openclaw message send        ──►  report to Telegram
    │   ├─ python3 queue_manager.py complete
    │   │
    │   └─ repeat for next video        ──►  sequential loop
    │
    └─ final report via openclaw message send
```

### Components

#### 1. Python Launcher Script (`run_pipeline.py`)

- **PID-lock file** (`/tmp/podcast-queue.lock`) for concurrency control
- If lock file exists and PID is alive → exit immediately (no overlap)
- On start: acquire lock, invoke `openclaw cron run <queue-processor-id>`
- On exit: release lock (in `finally` block + `atexit`)
- Timeout: 30 minutes (1800 seconds) — enforced by the launcher script
- Note: `openclaw agentTurn` CLI is blocked by plugin config, so the launcher triggers the cron job directly

```python
# Key structure
LOCK_FILE = "/tmp/podcast-queue.lock"
CRON_JOB_ID = "a79e58b0-f9bd-4911-86a7-44c01a1ae572"

def acquire_lock():
    # Check for existing lock, validate PID is alive
    # Write own PID to lock file

def release_lock():
    # Remove lock file

def main():
    if not acquire_lock():
        print("Another instance is running")
        return
    try:
        subprocess.run(["openclaw", "cron", "run", CRON_JOB_ID], timeout=1800)
    finally:
        release_lock()
```

#### 2. Cron Job Configuration

- **Schedule:** `40 8,10,12,14,16,18 * * *` (every 2 hours, :40 offset)
- **Timeout:** 1800 seconds (30 minutes)
- **Payload:** `agentTurn` on `work` agent with full pipeline instructions
- **Session target:** `isolated` (each run is independent)
- **Delivery:** announce to Telegram (`--channel telegram --target 49621692`)

The cron job uses `agentTurn` (not `sessions_spawn`) on the `work` agent. The agent itself handles the full pipeline via `exec` calls to Python scripts, with LLM translation in-context. Concurrency is controlled by the `run_pipeline.py` launcher, which can also be called manually or from the youtube-collector cron.

#### 3. agentTurn Task Payload

The `work` agent receives a task instructing it to process the podcast queue:

```
Process the next video from the podcast translation queue.

For each video:
1. Run `python3 queue_manager.py next` to get the next pending video
2. If no pending videos, report "Queue empty" and finish
3. Download: `yt-dlp -x --audio-format mp3 --audio-quality 0 -o "input/{id}.mp3" "https://youtube.com/watch?v={id}"`
4. Transcribe: `python3 scripts/transcribe_cached.py "input/{id}.mp3" transcripts/ small`
5. Prepare: `python3 scripts/prepare_transcript.py "transcripts/{id}.txt" "translations/{id}_ready.txt"`
6. Translate: Read the prepared transcript, translate EN→RU preserving technical terms. Remove unspeakable characters (CJK, etc.)
7. Write translation to `translations/{id}_ru_tts.txt` (clean text without timestamps, ready for TTS)
8. Generate TTS: `python3 scripts/generate_tts.py "translations/{id}_ru_tts.txt" "audio/{id}.ru.mp3"`
9. Report: `openclaw message send --channel telegram --target 49621692 --message "Completed: {title}"`
10. Mark complete: `python3 queue_manager.py complete {id}`
11. If error: `python3 queue_manager.py fail {id}` and continue to next video

Process ALL pending videos in sequence, then send a final summary.
```

#### 4. Translation Strategy

**Primary: LLM in-context translation**

The `work` agent reads the prepared transcript and produces a Russian translation. Benefits:
- Context-aware terminology (GPU, API, OpenAI stay in English)
- Natural sentence flow
- Speaker style matching

**Fallback: GoogleTranslator (deep_translator)**

If the transcript is too long for a single LLM turn, or the agent fails mid-translation:
- The `process-queue.py` script already uses `GoogleTranslator` as a standalone step
- The agent can fall back to: `python3 process-queue.py --translate-only {id}`

#### 5. Error Handling

- **Video download failure:** Mark as failed, continue to next video
- **Transcription failure:** Mark as failed, continue to next video
- **LLM translation failure:** Fall back to GoogleTranslator via exec
- **TTS generation failure:** Mark as failed, continue to next video
- **Agent timeout (30 min):** Launcher kills the process, releases lock
- **Concurrent invocation:** Lock file prevents overlap

#### 6. Timeout Configuration

- **Launcher timeout:** 1800 seconds (30 minutes)
- **agentTurn timeout:** Set via OpenClaw cron `timeoutSeconds: 1800`
- **Per-video timeout:** The agent monitors elapsed time and stops after ~25 minutes, sending a partial summary
- **Subprocess timeouts:** Already configured in `process-queue.py` (300s download, 7200s transcribe, 600s TTS)

### File Changes

| File | Action |
|------|--------|
| `run_pipeline.py` | **Create** — Python launcher with PID-lock for manual/cascaded invocation |
| `process-queue.py` | **Modify** — add `--translate-only` flag for GoogleTranslator fallback |
| `queue_manager.py` | No changes needed |
| `cron/jobs.json` | **Modify** — update queue-processor cron payload to full pipeline (agentTurn, no sessions_spawn), timeoutSeconds=1800 |
| `scripts/transcribe_cached.py` | No changes needed |
| `scripts/prepare_transcript.py` | No changes needed |
| `scripts/generate_tts.py` | No changes needed |

### Concurrency Control

The `run_pipeline.py` launcher uses a PID-lock file pattern:

1. Check `/tmp/podcast-queue.lock` — if exists, read PID
2. If PID is alive (`kill -0`), exit immediately
3. If PID is stale (process dead), remove stale lock
4. Write own PID to lock file
5. Run `openclaw cron run <queue-processor-id>` with 30-minute timeout
6. Release lock in `finally` block and `atexit`

This ensures:
- Only one queue processor runs at a time (no overlapping cron invocations)
- Stale locks are auto-cleaned
- Lock is always released, even on crash (atexit + finally)

### Telegram Reporting

After each video completes or fails:
```
openclaw message send --channel telegram --target 49621692 --message "✅ Done: {title}"
```
or
```
openclaw message send --channel telegram --target 49621692 --message "❌ Failed: {title} — {error}"
```

Final summary:
```
📊 Queue processed: 3 completed, 1 failed, 0 remaining
```

### What We're NOT Changing

- Global `agents.defaults.subagents.maxConcurrent` — stays at default
- `queue_manager.py` — no changes needed
- Individual pipeline scripts — no changes needed
- Other cron jobs — unaffected

## Out of Scope

- Parallel video processing (sequential is simpler and uses less memory on RPi)
- Auto-adding videos to queue (handled by youtube-collector cron)
- Voice selection UI (default Dmitry voice)
- Quality metrics or translation evaluation