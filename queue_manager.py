#!/usr/bin/env python3
"""
YouTube Video Translation Queue Manager

Thread-safe queue manager with file locking and atomic writes.
Features:
- File locking (fcntl) prevents concurrent modification
- Atomic writes (temp + fsync + rename) prevent corruption
- Auto-cleanup stale processing on every load
- Retry logic: failed videos return to pending queue
- Attempt counter: tracks how many times video was tried
"""

import fcntl
import json
import os
import subprocess
import tempfile
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
        self.lock_file = self.queue_file.with_suffix('.lock')
        self._ensure_queue_file()

    def _ensure_queue_file(self):
        """Create queue file if it doesn't exist."""
        if not self.queue_file.exists():
            self._atomic_save({
                "pending": [],
                "processing": {},
                "completed": [],
                "failed": [],
                "notified": []
            })

    def _atomic_save(self, data):
        """Atomically save queue data to file.
        
        Pattern: write to temp -> fsync -> rename (atomic on POSIX).
        """
        json_bytes = json.dumps(data, indent=2, ensure_ascii=False).encode('utf-8')
        fd, temp_path = tempfile.mkstemp(
            dir=self.queue_file.parent,
            prefix=f'.{self.queue_file.name}.tmp.'
        )
        try:
            os.write(fd, json_bytes)
            os.fsync(fd)
            os.close(fd)
            os.rename(temp_path, self.queue_file)
        except:
            os.close(fd)
            try:
                os.unlink(temp_path)
            except FileNotFoundError:
                pass
            raise

    def _load_queue(self):
        """Load queue from file with auto-cleanup."""
        if not self.queue_file.exists():
            return {"pending": [], "processing": {}, "completed": [], "failed": [], "notified": []}
        
        try:
            with open(self.queue_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Normalize: processing should always be dict (never None)
            if data.get('processing') is None:
                data['processing'] = {}
            
            # Auto-clear completed to keep queue lean
            if data.get('completed'):
                data['completed'] = []
                self._atomic_save(data)
            
            return data
        except (json.JSONDecodeError, OSError):
            print("Warning: Queue file corrupted, resetting")
            default = {"pending": [], "processing": {}, "completed": [], "failed": [], "notified": []}
            self._atomic_save(default)
            return default

    def _save_queue(self, queue):
        """Save queue atomically."""
        self._atomic_save(queue)

    def _acquire_lock(self):
        """Acquire exclusive file lock for queue operations."""
        # Ensure lock file exists
        if not self.lock_file.exists():
            self.lock_file.touch()
        self._lock_fd = open(self.lock_file, 'w')
        fcntl.flock(self._lock_fd.fileno(), fcntl.LOCK_EX)
        return self._lock_fd

    def _release_lock(self):
        """Release file lock."""
        if hasattr(self, '_lock_fd') and self._lock_fd:
            fcntl.flock(self._lock_fd.fileno(), fcntl.LOCK_UN)
            self._lock_fd.close()
            self._lock_fd = None

    def add_videos(self, videos):
        """Add videos to pending queue (thread-safe)."""
        self._acquire_lock()
        try:
            queue = self._load_queue()

            existing_ids = set(v["videoId"] for v in queue["pending"])
            existing_ids.update(v["videoId"] for v in queue["failed"])
            existing_ids.update(v["videoId"] for v in queue.get("notified", []))
            if queue["processing"]:
                existing_ids.add(queue["processing"]["videoId"])

            added_count = 0
            for video in videos:
                if video["videoId"] not in existing_ids:
                    video["addedAt"] = datetime.now(timezone.utc).isoformat()
                    video["attempts"] = 0
                    video["lastError"] = None
                    queue["pending"].append(video)
                    added_count += 1

            self._save_queue(queue)
            return added_count
        finally:
            self._release_lock()

    def get_next_video(self):
        """Get next video with stale cleanup and locking."""
        self._acquire_lock()
        try:
            queue = self._load_queue()
            
            # Auto-reset stale processing (orphan detection)
            self._do_reset_stale(queue, max_minutes=30)

            if not queue["pending"]:
                self._save_queue(queue)  # Save in case stale was reset
                return None

            # Move first pending to processing
            video = queue["pending"].pop(0)
            video["startedAt"] = datetime.now(timezone.utc).isoformat()
            video["attempts"] = video.get("attempts", 0)
            video["lastError"] = video.get("lastError")
            video["statusHistory"] = video.get("statusHistory", [])
            video["statusHistory"].append({
                "status": "processing",
                "timestamp": video["startedAt"]
            })

            queue["processing"] = video
            self._save_queue(queue)
            return video
        finally:
            self._release_lock()

    def mark_completed(self, video_id, output_files=None):
        """Mark video as completed."""
        self._acquire_lock()
        try:
            queue = self._load_queue()

            if not queue["processing"] or queue["processing"]["videoId"] != video_id:
                return False

            video = queue["processing"]
            video["completedAt"] = datetime.now(timezone.utc).isoformat()
            video["outputFiles"] = output_files or {}
            
            # Don't add to completed list (auto-cleared on next load anyway)
            # Just clear processing
            queue["processing"] = {}
            self._save_queue(queue)
            return True
        finally:
            self._release_lock()

    def mark_failed(self, video_id, error):
        """Mark video as failed with retry logic."""
        self._acquire_lock()
        try:
            queue = self._load_queue()

            video = None
            if queue["processing"] and queue["processing"]["videoId"] == video_id:
                video = queue["processing"]
                queue["processing"] = {}
            else:
                # Search in pending/failed as fallback
                for v in queue["pending"]:
                    if v["videoId"] == video_id:
                        video = v
                        queue["pending"].remove(v)
                        break
                if not video:
                    for v in queue["failed"]:
                        if v["videoId"] == video_id:
                            video = v
                            queue["failed"].remove(v)
                            break

            if not video:
                return {"action": "not_found", "videoId": video_id, "message": f"Video {video_id} not found in queue"}

            video["attempts"] = video.get("attempts", 0) + 1
            video["lastError"] = error
            video["failedAt"] = datetime.now(timezone.utc).isoformat()
            video["statusHistory"] = video.get("statusHistory", [])
            video["statusHistory"].append({
                "status": "failed",
                "timestamp": video["failedAt"],
                "error": error
            })

            if video["attempts"] < 3:
                queue["pending"].append(video)
                self._save_queue(queue)
                return {
                    "action": "retry",
                    "videoId": video_id,
                    "attempts": video["attempts"],
                    "lastError": error,
                    "message": f"Marked {video_id} as failed (attempt {video['attempts']}/3), returned to pending"
                }
            else:
                queue["failed"].append(video)
                self._save_queue(queue)
                return {
                    "action": "failed",
                    "videoId": video_id,
                    "attempts": video["attempts"],
                    "lastError": error,
                    "message": f"Marked {video_id} as PERMANENTLY FAILED after {video['attempts']} attempts"
                }
        finally:
            self._release_lock()

    def remove_video(self, video_id):
        """Permanently remove video from queue."""
        self._acquire_lock()
        try:
            queue = self._load_queue()
            removed_from = None

            for section in ["pending", "failed", "notified"]:
                for i, video in enumerate(queue.get(section, [])):
                    if isinstance(video, dict) and video.get("videoId") == video_id:
                        queue[section].pop(i)
                        removed_from = section
                        break
                if removed_from:
                    break

            if not removed_from and queue.get("processing", {}).get("videoId") == video_id:
                queue["processing"] = {}
                removed_from = "processing"

            self._save_queue(queue)
            return {
                "action": "removed",
                "videoId": video_id,
                "from": removed_from or "not_found"
            }
        finally:
            self._release_lock()

    def reset_stale(self, max_minutes=30):
        """Reset stale processing video (public API, thread-safe)."""
        self._acquire_lock()
        try:
            queue = self._load_queue()
            result = self._do_reset_stale(queue, max_minutes)
            if result:
                self._save_queue(queue)
            return result
        finally:
            self._release_lock()

    def _do_reset_stale(self, queue, max_minutes=30):
        """Internal: reset stale processing without locking."""
        processing = queue.get("processing", {})
        if not processing:
            return None

        started_at = processing.get("startedAt")
        if not started_at:
            return None

        try:
            started = datetime.fromisoformat(started_at.replace('Z', '+00:00'))
            elapsed = (datetime.now(timezone.utc) - started).total_seconds() / 60

            if elapsed > max_minutes:
                video = processing
                queue["processing"] = {}
                video["lastError"] = f"Stale reset after {int(elapsed)} minutes"
                video["attempts"] = video.get("attempts", 0)
                video["statusHistory"] = video.get("statusHistory", [])
                video["statusHistory"].append({
                    "status": "stale_reset",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "error": video["lastError"]
                })
                queue["pending"].append(video)
                return video
        except (ValueError, TypeError):
            pass

        return None

    def mark_notified(self, video_id):
        """Mark failed video as notified."""
        self._acquire_lock()
        try:
            queue = self._load_queue()
            for i, video in enumerate(queue["failed"]):
                if video["videoId"] == video_id:
                    video = queue["failed"].pop(i)
                    video["notifiedAt"] = datetime.now(timezone.utc).isoformat()
                    queue.setdefault("notified", []).append(video)
                    self._save_queue(queue)
                    return True
            return False
        finally:
            self._release_lock()

    def get_failed_for_notification(self):
        """Get videos needing notification (3+ attempts)."""
        self._acquire_lock()
        try:
            queue = self._load_queue()
            return [v for v in queue["failed"] if v.get("attempts", 0) >= 3]
        finally:
            self._release_lock()

    def get_status(self):
        """Get queue status summary."""
        self._acquire_lock()
        try:
            queue = self._load_queue()
            return {
                "pending": len(queue["pending"]),
                "processing": 1 if queue.get("processing") else 0,
                "completed": len(queue["completed"]),
                "failed": len(queue["failed"]),
                "notified": len(queue.get("notified", []))
            }
        finally:
            self._release_lock()

    def get_detailed_status(self):
        """Get detailed queue status with retry info."""
        self._acquire_lock()
        try:
            queue = self._load_queue()
            return {
                "pending": queue["pending"],
                "processing": queue.get("processing", {}),
                "completed": queue["completed"],
                "failed": queue["failed"],
                "notified": queue.get("notified", [])
            }
        finally:
            self._release_lock()

    def clear_old_completed(self, days=7):
        """Remove completed entries older than specified days (no-op, auto-cleared)."""
        return 0

    def clear_all_completed(self):
        """Remove all completed entries (no-op, auto-cleared)."""
        return 0


def main():
    """CLI interface."""
    import sys

    if len(sys.argv) < 2:
        print("Usage: queue_manager.py <command> [args]")
        print("\nCommands:")
        print("  add <videoId> <title> <channel>  Add video to queue")
        print("  next                               Get next video to process")
        print("  complete <videoId>                 Mark video as completed")
        print("  fail <videoId> <error>             Mark video as failed (with retry)")
        print("  remove <videoId>                   Permanently remove video from queue")
        print("  status                             Show queue status")
        print("  detailed-status                    Show detailed status")
        print("  reset-stale                        Return stuck video to pending")
        print("  clear-old [days]                   No-op (auto-cleared)")
        sys.exit(1)

    command = sys.argv[1]
    qm = QueueManager()

    if command == "add":
        if len(sys.argv) < 5:
            print("Error: add requires videoId, title, and channel")
            sys.exit(1)
        count = qm.add_videos([{
            "videoId": sys.argv[2],
            "title": sys.argv[3],
            "channel": sys.argv[4]
        }])
        print(f"Added {count} video(s) to queue")

    elif command == "next":
        video = qm.get_next_video()
        if video:
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
        if qm.mark_completed(sys.argv[2]):
            print(f"Marked {sys.argv[2]} as completed")
        else:
            print(f"Video {sys.argv[2]} not in processing state")

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
            print(f"Video {video_id} not found in queue")

    elif command == "remove":
        if len(sys.argv) < 3:
            print("Error: remove requires videoId")
            sys.exit(1)
        result = qm.remove_video(sys.argv[2])
        print(f"Removed {result['videoId']} from {result['from']}")

    elif command == "status":
        status = qm.get_status()
        print(f"Queue Status:")
        print(f"  Pending: {status['pending']}")
        print(f"  Processing: {status['processing']}")
        print(f"  Completed: {status['completed']}")
        print(f"  Failed: {status['failed']}")
        print(f"  Notified: {status['notified']}")
        if status['processing'] > 0:
            detail = qm.get_detailed_status()
            proc = detail.get('processing', {})
            if proc:
                print(f"\nCurrently processing:\n  {proc.get('title', 'Unknown')}\n  {proc.get('videoId', '')}")

    elif command == "detailed-status":
        status = qm.get_detailed_status()
        print(json.dumps(status, indent=2, ensure_ascii=False, default=str))

    elif command == "reset-stale":
        result = qm.reset_stale()
        if result:
            print(f"Reset stale video: {result['title']} ({result['videoId']})")
            print(f"Reason: {result['lastError']}")
        else:
            print("No stale processing video found")

    elif command == "clear-old":
        print("No-op: completed entries are auto-cleared on load")

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
