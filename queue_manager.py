#!/usr/bin/env python3
"""
YouTube Video Translation Queue Manager

Manages a queue of YouTube videos to translate, processing them one at a time.
Features:
- Retry logic: failed videos return to pending queue
- Attempt counter: tracks how many times video was tried
- Last error tracking: stores error message for debugging
- Notification threshold: alerts after 3 failed attempts
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
                "failed": [],
                "notified": []  # Videos with 3+ attempts that were already reported
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
        existing_ids.update(v["videoId"] for v in queue.get("notified", []))
        if queue["processing"]:
            existing_ids.add(queue["processing"]["videoId"])

        added_count = 0
        for video in videos:
            if video["videoId"] not in existing_ids:
                video["addedAt"] = datetime.now(timezone.utc).isoformat()
                video["attempts"] = 0  # Initialize attempt counter
                video["lastError"] = None
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
        if "attempts" not in video:
            video["attempts"] = 0
        if "lastError" not in video:
            video["lastError"] = None
        if "statusHistory" not in video:
            video["statusHistory"] = []
        
        video["statusHistory"].append({
            "status": "processing",
            "timestamp": video["startedAt"]
        })
        
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
            video["attempts"] = video.get("attempts", 0) + 1
            if output_files:
                video["outputFiles"] = output_files
            
            video["statusHistory"] = video.get("statusHistory", [])
            video["statusHistory"].append({
                "status": "completed",
                "timestamp": video["completedAt"]
            })
            
            queue["completed"].append(video)
            queue["processing"] = None

            self._save_queue(queue)
            return True

        return False

    def mark_failed(self, video_id, error):
        """Mark a video as failed with retry logic.
        
        If video has < 3 attempts, returns it to pending queue.
        If video has >= 3 attempts, moves it to failed queue and returns notification info.

        Args:
            video_id: YouTube video ID
            error: Error message

        Returns:
            Dict with action taken:
            - "action": "retry" if returned to pending
            - "action": "failed" if moved to failed (3+ attempts)
            - "action": "not_found" if video not in processing
            - "video": video dict (for "failed" action, includes attempts)
        """
        queue = self._load_queue()

        if not queue["processing"] or queue["processing"]["videoId"] != video_id:
            return {"action": "not_found"}

        video = queue["processing"]
        video["failedAt"] = datetime.now(timezone.utc).isoformat()
        video["lastError"] = error
        video["attempts"] = video.get("attempts", 0) + 1
        
        video["statusHistory"] = video.get("statusHistory", [])
        video["statusHistory"].append({
            "status": "failed",
            "timestamp": video["failedAt"],
            "error": error
        })

        queue["processing"] = None

        if video["attempts"] < 3:
            # Return to pending for retry
            # Remove stale timestamps that will be regenerated on next attempt
            video.pop("startedAt", None)
            video.pop("failedAt", None)
            video.pop("statusHistory", None)  # Keep history? No, too large for repeated retries
            
            queue["pending"].insert(0, video)  # Put at front for immediate retry
            self._save_queue(queue)
            return {
                "action": "retry",
                "videoId": video_id,
                "attempts": video["attempts"],
                "lastError": error
            }
        else:
            # 3+ attempts, move to failed
            queue["failed"].append(video)
            self._save_queue(queue)
            return {
                "action": "failed",
                "videoId": video_id,
                "title": video.get("title", "Unknown"),
                "attempts": video["attempts"],
                "lastError": error
            }

    def mark_notified(self, video_id):
        """Mark a failed video as already notified.
        
        Moves video from failed to notified list.
        
        Args:
            video_id: YouTube video ID
        """
        queue = self._load_queue()
        
        # Find in failed list
        failed_video = None
        for i, video in enumerate(queue["failed"]):
            if video["videoId"] == video_id:
                failed_video = queue["failed"].pop(i)
                break
        
        if failed_video:
            if "notified" not in queue:
                queue["notified"] = []
            failed_video["notifiedAt"] = datetime.now(timezone.utc).isoformat()
            queue["notified"].append(failed_video)
            self._save_queue(queue)
            return True
        
        return False

    def get_failed_for_notification(self):
        """Get videos that have failed 3+ times and need notification.
        
        Returns:
            List of video dicts with attempts >= 3
        """
        queue = self._load_queue()
        return [v for v in queue.get("failed", []) if v.get("attempts", 0) >= 3]

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

        # Return to pending (increment attempt count since this is a failure)
        video["attempts"] = video.get("attempts", 0) + 1
        video["lastError"] = f"Stale reset after {round(elapsed_minutes)} minutes"
        video.pop("startedAt", None)
        
        if video["attempts"] >= 3:
            # Too many stale resets, move to failed
            video["failedAt"] = datetime.now(timezone.utc).isoformat()
            queue["failed"].append(video)
            queue["processing"] = None
            self._save_queue(queue)
            return {
                "videoId": video_id,
                "action": "moved_to_failed",
                "stale_minutes": round(elapsed_minutes),
                "attempts": video["attempts"]
            }
        
        # Return to pending
        queue["pending"].insert(0, video)
        queue["processing"] = None
        self._save_queue(queue)

        return {
            "videoId": video_id,
            "action": "returned_to_pending",
            "stale_minutes": round(elapsed_minutes),
            "attempts": video["attempts"]
        }

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
            "notified": len(queue.get("notified", [])),
            "current": queue["processing"]
        }

    def get_detailed_status(self):
        """Get detailed queue status with retry info.
        
        Returns:
            Dict with full queue info including attempts
        """
        queue = self._load_queue()
        
        # Count videos with retry attempts
        retry_pending = [v for v in queue["pending"] if v.get("attempts", 0) > 0]
        
        return {
            "pending": len(queue["pending"]),
            "pending_with_retries": len(retry_pending),
            "processing": 1 if queue["processing"] else 0,
            "completed": len(queue["completed"]),
            "failed": len(queue["failed"]),
            "notified": len(queue.get("notified", [])),
            "current": queue["processing"],
            "retry_videos": [
                {
                    "videoId": v["videoId"],
                    "title": v["title"],
                    "attempts": v.get("attempts", 0),
                    "lastError": v.get("lastError", "N/A")[:100]
                }
                for v in retry_pending
            ]
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
        print("  fail <videoId> <error>             Mark video as failed (with retry)")
        print("  status                             Show queue status")
        print("  detailed-status                    Show detailed status with retry info")
        print("  reset-stale                        Return stuck video to pending")
        print("  clear-old [days]                   Clear old completed entries")
        print("  notify <videoId>                   Mark failed video as notified")
        print("  get-failed                         Get videos needing notification")
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
                    "startedAt": video.get("startedAt", ""),
                    "attempts": video.get("attempts", 0),
                    "lastError": video.get("lastError", "")
                }, indent=2, ensure_ascii=False))
            else:
                print(f"Processing: {video['title']}")
                print(f"Video ID: {video['videoId']}")
                print(f"Channel: {video['channel']}")
                if video.get("attempts", 0) > 0:
                    print(f"Attempts: {video['attempts']} (retry)")
                if video.get("lastError"):
                    print(f"Last error: {video['lastError'][:100]}")
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
        result = qm.mark_failed(video_id, error)
        
        if result["action"] == "retry":
            print(f"Marked {video_id} as failed (attempt {result['attempts']}/3)")
            print(f"Returned to pending queue for retry")
            print(f"Error: {result['lastError'][:100]}")
        elif result["action"] == "failed":
            print(f"Marked {video_id} as PERMANENTLY FAILED after {result['attempts']} attempts")
            print(f"Error: {result['lastError'][:100]}")
            print("NOTIFICATION NEEDED: Send Telegram alert")
        else:
            print(f"Video {video_id} not in processing state")

    elif command == "notify":
        if len(sys.argv) < 3:
            print("Error: notify requires videoId")
            sys.exit(1)
        video_id = sys.argv[2]
        if qm.mark_notified(video_id):
            print(f"Marked {video_id} as notified")
        else:
            print(f"Video {video_id} not in failed list")

    elif command == "get-failed":
        failed = qm.get_failed_for_notification()
        if failed:
            print(f"Videos needing notification ({len(failed)}):")
            for video in failed:
                print(f"  - {video['title']} ({video['videoId']})")
                print(f"    Attempts: {video.get('attempts', 0)}")
                print(f"    Last error: {video.get('lastError', 'N/A')[:100]}")
        else:
            print("No videos needing notification")

    elif command == "status":
        status = qm.get_status()
        print(f"Queue Status:")
        print(f"  Pending: {status['pending']}")
        print(f"  Processing: {status['processing']}")
        print(f"  Completed: {status['completed']}")
        print(f"  Failed: {status['failed']}")
        print(f"  Notified: {status['notified']}")
        if status["current"]:
            print(f"\nCurrently processing:")
            print(f"  {status['current']['title']}")
            print(f"  {status['current']['videoId']}")

    elif command == "detailed-status":
        status = qm.get_detailed_status()
        print(f"Queue Status (Detailed):")
        print(f"  Pending: {status['pending']} ({status['pending_with_retries']} with retries)")
        print(f"  Processing: {status['processing']}")
        print(f"  Completed: {status['completed']}")
        print(f"  Failed: {status['failed']}")
        print(f"  Notified: {status['notified']}")
        if status["retry_videos"]:
            print(f"\nVideos with retries:")
            for v in status["retry_videos"]:
                print(f"  - {v['title']} (attempt {v['attempts']}/3)")
                print(f"    Last error: {v['lastError']}")

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
