#!/usr/bin/env python3
"""
Transcribe chunks from the chunk queue.

Reads {videoId}_chunks.json, finds pending chunks,
transcribes them with faster-whisper, updates status.

Usage:
    python3 transcribe_chunk.py {videoId}           # one chunk
    python3 transcribe_chunk.py --all {videoId}     # all pending chunks (model loaded once)

Output (JSON to stdout):
    {"chunk": 3, "totalChunks": 7, "status": "done", "pending": 4}
    {"chunk": 3, "totalChunks": 7, "status": "failed", "error": "...", "pending": 4}
    {"allDone": true, "videoId": "...", "totalChunks": 7}
    {"error": "no_chunks_json"}
    {"error": "all_chunks_processed"}
"""

import json
import os
import signal
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from log_helper import log_event

LOCK_FILE = Path("/tmp/transcribe_chunk.lock")

CHUNKS_DIR = Path(__file__).parent.parent / "chunks"

CACHE_DIR = Path.home() / ".cache" / "huggingface" / "hub"


def load_chunks_meta(video_id):
    """Load chunks metadata JSON."""
    chunks_json = CHUNKS_DIR / f"{video_id}_chunks.json"
    if not chunks_json.exists():
        return None
    return json.loads(chunks_json.read_text())


def save_chunks_meta(video_id, data):
    """Save chunks metadata JSON."""
    chunks_json = CHUNKS_DIR / f"{video_id}_chunks.json"
    chunks_json.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def transcribe_chunk_with_model(model, chunk_file, output_dir):
    """Transcribe a single chunk using a pre-loaded model.

    Args:
        model: Loaded WhisperModel instance
        chunk_file: Path to chunk MP3
        output_dir: Directory for transcript output

    Returns:
        Tuple of (success: bool, segment_count: int, error: str or None)
    """
    try:
        segments, info = model.transcribe(
            str(chunk_file),
            beam_size=1,
            vad_filter=False,
            word_timestamps=False,
            language=None
        )
    except Exception as e:
        return False, 0, f"Transcription error: {e}"

    if not info:
        return False, 0, "No info object returned"

    chunk_basename = Path(chunk_file).stem
    transcript_file = Path(output_dir) / f"{chunk_basename}.txt"
    segment_count = 0

    with open(transcript_file, 'w', encoding='utf-8') as f:
        for segment in segments:
            segment_count += 1
            minutes_start = int(segment.start // 60)
            seconds_start = int(segment.start % 60)
            minutes_end = int(segment.end // 60)
            seconds_end = int(segment.end % 60)
            f.write(f"[{minutes_start:02d}:{seconds_start:02d} - {minutes_end:02d}:{seconds_end:02d}] {segment.text}\n")

    return True, segment_count, None


def transcribe_next_chunk(video_id):
    """Find and transcribe the next pending chunk (loads model each call).

    Args:
        video_id: YouTube video ID

    Returns:
        Dict with result
    """
    data = load_chunks_meta(video_id)
    if data is None:
        return {"error": "no_chunks_json", "videoId": video_id}

    target_chunk = None
    for chunk in data["chunks"]:
        if chunk["status"] == "pending":
            target_chunk = chunk
            break

    if target_chunk is None:
        all_done = all(c["status"] == "done" for c in data["chunks"])
        any_failed = any(c["status"] == "failed" for c in data["chunks"])

        if all_done:
            data["status"] = "assembling"
            save_chunks_meta(video_id, data)
            return {"allDone": True, "videoId": video_id, "totalChunks": data["totalChunks"]}
        elif any_failed:
            return {"error": "chunk_failed", "videoId": video_id}
        else:
            return {"error": "all_chunks_processed", "videoId": video_id}

    target_chunk["status"] = "transcribing"
    save_chunks_meta(video_id, data)

    chunk_idx = target_chunk["index"]
    total = data["totalChunks"]
    chunk_file = CHUNKS_DIR / target_chunk["file"]

    log_event(video_id, "TRANSCRIBE_START",
              chunk=f"{chunk_idx}/{total}",
              file=target_chunk["file"])

    from faster_whisper import WhisperModel
    try:
        model = WhisperModel(
            "small", device="cpu", compute_type="int8",
            download_root=str(CACHE_DIR), cpu_threads=4, num_workers=2
        )
    except Exception as e:
        target_chunk["status"] = "failed"
        data["status"] = "failed"
        save_chunks_meta(video_id, data)
        log_event(video_id, "TRANSCRIBE_FAIL", chunk=f"{chunk_idx}/{total}", error=f"Model load failed: {e}")
        return {"chunk": chunk_idx, "totalChunks": total, "status": "failed", "error": f"Model load failed: {e}"}

    start_time = time.time()
    success, _, error = transcribe_chunk_with_model(model, chunk_file, str(CHUNKS_DIR))
    elapsed = time.time() - start_time

    if success:
        target_chunk["status"] = "done"
        log_event(video_id, "TRANSCRIBE_OK", chunk=f"{chunk_idx}/{total}", duration=f"{elapsed:.0f}s")

        pending_count = sum(1 for c in data["chunks"] if c["status"] == "pending")
        if pending_count == 0 and all(c["status"] == "done" for c in data["chunks"]):
            data["status"] = "assembling"
            save_chunks_meta(video_id, data)
            return {"allDone": True, "videoId": video_id, "totalChunks": total}

        save_chunks_meta(video_id, data)
        return {"chunk": chunk_idx, "totalChunks": total, "status": "done", "pending": pending_count}
    else:
        target_chunk["status"] = "failed"
        data["status"] = "failed"
        save_chunks_meta(video_id, data)
        log_event(video_id, "TRANSCRIBE_FAIL", chunk=f"{chunk_idx}/{total}", error=error, duration=f"{elapsed:.0f}s")
        return {"chunk": chunk_idx, "totalChunks": total, "status": "failed", "error": error,
                "pending": sum(1 for c in data["chunks"] if c["status"] == "pending")}


def transcribe_all_chunks(video_id):
    """Transcribe all pending chunks, loading the model once.

    Args:
        video_id: YouTube video ID

    Returns:
        Dict with summary
    """
    data = load_chunks_meta(video_id)
    if data is None:
        return {"error": "no_chunks_json", "videoId": video_id}

    pending = [c for c in data["chunks"] if c["status"] == "pending"]
    if not pending:
        all_done = all(c["status"] == "done" for c in data["chunks"])
        if all_done:
            data["status"] = "assembling"
            save_chunks_meta(video_id, data)
            return {"allDone": True, "videoId": video_id, "totalChunks": data["totalChunks"]}
        return {"error": "all_chunks_processed", "videoId": video_id}

    from faster_whisper import WhisperModel

    log_event(video_id, "TRANSCRIBE_ALL_START", pending=len(pending))
    start_total = time.time()

    log_event(video_id, "MODEL_LOAD_START")
    try:
        model = WhisperModel(
            "small", device="cpu", compute_type="int8",
            download_root=str(CACHE_DIR), cpu_threads=4, num_workers=2
        )
    except Exception as e:
        log_event(video_id, "MODEL_LOAD_FAIL", error=str(e))
        return {"error": f"Model load failed: {e}"}

    model_load_time = time.time() - start_total
    log_event(video_id, "MODEL_LOAD_OK", duration=f"{model_load_time:.1f}s")

    results = []
    for chunk in pending:
        chunk_idx = chunk["index"]
        total = data["totalChunks"]
        chunk_file = CHUNKS_DIR / chunk["file"]

        chunk["status"] = "transcribing"
        save_chunks_meta(video_id, data)

        log_event(video_id, "TRANSCRIBE_START", chunk=f"{chunk_idx}/{total}", file=chunk["file"])
        start = time.time()

        success, segments, error = transcribe_chunk_with_model(model, chunk_file, str(CHUNKS_DIR))
        elapsed = time.time() - start

        if success:
            chunk["status"] = "done"
            log_event(video_id, "TRANSCRIBE_OK", chunk=f"{chunk_idx}/{total}",
                      duration=f"{elapsed:.0f}s", segments=segments)
            results.append({"chunk": chunk_idx, "status": "done", "duration": f"{elapsed:.0f}s"})
        else:
            chunk["status"] = "failed"
            data["status"] = "failed"
            save_chunks_meta(video_id, data)
            log_event(video_id, "TRANSCRIBE_FAIL", chunk=f"{chunk_idx}/{total}", error=error, duration=f"{elapsed:.0f}s")
            return {"error": "chunk_failed", "videoId": video_id, "failedChunk": chunk_idx,
                    "completed": [r for r in results if r["status"] == "done"]}

        save_chunks_meta(video_id, data)

    total_elapsed = time.time() - start_total
    all_done = all(c["status"] == "done" for c in data["chunks"])

    if all_done:
        data["status"] = "assembling"
        save_chunks_meta(video_id, data)
        log_event(video_id, "TRANSCRIBE_ALL_OK", total_duration=f"{total_elapsed:.0f}s", chunks=len(results))
        return {"allDone": True, "videoId": video_id, "totalChunks": data["totalChunks"],
                "transcribed": len(results), "totalDuration": f"{total_elapsed:.0f}s"}

    save_chunks_meta(video_id, data)
    return {"videoId": video_id, "transcribed": len(results), "totalDuration": f"{total_elapsed:.0f}s"}


def acquire_lock():
    """Acquire PID-lock to prevent parallel transcription. Returns True if acquired."""
    if LOCK_FILE.exists():
        try:
            old_pid = int(LOCK_FILE.read_text().strip())
            os.kill(old_pid, 0)  # Check if process is alive
            return False  # Lock held by running process
        except (OSError, ProcessLookupError, ValueError):
            LOCK_FILE.unlink(missing_ok=True)  # Stale lock
    LOCK_FILE.write_text(str(os.getpid()))
    return True


def release_lock():
    """Release PID-lock."""
    try:
        LOCK_FILE.unlink(missing_ok=True)
    except OSError:
        pass


if __name__ == "__main__":
    # Lower process priority to avoid hogging CPU on ARM
    os.nice(10)

    # Parse --all flag
    do_all = "--all" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--all"]

    if not args:
        print("Usage: python3 transcribe_chunk.py [--all] <videoId>")
        print("")
        print("  <videoId>        Transcribe one pending chunk")
        print("  --all <videoId>  Transcribe all pending chunks (model loaded once)")
        sys.exit(1)

    video_id = args[0]

    # Acquire lock (prevent parallel runs)
    if not acquire_lock():
        existing_pid = LOCK_FILE.read_text().strip()
        print(json.dumps({"error": f"already_running", "pid": int(existing_pid)}))
        sys.exit(0)

    try:
        # Set timeout: 10 min per chunk or 60 min for --all
        timeout = 3600 if do_all else 600

        def timeout_handler(signum, frame):
            log_event(video_id, "TRANSCRIBE_FAIL", chunk="?" if not do_all else "*",
                      error=f"timeout ({timeout // 60} min)")
            print(json.dumps({"status": "failed", "error": f"timeout ({timeout // 60} min)"}))
            sys.exit(2)

        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(timeout)

        if do_all:
            result = transcribe_all_chunks(video_id)
        else:
            result = transcribe_next_chunk(video_id)

        print(json.dumps(result, indent=2, ensure_ascii=False))
        signal.alarm(0)

        if "error" in result and result.get("error") not in ("all_chunks_processed",):
            sys.exit(1)
    finally:
        release_lock()