#!/usr/bin/env python3
"""
Shared logging helper for podcast-translator scripts.

Writes structured log entries to per-video log files.
Format: [YYYY-MM-DD HH:MM:SS] EVENT key=value key=value
"""

import os
from datetime import datetime
from pathlib import Path

LOG_DIR = Path(__file__).parent.parent / "logs"


def log_event(video_id, event, **kwargs):
    """Append a structured log entry for a video.

    Args:
        video_id: YouTube video ID
        event: Event name (e.g. CHUNK_START, TRANSCRIBE_OK)
        **kwargs: Key-value pairs to include
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / f"{video_id}.log"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    parts = [f"{k}={v}" for k, v in kwargs.items()]
    line = f"[{timestamp}] {event}"
    if parts:
        line += " " + " ".join(parts)
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(line + "\n")