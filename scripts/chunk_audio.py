#!/usr/bin/env python3
"""
Split long audio files into 5-minute chunks for transcription.

Uses ffprobe to check duration, ffmpeg to split.
Creates a _chunks.json metadata file for the chunk queue.

Usage:
    python3 chunk_audio.py input/{videoId}.mp3 [--chunk-duration 300]

Output (JSON to stdout):
    {"chunking": true, "totalChunks": 7, "chunksFile": "chunks/..._chunks.json"}
    {"chunking": false, "reason": "duration_below_threshold", "duration": 180}
    {"error": "too_short", "duration": 25}
    {"error": "too_long", "duration": 8000}
"""

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from log_helper import log_event

CHUNKS_DIR = Path(__file__).parent.parent / "chunks"
MIN_DURATION = 30       # seconds — skip videos shorter than this
MAX_DURATION = 7200     # seconds (2h) — skip videos longer than this
DEFAULT_CHUNK_DURATION = 300  # 5 minutes


def get_audio_duration(audio_file):
    """Get audio duration in seconds using ffprobe."""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(audio_file)],
        capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None
    try:
        return float(result.stdout.strip())
    except ValueError:
        return None


def check_disk_space(audio_file, total_chunks):
    """Check if there's enough disk space for chunk files."""
    try:
        file_size = os.path.getsize(audio_file)
        # Each chunk is roughly file_size / total_duration * chunk_duration
        # Add 20% buffer
        needed = int(file_size * 1.2)
        stat = os.statvfs(str(CHUNKS_DIR.parent))
        available = stat.f_bavail * stat.f_frsize
        return available > needed
    except Exception:
        return True  # Skip check if we can't determine


def chunk_audio(audio_file, chunk_duration=DEFAULT_CHUNK_DURATION):
    """Split audio file into chunks and create metadata file.

    Args:
        audio_file: Path to the MP3 file
        chunk_duration: Duration of each chunk in seconds

    Returns:
        Dict with result info
    """
    audio_path = Path(audio_file)
    video_id = audio_path.stem  # e.g. "jblguhXunZs" from "jblguhXunZs.mp3"

    log_event(video_id, "CHUNK_START", total="?", duration="?", chunk_size=f"{chunk_duration}s")

    # Get duration
    duration = get_audio_duration(audio_path)
    if duration is None:
        error_msg = f"Cannot determine audio duration: {audio_path}"
        log_event(video_id, "CHUNK_FAIL", error=error_msg)
        return {"error": "ffprobe_failed", "message": error_msg}

    log_event(video_id, "CHUNK_START", total="?", duration=f"{duration:.1f}s", chunk_size=f"{chunk_duration}s")

    # Check duration thresholds
    if duration < MIN_DURATION:
        log_event(video_id, "CHUNK_SKIP", reason="too_short", duration=f"{duration:.1f}s")
        return {"error": "too_short", "duration": round(duration, 1)}

    if duration > MAX_DURATION:
        log_event(video_id, "CHUNK_SKIP", reason="too_long", duration=f"{duration:.1f}s")
        return {"error": "too_long", "duration": round(duration, 1)}

    # No chunking needed for short audio
    if duration <= chunk_duration:
        log_event(video_id, "CHUNK_SKIP", reason="duration_below_threshold", duration=f"{duration:.1f}s")
        return {"chunking": False, "reason": "duration_below_threshold", "duration": round(duration, 1)}

    # Calculate number of chunks
    total_chunks = int(duration / chunk_duration) + (1 if duration % chunk_duration > 0 else 0)

    # Check disk space
    if not check_disk_space(audio_path, total_chunks):
        error_msg = f"Not enough disk space for {total_chunks} chunks"
        log_event(video_id, "CHUNK_FAIL", error=error_msg)
        return {"error": "disk_space", "message": error_msg}

    # Create chunks directory
    CHUNKS_DIR.mkdir(parents=True, exist_ok=True)

    # Create chunk files using ffmpeg
    chunks_meta = []
    for i in range(total_chunks):
        start_time = i * chunk_duration
        chunk_file = CHUNKS_DIR / f"{video_id}_chunk{i+1:03d}.mp3"

        log_event(video_id, "CHUNK_CREATE", chunk=f"{i+1}/{total_chunks}", file=chunk_file.name)

        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", str(audio_path),
                "-ss", str(start_time),
                "-t", str(chunk_duration),
                "-c", "copy",
                "-avoid_negative_ts", "1",
                str(chunk_file)
            ],
            capture_output=True, text=True, timeout=120
        )

        if result.returncode != 0:
            error_msg = f"ffmpeg chunk {i+1} failed: {result.stderr[:200]}"
            log_event(video_id, "CHUNK_CREATE_FAIL", chunk=f"{i+1}/{total_chunks}", error=error_msg)
            # Clean up partial chunks
            for meta in chunks_meta:
                p = CHUNKS_DIR / meta["file"]
                if p.exists():
                    p.unlink()
            if chunk_file.exists():
                chunk_file.unlink()
            return {"error": "chunk_failed", "chunk": i + 1, "message": error_msg}

        chunks_meta.append({
            "index": i + 1,
            "file": chunk_file.name,
            "startOffset": start_time,
            "status": "pending"
        })

    log_event(video_id, "CHUNK_ALL_CREATED", total=total_chunks)

    # Write chunks metadata
    chunks_data = {
        "videoId": video_id,
        "totalChunks": total_chunks,
        "chunkDuration": chunk_duration,
        "sourceDuration": round(duration, 1),
        "status": "transcribing",
        "chunks": chunks_meta
    }

    chunks_json = CHUNKS_DIR / f"{video_id}_chunks.json"
    chunks_json.write_text(json.dumps(chunks_data, indent=2, ensure_ascii=False))

    return {
        "chunking": True,
        "totalChunks": total_chunks,
        "chunksFile": str(chunks_json)
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 chunk_audio.py <audio_file> [--chunk-duration 300]")
        print("")
        print("Splits audio into chunks if longer than chunk-duration seconds.")
        print("Outputs JSON to stdout.")
        sys.exit(1)

    audio_file = sys.argv[1]
    chunk_dur = DEFAULT_CHUNK_DURATION

    if "--chunk-duration" in sys.argv:
        idx = sys.argv.index("--chunk-duration")
        if idx + 1 < len(sys.argv):
            chunk_dur = int(sys.argv[idx + 1])

    result = chunk_audio(audio_file, chunk_dur)
    print(json.dumps(result, indent=2, ensure_ascii=False))

    if "error" in result:
        sys.exit(1)