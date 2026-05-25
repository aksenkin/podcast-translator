#!/usr/bin/env python3
"""
Rename MP3 file from video ID to human-readable title.

Usage:
    python3 rename_with_title.py <video_id> <title>

Example:
    python3 rename_with_title.py 9N3jEavj5Ps "Anthropic Just Reset AI Expectations"
"""

import os
import sys
import re
from pathlib import Path


def sanitize_filename(title, max_length=100):
    """Sanitize title for use as filename.
    
    Removes special characters, keeps spaces and basic punctuation.
    """
    # Remove characters that are invalid in filenames
    sanitized = re.sub(r'[<>:"/\\|?*]', '', title)
    # Remove control characters
    sanitized = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', sanitized)
    # Trim whitespace
    sanitized = sanitized.strip()
    # Limit length
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length].strip()
    return sanitized


def rename_mp3(video_id, title, audio_dir="audio"):
    """Rename MP3 from video ID to title.
    
    Args:
        video_id: YouTube video ID
        title: Video title for new filename
        audio_dir: Directory containing audio files
    
    Returns:
        Dict with result
    """
    audio_path = Path(audio_dir)
    
    # Source file (with ID)
    source = audio_path / f"{video_id}.ru.mp3"
    
    # Target file (with title)
    safe_title = sanitize_filename(title)
    target = audio_path / f"{safe_title}.ru.mp3"
    
    if not source.exists():
        return {
            "success": False,
            "error": f"Source file not found: {source}"
        }
    
    if target.exists():
        # Already renamed or same name
        if source.samefile(target):
            return {
                "success": True,
                "message": "File already has correct name",
                "file": str(target)
            }
        return {
            "success": False,
            "error": f"Target file already exists: {target}"
        }
    
    try:
        os.rename(source, target)
        return {
            "success": True,
            "from": str(source),
            "to": str(target),
            "file": str(target)
        }
    except OSError as e:
        return {
            "success": False,
            "error": f"Rename failed: {e}"
        }


def main():
    if len(sys.argv) < 3:
        print("Usage: rename_with_title.py <video_id> <title>")
        print("")
        print("Example:")
        print('  python3 rename_with_title.py 9N3jEavj5Ps "Anthropic Just Reset AI Expectations"')
        sys.exit(1)
    
    video_id = sys.argv[1]
    title = sys.argv[2]
    audio_dir = sys.argv[3] if len(sys.argv) > 3 else "audio"
    
    result = rename_mp3(video_id, title, audio_dir)
    
    import json
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    sys.exit(0 if result["success"] else 1)


if __name__ == "__main__":
    main()
