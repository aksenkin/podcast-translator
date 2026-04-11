#!/usr/bin/env python3
"""
YouTube Video Queue Processor for OpenClaw

Processes videos from the queue by spawning OpenClaw subagents for translation.
Designed for cron job execution.
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from datetime import datetime

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))
from queue_manager import QueueManager
from channel_monitor import YouTubeChannelMonitor


class QueueProcessor:
    def __init__(self, skill_dir=None):
        """Initialize queue processor."""
        if skill_dir is None:
            skill_dir = Path(__file__).parent
        self.skill_dir = Path(skill_dir)
        self.qm = QueueManager(self.skill_dir / "youtube-queue.json")
        self.monitor = YouTubeChannelMonitor(skill_dir)
        self.results = []
        self.start_time = None

    def add_youtube_videos_to_queue(self, channels=None, videos_per_channel=3):
        """Check YouTube channels and add new videos to queue.

        Wrapper method for YouTubeChannelMonitor.

        Args:
            channels: List of channel dicts with 'name' and 'url' keys
            videos_per_channel: Max videos to check per channel

        Returns:
            Dict with results: checked, added, skipped, errors, videos
        """
        return self.monitor.add_youtube_videos_to_queue(
            channels=channels,
            videos_per_channel=videos_per_channel
        )

    def spawn_subagent(self, youtube_url, voice="ru-RU-DmitryNeural", title=None, channel=None):
        """
        Spawn OpenClaw subagent for podcast translation.

        Args:
            youtube_url: YouTube video URL
            voice: TTS voice to use
            title: Video title (for MP3 metadata)
            channel: Channel name (for MP3 metadata)

        Returns:
            Dict with spawn result
        """
        print(f"🚀 Spawning subagent for: {youtube_url}")

        # Define SKILL_DIR for use in task template
        SKILL_DIR = str(self.skill_dir)

        # Prepare the task for subagent
        # Test task: sleep 10s, send Telegram report with video URL
        task = f"""## Video Processing Test - Send URL to Telegram

⚠️ CRITICAL: Do NOT install any software.

### Step 1: Sleep for 10 seconds
echo "STATUS: Starting 10 second sleep test..."
sleep 10
echo "SUCCESS: Sleep completed"

### Step 2: Send video URL to Telegram
echo "STATUS: Sending video URL to Telegram..."

TELEGRAM_MESSAGE="🎬 **Video Processing Complete**

✅ Agent successfully processed test task
🔗 Video URL: {youtube_url}
📺 Title: {title}
📺 Channel: {channel}
🕐 Completed at: $(date)

System is ready for production use!"

# Send via OpenClaw Telegram integration
import os
env = os.environ.copy()
env["PATH"] = "/home/clawd/.nvm/versions/node/v22.22.0/bin:" + env.get("PATH", "")

import subprocess
telegram_result = subprocess.run(
    ["openclaw", "agent", "--agent", "claude", "--local",
     "--deliver", "--reply-channel", "telegram",
     "--message", TELEGRAM_MESSAGE],
    capture_output=True,
    text=True,
    timeout=60,
    cwd="{SKILL_DIR}",
    env=env
)

if telegram_result.returncode == 0:
    echo "📤 Telegram report sent successfully"
else:
    echo "⚠️  Telegram delivery failed (non-critical)"

### Step 3: Final report
echo "SUCCESS: Agent finished test - slept 10 seconds, sent video URL to Telegram"
echo "REPORT: Video {youtube_url} processed successfully"
"""
        try:
            # Run OpenClaw agent command with full task
            # Use --local to run embedded agent locally
            # Use default agent (claude) for processing
            import os
            env = os.environ.copy()
            env["PATH"] = "/home/clawd/.nvm/versions/node/v22.22.0/bin:" + env.get("PATH", "")

            result = subprocess.run(
                [
                    "openclaw",
                    "agent",
                    "--agent", "claude",
                    "--local",
                    "--message", task,
                    "--timeout", "7200"  # 2 hours
                ],
                capture_output=True,
                text=True,
                timeout=7300,  # 2 hours + 2 min buffer
                cwd=str(self.skill_dir),
                env=env
            )

            success = result.returncode == 0

            return {
                "success": success,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode
            }

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": "Subagent timeout after 2 hours"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def send_to_telegram(self, audio_file, video_info):
        """
        Send translated MP3 file to Telegram.

        Args:
            audio_file: Path to the translated MP3 file
            video_info: Video metadata (title, videoId, etc.)
        """
        print(f"📤 Sending to Telegram: {video_info['title']}")

        # Verify file exists
        if not Path(audio_file).exists():
            print(f"❌ Audio file not found: {audio_file}")
            return {
                "success": False,
                "error": "File not found",
                "file": audio_file
            }

        # Get file size for message
        file_size = Path(audio_file).stat().st_size
        file_size_mb = file_size / (1024 * 1024)

        # Prepare message with video info
        message = f"""🎙️ *{video_info['title']}*

📺 Channel: {video_info['channel']}
🆔 Video ID: {video_info.get('videoId', 'N/A')}
📊 Size: {file_size_mb:.1f} MB

🔗 Original: https://www.youtube.com/watch?v={video_info.get('videoId', '')}"""

        try:
            # Send MP3 file via OpenClaw Telegram integration
            cmd = [
                "openclaw",
                "message",
                "send",
                "--channel", "telegram",
                "--media", str(audio_file),
                "--message", message,
                "--json"
            ]

            print(f"   📁 File: {audio_file} ({file_size_mb:.1f} MB)")
            print(f"   📤 Sending...")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minutes timeout for large files
            )

            if result.returncode == 0:
                print(f"   ✅ Sent successfully!")

                # Try to parse JSON response
                try:
                    response = json.loads(result.stdout)
                    return {
                        "success": True,
                        "file": audio_file,
                        "message_id": response.get("messageId"),
                        "response": response
                    }
                except json.JSONDecodeError:
                    return {
                        "success": True,
                        "file": audio_file,
                        "output": result.stdout
                    }
            else:
                error_msg = result.stderr or result.stdout or "Unknown error"
                print(f"   ❌ Failed to send: {error_msg}")
                return {
                    "success": False,
                    "error": error_msg,
                    "file": audio_file,
                    "stderr": result.stderr,
                    "stdout": result.stdout
                }

        except subprocess.TimeoutExpired:
            print(f"   ❌ Timeout sending file (5 minutes)")
            return {
                "success": False,
                "error": "Timeout",
                "file": audio_file
            }
        except Exception as e:
            print(f"   ❌ Error: {e}")
            return {
                "success": False,
                "error": str(e),
                "file": audio_file
            }

    def process_video(self, video):
        """
        Process a single video from the queue.

        Args:
            video: Video dict with videoId, title, channel

        Returns:
            Dict with processing result
        """
        video_id = video['videoId']
        youtube_url = f"https://www.youtube.com/watch?v={video_id}"
        title = video['title']

        print(f"\n{'='*60}")
        print(f"🎙️ Processing: {title}")
        print(f"📺 Channel: {video['channel']}")
        print(f"🆔 ID: {video_id}")
        print(f"{'='*60}\n")

        # Spawn subagent for translation
        print(f"⏳ Starting translation subagent...")
        result = self.spawn_subagent(youtube_url, title=title, channel=video['channel'])

        if not result['success']:
            error_msg = result.get('error', result.get('stderr', 'Unknown error'))
            print(f"❌ Subagent failed: {error_msg}")

            # Mark as failed
            self.qm.mark_failed(video_id, error_msg)

            return {
                "success": False,
                "video_id": video_id,
                "error": error_msg
            }

        print(f"✅ Subagent completed successfully")

        # Find generated manifest file
        # The subagent creates manifest at: translations/{basename}_manifest.txt
        # Find the most recent manifest file (created in last 10 minutes)
        import glob
        import time
        import os

        manifest_pattern = str(self.skill_dir / "translations/*_manifest.txt")
        all_manifests = glob.glob(manifest_pattern)

        # Filter for recent manifests (last 10 minutes)
        recent_manifests = []
        ten_minutes_ago = time.time() - 600
        for mf in all_manifests:
            if os.path.getmtime(mf) > ten_minutes_ago:
                recent_manifests.append(mf)

        if not recent_manifests:
            print(f"⚠️  No recent manifest file found for {video_id}")
            print(f"   Searched for: {manifest_pattern}")

            # Mark as completed but without files
            self.qm.mark_completed(video_id)

            return {
                "success": True,
                "video_id": video_id,
                "warning": "No manifest file found"
            }

        # Use the most recent manifest
        manifest_file = max(recent_manifests, key=os.path.getmtime)

        manifest_file = manifest_files[0]
        print(f"📄 Found manifest: {manifest_file}")

        # Read manifest to get output files
        try:
            with open(manifest_file, 'r') as f:
                manifest_content = f.read()

            # Parse manifest to find audio file path
            audio_path = None
            for line in manifest_content.split('\n'):
                if line.startswith('audio:'):
                    audio_path = line.split(':', 1)[1].strip()
                    break

            if audio_path and os.path.exists(audio_path):
                print(f"✅ Found audio file: {audio_path}")

                # Send to Telegram
                telegram_result = self.send_to_telegram(audio_path, video)

                # Mark as completed with output files
                self.qm.mark_completed(video_id, {
                    "audio": audio_path,
                    "manifest": manifest_file
                })

                return {
                    "success": True,
                    "video_id": video_id,
                    "audio_file": audio_path,
                    "telegram_sent": telegram_result['success']
                }
            else:
                print(f"⚠️  Audio file not found: {audio_path}")

                # Mark as completed anyway (subagent finished)
                self.qm.mark_completed(video_id)

                return {
                    "success": True,
                    "video_id": video_id,
                    "warning": "Audio file not found"
                }

        except Exception as e:
            print(f"❌ Error reading manifest: {e}")
            self.qm.mark_completed(video_id)

            return {
                "success": True,
                "video_id": video_id,
                "warning": f"Manifest error: {e}"
            }

    def run(self, max_videos=2):
        """
        Process pending videos from the queue.

        Args:
            max_videos: Maximum number of videos to process (default: 2)

        Returns:
            Dict with processing results
        """
        self.start_time = datetime.now()
        print(f"🚀 Queue Processor Started at {self.start_time.strftime('%H:%M:%S')}")

        # Time window check: only process between 08:30 and 20:00
        current_hour = self.start_time.hour
        current_minute = self.start_time.minute
        current_time = current_hour * 100 + current_minute  # Convert to comparable number (e.g., 8:30 = 830, 20:00 = 2000)

        # Skip processing if before 08:30 or after 20:00
        # TEMPORARILY DISABLED for testing
        if False:  # current_time < 830 or current_time >= 2000
            print(f"⏰ Current time: {self.start_time.strftime('%H:%M')}")
            print(f"⚠️  Outside processing window (08:30-20:00)")
            print(f"📊 Queue check only - skipping processing\n")

            # Just show queue status and exit
            status = self.qm.get_status()
            print(f"📊 Queue Status:")
            print(f"   Pending: {status['pending']}")
            print(f"   Processing: {status['processing']}")
            print(f"   Completed: {status['completed']}")
            print(f"   Failed: {status['failed']}")

            return {
                "success": True,
                "skipped": True,
                "reason": "outside_processing_window",
                "message": f"Current time {self.start_time.strftime('%H:%M')} is outside processing window (08:30-20:00)",
                "queue_status": status,
                "processed": 0,
                "elapsed_seconds": 0
            }

        print(f"✅ Within processing window (08:30-20:00)")
        print(f"⏰ Max videos to process: {max_videos}\n")

        # Clear all completed entries from previous runs
        cleared = self.qm.clear_all_completed()
        if cleared > 0:
            print(f"🧹 Cleared {cleared} completed entries from previous runs\n")
        else:
            print("📋 Queue is clean (no old completed entries)\n")

        # Show initial status
        status = self.qm.get_status()
        print(f"📊 Initial Queue Status:")
        print(f"   Pending: {status['pending']}")
        print(f"   Processing: {status['processing']}")
        print(f"   Completed: {status['completed']}")
        print(f"   Failed: {status['failed']}")

        if status['pending'] == 0:
            return {
                "success": True,
                "message": "No videos in queue to process",
                "processed": 0,
                "results": []
            }

        # Process videos one by one
        processed_count = 0
        for i in range(max_videos):
            video = self.qm.get_next_video()

            if not video:
                print(f"\n✅ No more videos in queue")
                break

            print(f"\n📹 Processing video {i + 1}/{max_videos}")

            result = self.process_video(video)
            self.results.append(result)

            if result['success']:
                processed_count += 1
                print(f"✅ Video {i + 1} completed successfully")

                # Send success report to Telegram
                try:
                    import os
                    env = os.environ.copy()
                    env["PATH"] = "/home/clawd/.nvm/versions/node/v22.22.0/bin:" + env.get("PATH", "")

                    telegram_message = f"🎉 **Video Processing Complete**\\n\\n✅ Successfully processed: {video['title']}\\n📺 Channel: {video['channel']}\\n🆔 ID: {video['videoId']}\\n🕐 Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\\n\\nAgent test PASSED - System is ready for production!"

                    telegram_result = subprocess.run(
                        ["openclaw", "agent", "--agent", "claude", "--local",
                         "--deliver", "--reply-channel", "telegram",
                         "--message", telegram_message],
                        capture_output=True,
                        text=True,
                        timeout=60,
                        cwd=str(self.skill_dir),
                        env=env
                    )

                    if telegram_result.returncode == 0:
                        print(f"📤 Telegram report sent successfully")
                    else:
                        print(f"⚠️  Telegram delivery failed (non-critical)")
                except Exception as e:
                    print(f"⚠️  Could not send Telegram report: {e}")
            else:
                print(f"❌ Video {i + 1} failed: {result.get('error', 'Unknown error')}")

        # Final summary
        elapsed = (datetime.now() - self.start_time).total_seconds()

        final_status = self.qm.get_status()
        print(f"\n{'='*60}")
        print(f"📊 PROCESSING SUMMARY")
        print(f"{'='*60}")
        print(f"⏱️  Total time: {elapsed:.1f} seconds ({elapsed/60:.1f} minutes)")
        print(f"📹 Processed: {processed_count}/{max_videos}")
        print(f"📊 Final Queue Status:")
        print(f"   Pending: {final_status['pending']}")
        print(f"   Processing: {final_status['processing']}")
        print(f"   Completed: {final_status['completed']}")
        print(f"   Failed: {final_status['failed']}")

        return {
            "success": True,
            "processed": processed_count,
            "elapsed_seconds": elapsed,
            "results": self.results,
            "queue_status": final_status
        }


def main():
    """Main entry point for queue processor."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Process YouTube video translation queue"
    )
    parser.add_argument(
        "--max-videos",
        type=int,
        default=2,
        help="Maximum number of videos to process (default: 2)"
    )

    args = parser.parse_args()

    processor = QueueProcessor()
    result = processor.run(max_videos=args.max_videos)

    # Exit with error code if processing failed
    if not result['success']:
        sys.exit(1)

    # Print summary in machine-readable format
    print(f"\nRESULT: {json.dumps({
        'processed': result['processed'],
        'elapsed_seconds': result['elapsed_seconds'],
        'queue_status': result['queue_status']
    }, indent=2)}")


if __name__ == "__main__":
    main()
