#!/usr/bin/env python3
"""
Simplified test agent for podcast translation
Processes one video with minimal task
"""

import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path("/home/clawd/.openclaw/workspace/skills/podcast-translator")

def test_simple_agent():
    """Test agent with simplified task"""

    # Use the video that failed last
    youtube_url = "https://www.youtube.com/watch?v=tZ2B3itsgUw"

    # Create a minimal task - just download and report
    simple_task = f"""## Test Task: Download Audio

⚠️ CRITICAL: Do NOT install any software.

Download audio from this YouTube video: {youtube_url}

Steps:
1. Go to directory: {SKILL_DIR}
2. Download audio: yt-dlp -x --audio-format mp3 --audio-quality 0 -o "input/test_$(date +%Y%m%d_%H%M%S).mp3" "{youtube_url}"
3. Report SUCCESS with the filename

That's it - just download and report."""

    print("🧪 Testing simplified agent task...")
    print(f"📺 Video: {youtube_url}")

    result = subprocess.run(
        [
            "openclaw",
            "agent",
            "--agent", "claude",
            "--local",
            "--message", simple_task,
            "--timeout", "600"  # 10 minutes
        ],
        capture_output=True,
        text=True,
        timeout=610,
        cwd=str(SKILL_DIR)
    )

    print("\n📊 RESULT:")
    print(f"Exit code: {result.returncode}")
    print(f"\nSTDOUT:\n{result.stdout}")
    print(f"\nSTDERR:\n{result.stderr}")

    return result.returncode == 0

if __name__ == "__main__":
    success = test_simple_agent()
    sys.exit(0 if success else 1)
