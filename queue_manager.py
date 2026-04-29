#!/usr/bin/env python3
"""
YouTube Video Translation Queue Manager

Manages a queue of YouTube videos to translate, processing them one at a time.
"""

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path


class QueueManager:
    def __init__(self, queue_file=None):
        """Initialize queue manager with queue file path."""
        if queue_file is None:
            queue_file = os.path.join(
                os.path.dirname(__file__),
                "youtube-queue.json"
            )
        self.queue_file = Path(queue_file)
        self._ensure_queue_file()

    def _ensure_queue_file(self):
        """Create queue file if it doesn't exist."""
        if not self.queue_file.exists():
            self.queue_file.write_text(json.dumps({
                "pending": [],
                "processing": None,
                "completed": [],
                "failed": []
            }, indent=2))

    def _load_queue(self):
        """Load queue from file."""
        return json.loads(self.queue_file.read_text())

    def _save_queue(self, queue):
        """Save queue to file."""
        self.queue_file.write_text(json.dumps(queue, indent=2, ensure_ascii=False))

    def add_videos(self, videos):
        """Add videos to the pending queue.

        Args:
            videos: List of dicts with 'videoId', 'title', 'channel' keys
        """
        queue = self._load_queue()

        existing_ids = set(v["videoId"] for v in queue["pending"])
        existing_ids.update(v["videoId"] for v in queue["completed"])
        existing_ids.update(v["videoId"] for v in queue["failed"])
        if queue["processing"]:
            existing_ids.add(queue["processing"]["videoId"])

        added_count = 0
        for video in videos:
            if video["videoId"] not in existing_ids:
                video["addedAt"] = datetime.now(timezone.utc).isoformat()
                queue["pending"].append(video)
                added_count += 1

        self._save_queue(queue)
        return added_count

    def get_next_video(self):
        """Get the next video to process.

        Resets stale processing video first.

        Returns:
            Video dict or None if no pending videos
        """
        self.reset_stale()

        queue = self._load_queue()

        if not queue["pending"]:
            return None

        # Move first pending video to processing
        video = queue["pending"].pop(0)
        video["startedAt"] = datetime.now(timezone.utc).isoformat()
        queue["processing"] = video

        self._save_queue(queue)
        return video

    def mark_completed(self, video_id, output_files=None):
        """Mark a video as completed.

        Args:
            video_id: YouTube video ID
            output_files: Dict with paths to generated files
        """
        queue = self._load_queue()

        if queue["processing"] and queue["processing"]["videoId"] == video_id:
            video = queue["processing"]
            video["completedAt"] = datetime.now(timezone.utc).isoformat()
            if output_files:
                video["outputFiles"] = output_files
            queue["completed"].append(video)
            queue["processing"] = None

            self._save_queue(queue)
            return True

        return False

    def mark_failed(self, video_id, error):
        """Mark a video as failed.

        Args:
            video_id: YouTube video ID
            error: Error message
        """
        queue = self._load_queue()

        if queue["processing"] and queue["processing"]["videoId"] == video_id:
            video = queue["processing"]
            video["failedAt"] = datetime.now(timezone.utc).isoformat()
            video["error"] = error
            queue["failed"].append(video)
            queue["processing"] = None

            self._save_queue(queue)
            return True

        return False

    def reset_stale(self, max_minutes=30):
        """Return a stuck video from processing back to pending.

        If a video has been in processing for longer than max_minutes
        and no transcribe/python process is running for it, it's stale.

        Args:
            max_minutes: Maximum allowed time in processing (default 30)

        Returns:
            Dict with videoId and action taken, or None
        """
        queue = self._load_queue()

        if not queue["processing"]:
            return None

        video = queue["processing"]
        started_at = video.get("startedAt", "")
        if not started_at:
            return None

        try:
            started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
            elapsed_minutes = (datetime.now(timezone.utc) - started).total_seconds() / 60
        except (ValueError, TypeError):
            return None

        if elapsed_minutes <= max_minutes:
            return None

        # Check if any transcription process is actually running
        video_id = video["videoId"]
        try:
            result = subprocess.run(
                ["pgrep", "-f", f"transcribe.*{video_id}"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                # Process is alive, not stale
                return None
        except Exception:
            pass

        # Return to pending
        video.pop("startedAt", None)
        queue["pending"].insert(0, video)
        queue["processing"] = None
        self._save_queue(queue)

        return {"videoId": video_id, "action": "returned_to_pending", "stale_minutes": round(elapsed_minutes)}

    def get_status(self):
        """Get queue status.

        Returns:
            Dict with counts and current processing video
        """
        queue = self._load_queue()

        return {
            "pending": len(queue["pending"]),
            "processing": 1 if queue["processing"] else 0,
            "completed": len(queue["completed"]),
            "failed": len(queue["failed"]),
            "current": queue["processing"]
        }

    def clear_old_completed(self, days=7):
        """Remove completed entries older than specified days."""
        queue = self._load_queue()
        cutoff = datetime.now(timezone.utc).timestamp() - (days * 86400)

        old_completed = []
        new_completed = []

        for video in queue["completed"]:
            completed_time = datetime.fromisoformat(
                video["completedAt"].replace("Z", "+00:00")
            ).timestamp()
            if completed_time < cutoff:
                old_completed.append(video)
            else:
                new_completed.append(video)

        queue["completed"] = new_completed
        self._save_queue(queue)

        return len(old_completed)

    def clear_all_completed(self):
        """Remove ALL completed entries from queue."""
        queue = self._load_queue()
        cleared_count = len(queue["completed"])
        queue["completed"] = []
        self._save_queue(queue)
        return cleared_count


def main():
    """CLI interface for queue manager."""
    import sys

    if len(sys.argv) < 2:
        print("Usage: queue-manager.py <command> [args]")
        print("\nCommands:")
        print("  add <videoId> <title> <channel>  Add video to queue")
        print("  next                               Get next video to process")
        print("  complete <videoId>                 Mark video as completed")
        print("  fail <videoId> <error>             Mark video as failed")
        print("  status                             Show queue status")
        print("  reset-stale                        Return stuck video to pending")
        print("  clear-old [days]                   Clear old completed entries")
        sys.exit(1)

    command = sys.argv[1]
    qm = QueueManager()

    if command == "add":
        if len(sys.argv) < 5:
            print("Error: add requires videoId, title, and channel")
            sys.exit(1)
        video_id = sys.argv[2]
        title = sys.argv[3]
        channel = sys.argv[4]
        count = qm.add_videos([{
            "videoId": video_id,
            "title": title,
            "channel": channel
        }])
        print(f"Added {count} video(s) to queue")

    elif command == "next":
        video = qm.get_next_video()
        if video:
            # Check for --json flag
            if "--json" in sys.argv:
                print(json.dumps({
                    "videoId": video["videoId"],
                    "title": video["title"],
                    "channel": video["channel"],
                    "url": f"https://www.youtube.com/watch?v={video['videoId']}",
                    "startedAt": video.get("startedAt", "")
                }, indent=2, ensure_ascii=False))
            else:
                print(f"Processing: {video['title']}")
                print(f"Video ID: {video['videoId']}")
                print(f"Channel: {video['channel']}")
        else:
            if "--json" in sys.argv:
                print(json.dumps({"empty": True}))
            else:
                print("No videos in queue")

    elif command == "complete":
        if len(sys.argv) < 3:
            print("Error: complete requires videoId")
            sys.exit(1)
        video_id = sys.argv[2]
        if qm.mark_completed(video_id):
            print(f"Marked {video_id} as completed")
        else:
            print(f"Video {video_id} not in processing state")

    elif command == "fail":
        if len(sys.argv) < 4:
            print("Error: fail requires videoId and error message")
            sys.exit(1)
        video_id = sys.argv[2]
        error = " ".join(sys.argv[3:])
        if qm.mark_failed(video_id, error):
            print(f"Marked {video_id} as failed: {error}")
        else:
            print(f"Video {video_id} not in processing state")

    elif command == "status":
        status = qm.get_status()
        print(f"Queue Status:")
        print(f"  Pending: {status['pending']}")
        print(f"  Processing: {status['processing']}")
        print(f"  Completed: {status['completed']}")
        print(f"  Failed: {status['failed']}")
        if status["current"]:
            print(f"\nCurrently processing:")
            print(f"  {status['current']['title']}")
            print(f"  {status['current']['videoId']}")

    elif command == "reset-stale":
        result = qm.reset_stale()
        if result:
            print(f"Returned {result['videoId']} to pending (was stuck for {result['stale_minutes']} min)")
        else:
            print("No stale videos found")

    elif command == "clear-old":
        days = int(sys.argv[2]) if len(sys.argv) > 2 else 7
        cleared = qm.clear_old_completed(days)
        print(f"Cleared {cleared} old completed entries (>{days} days)")

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
