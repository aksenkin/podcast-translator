#!/usr/bin/env python3
"""
Queue Monitor Daemon - Monitors youtube-queue.json for changes

Watches the queue file for changes and automatically triggers processing
when new videos are added to the pending queue.
"""

import time
import json
import subprocess
from pathlib import Path
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


class QueueFileHandler(FileSystemEventHandler):
    def __init__(self, queue_file, skill_dir):
        self.queue_file = Path(queue_file)
        self.skill_dir = Path(skill_dir)
        self.last_processed = set()
        self.processing = False

    def on_modified(self, event):
        """Called when file is modified"""
        if event.src_path != str(self.queue_file):
            return

        # Avoid rapid-fire processing
        if self.processing:
            return

        try:
            # Wait for file write to complete
            time.sleep(1)

            # Read queue
            with open(self.queue_file, 'r') as f:
                queue = json.load(f)

            pending_count = len(queue.get('pending', []))
            processing = queue.get('processing')

            if processing:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Queue already processing, skip")
                return

            # Check if we have new pending videos
            pending_ids = set(v['videoId'] for v in queue.get('pending', []))
            new_videos = pending_ids - self.last_processed

            if new_videos and pending_count > 0:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] New videos detected: {len(new_videos)}")
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Total pending: {pending_count}")

                # Check time window (08:30-20:00)
                current_hour = datetime.now().hour
                current_minute = datetime.now().minute
                current_time = current_hour * 100 + current_minute

                if current_time >= 830 and current_time < 2000:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Within processing window - starting processor")
                    self.trigger_processing()
                    self.last_processed = pending_ids
                else:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Outside processing window - waiting")
                    self.last_processed = pending_ids

        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Error: {e}")

    def trigger_processing(self):
        """Trigger queue processor"""
        try:
            self.processing = True
            script_path = self.skill_dir / "run_queue_processor.sh"

            print(f"[{datetime.now().strftime('%H:%M:%S')}] Executing: {script_path}")

            result = subprocess.run(
                ['bash', str(script_path)],
                capture_output=True,
                text=True,
                timeout=7200  # 2 hours timeout
            )

            print(f"[{datetime.now().strftime('%H:%M:%S')}] Processor exit code: {result.returncode}")

            if result.returncode == 0:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] ✓ Processing completed")
            else:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] ✗ Processing failed")
                if result.stderr:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Error: {result.stderr[:200]}")

        except subprocess.TimeoutExpired:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ✗ Processing timeout (2 hours)")
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ✗ Error: {e}")
        finally:
            self.processing = False


def main():
    """Start queue monitoring daemon"""
    queue_file = Path("/home/clawd/.openclaw/workspace/youtube-queue.json")
    skill_dir = Path("/home/clawd/.openclaw/workspace/skills/podcast-translator")

    if not queue_file.exists():
        print(f"❌ Queue file not found: {queue_file}")
        return

    print(f"🚀 Queue Monitor Daemon Started")
    print(f"📁 Monitoring: {queue_file}")
    print(f"⏰ Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📊 Log: /tmp/queue-monitor-daemon.log")
    print(f"")
    print(f"✅ Ready to process videos when added to queue")
    print(f"   (Press Ctrl+C to stop)")

    # Redirect output to log file
    log_file = open('/tmp/queue-monitor-daemon.log', 'a')

    event_handler = QueueFileHandler(queue_file, skill_dir)
    observer = Observer()
    observer.schedule(event_handler, path=str(queue_file.parent))
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print(f"\n🛑 Queue Monitor Daemon Stopped: {datetime.now().strftime('%H:%M:%S')}")
        observer.stop()
        observer.join()
    finally:
        log_file.close()


if __name__ == "__main__":
    main()
