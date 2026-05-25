#!/usr/bin/env python3
"""
YouTube Video Queue Processor for OpenClaw

Processes videos from the queue sequentially with retry support.
Failed videos are returned to queue (up to 3 attempts).
After 3 failures, sends Telegram notification.

Usage:
  python3 process-queue.py --max-videos 1 --json
  python3 process-queue.py status
  python3 process-queue.py check-notify  # Check for failed videos needing notification
"""

import json
import sys
import os
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))
from queue_manager import QueueManager


def send_telegram_message(message, target="49621692"):
    """Send message via OpenClaw CLI."""
    try:
        os.system(f'openclaw message send --channel telegram --target {target} --message "{message}"')
    except Exception as e:
        print(f"Failed to send Telegram message: {e}")


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
        
        if video.get('attempts', 0) > 0:
            print(f"🔄 Retry attempt: {video['attempts']}/3")
        if video.get('lastError'):
            print(f"⚠️  Last error: {video['lastError'][:80]}...")

        return {
            "videoId": video_id,
            "title": video['title'],
            "channel": video['channel'],
            "url": youtube_url,
            "startedAt": video.get('startedAt', ''),
            "attempts": video.get('attempts', 0)
        }

    def mark_failed_with_retry(self, video_id, error):
        """Mark video as failed with automatic retry logic.
        
        Returns True if video was returned to queue for retry.
        Returns False if video permanently failed (3+ attempts).
        """
        result = self.qm.mark_failed(video_id, error)
        
        if result["action"] == "retry":
            print(f"⚠️  Video failed (attempt {result['attempts']}/3), returned to queue")
            return True
        elif result["action"] == "failed":
            print(f"❌ Video PERMANENTLY FAILED after {result['attempts']} attempts")
            
            # Send Telegram notification
            title = result.get('title', 'Unknown')
            error_msg = result.get('lastError', 'Unknown error')
            notification = (
                f"🚨 Видео НЕ УДАЛОСЬ перевести после 3 попыток:\n\n"
                f"📹 {title}\n"
                f"🆔 {video_id}\n"
                f"❌ Ошибка: {error_msg[:200]}\n\n"
                f"Попробуй перевести вручную или проверь логи."
            )
            send_telegram_message(notification)
            return False
        
        return True  # not_found case

    def check_failed_notifications(self):
        """Check for videos that failed 3+ times and send notifications.
        
        Returns:
            List of notified videos
        """
        failed = self.qm.get_failed_for_notification()
        notified = []
        
        for video in failed:
            title = video.get('title', 'Unknown')
            video_id = video['videoId']
            error = video.get('lastError', 'Unknown error')
            attempts = video.get('attempts', 0)
            
            notification = (
                f"🚨 Видео НЕ УДАЛОСЬ перевести после {attempts} попыток:\n\n"
                f"📹 {title}\n"
                f"🆔 {video_id}\n"
                f"❌ Ошибка: {error[:200]}\n\n"
                f"Попробуй перевести вручную или проверь логи."
            )
            
            send_telegram_message(notification)
            self.qm.mark_notified(video_id)
            notified.append(video_id)
        
        return notified

    def run(self, max_videos=1, json_output=False):
        """
        Process pending videos from the queue.

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
        status = self.qm.get_detailed_status()
        print(f"📊 Queue Status:")
        print(f"   Pending: {status['pending']} ({status['pending_with_retries']} with retries)")
        print(f"   Processing: {status['processing']}")
        print(f"   Completed: {status['completed']}")
        print(f"   Failed: {status['failed']}")
        print(f"   Notified: {status['notified']}")

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
        help="Optional command: 'status', 'check-notify'"
    )

    args = parser.parse_args()

    processor = QueueProcessor()

    if args.command == "status":
        status = processor.qm.get_detailed_status()
        print(f"Queue Status (Detailed):")
        print(f"  Pending: {status['pending']} ({status['pending_with_retries']} with retries)")
        print(f"  Processing: {status['processing']}")
        print(f"  Completed: {status['completed']}")
        print(f"  Failed: {status['failed']}")
        print(f"  Notified: {status['notified']}")
        if status["current"]:
            print(f"\nCurrently processing:")
            print(f"  {status['current']['title']}")
            print(f"  {status['current']['videoId']}")
            if status['current'].get('attempts', 0) > 0:
                print(f"  Retry attempt: {status['current']['attempts']}/3")
        if status["retry_videos"]:
            print(f"\nVideos awaiting retry:")
            for v in status["retry_videos"]:
                print(f"  - {v['title']} (attempt {v['attempts']}/3)")
        return

    elif args.command == "check-notify":
        print("Checking for failed videos needing notification...")
        notified = processor.check_failed_notifications()
        if notified:
            print(f"Sent notifications for {len(notified)} video(s): {', '.join(notified)}")
        else:
            print("No videos needing notification")
        return

    result = processor.run(max_videos=args.max_videos, json_output=args.json_output)

    # Exit with error code if processing failed
    if not result['success']:
        sys.exit(1)


if __name__ == "__main__":
    main()
