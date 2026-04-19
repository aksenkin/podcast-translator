#!/usr/bin/env python3
"""
YouTube Video Queue Processor for OpenClaw

Processes videos from the queue sequentially.
Subagent spawning is handled by the OpenClaw agent via sessions_spawn(agent="work").
This script only manages the queue — taking videos, marking completed/failed.

Usage:
  python3 queue_processor.py --max-videos 1 --json
  python3 queue_processor.py status
"""

import json
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))
from queue_manager import QueueManager


class QueueProcessor:
    def __init__(self, skill_dir=None):
        """Initialize queue processor."""
        if skill_dir is None:
            skill_dir = Path(__file__).parent
        self.skill_dir = Path(skill_dir)
        self.qm = QueueManager(self.skill_dir / "youtube-queue.json")

    def process_video(self):
        """
        Take the next video from the queue.
        Moves it from pending → processing and returns video info.

        Returns:
            Dict with video info or None if queue is empty
        """
        video = self.qm.get_next_video()

        if not video:
            return None

        video_id = video['videoId']
        youtube_url = f"https://www.youtube.com/watch?v={video_id}"

        print(f"📹 Processing: {video['title']}")
        print(f"📺 Channel: {video['channel']}")
        print(f"🆔 ID: {video_id}")
        print(f"🔗 URL: {youtube_url}")

        return {
            "videoId": video_id,
            "title": video['title'],
            "channel": video['channel'],
            "url": youtube_url,
            "startedAt": video.get('startedAt', '')
        }

    def run(self, max_videos=1, json_output=False):
        """
        Process pending videos from the queue.

        Takes videos from pending → processing one at a time.
        The OpenClaw agent handles subagent spawning via sessions_spawn.

        Args:
            max_videos: Maximum number of videos to process (default: 1)
            json_output: Output results as JSON

        Returns:
            Dict with processing results
        """
        start_time = datetime.now()
        print(f"🚀 Queue Processor Started at {start_time.strftime('%H:%M:%S')}")

        # Time window check: only process between 08:30 and 20:00
        current_hour = start_time.hour
        current_minute = start_time.minute
        current_time = current_hour * 100 + current_minute

        if current_time < 830 or current_time >= 2000:
            print(f"⏰ Current time: {start_time.strftime('%H:%M')}")
            print(f"⚠️  Outside processing window (08:30-20:00)")
            print(f"📊 Queue check only — skipping processing\n")

            status = self.qm.get_status()
            result = {
                "success": True,
                "skipped": True,
                "reason": "outside_processing_window",
                "message": f"Current time {start_time.strftime('%H:%M')} is outside processing window (08:30-20:00)",
                "queue_status": status,
                "processed": 0
            }

            if json_output:
                print(json.dumps(result, indent=2, ensure_ascii=False))

            return result

        print(f"✅ Within processing window (08:30-20:00)")
        print(f"⏰ Max videos to process: {max_videos}\n")

        # Show initial status
        status = self.qm.get_status()
        print(f"📊 Queue Status:")
        print(f"   Pending: {status['pending']}")
        print(f"   Processing: {status['processing']}")
        print(f"   Completed: {status['completed']}")
        print(f"   Failed: {status['failed']}")

        if status['pending'] == 0:
            result = {
                "success": True,
                "message": "Queue is empty",
                "processed": 0,
                "videos": []
            }
            if json_output:
                print(json.dumps(result, indent=2, ensure_ascii=False))
            return result

        # Take videos from queue (pending → processing)
        videos = []
        for i in range(max_videos):
            video_info = self.process_video()
            if video_info:
                videos.append(video_info)
            else:
                break

        result = {
            "success": True,
            "processed": len(videos),
            "videos": videos,
            "queue_status": self.qm.get_status()
        }

        if json_output:
            print(json.dumps(result, indent=2, ensure_ascii=False))

        return result


def main():
    """Main entry point for queue processor."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Process YouTube video translation queue"
    )
    parser.add_argument(
        "--max-videos",
        type=int,
        default=1,
        help="Maximum number of videos to process (default: 1)"
    )
    parser.add_argument(
        "--json-output",
        action="store_true",
        help="Output results as JSON"
    )
    parser.add_argument(
        "command",
        nargs="?",
        default=None,
        help="Optional command: 'status' to show queue status"
    )

    args = parser.parse_args()

    processor = QueueProcessor()

    if args.command == "status":
        status = processor.qm.get_status()
        print(f"Queue Status:")
        print(f"  Pending: {status['pending']}")
        print(f"  Processing: {status['processing']}")
        print(f"  Completed: {status['completed']}")
        print(f"  Failed: {status['failed']}")
        if status["current"]:
            print(f"\nCurrently processing:")
            print(f"  {status['current']['title']}")
            print(f"  {status['current']['videoId']}")
        return

    result = processor.run(max_videos=args.max_videos, json_output=args.json_output)

    # Exit with error code if processing failed
    if not result['success']:
        sys.exit(1)


if __name__ == "__main__":
    main()