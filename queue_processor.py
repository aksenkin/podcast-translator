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

        # Prepare the task for subagent
        # This matches the SKILL.md format from podcast-translator
        task = f"""## Podcast Translator: Process {youtube_url}

⚠️ CRITICAL: Do NOT install any software.
No pip, brew, curl, venv, or binary downloads.
If a tool is missing, STOP and report what's needed.

⚠️ CRITICAL: Print progress at each step in machine-readable format:
- STATUS: Step description
- HEARTBEAT: Progress updates
- SUCCESS: Step completed
- ERROR: Step failed

Run the COMPLETE pipeline — do not stop until all steps are done.

### Configuration
- PROJECT_DIR="{SKILL_DIR}"
- Voice: {voice}
- VIDEO_TITLE="{title or 'Unknown'}"
- CHANNEL_NAME="{channel or 'Unknown'}"

### Step 1: Download Audio
cd "$SKILL_DIR"
echo "STATUS: Downloading audio from YouTube..."
yt-dlp -x --audio-format mp3 --audio-quality 0 \\
  -o "input/podcast_$(date +%Y%m%d_%H%M%S).mp3" \\
  "{youtube_url}"

### Step 2: Transcribe to English
echo "STATUS: Starting transcription..."
python3 $SKILL_DIR/scripts/transcribe_cached.py \\
  "$INPUT_FILE" \\
  "$SKILL_DIR/transcripts/" \\
  small

### Step 3: Prepare for Translation
echo "STATUS: Preparing transcript for translation..."
python3 $SKILL_DIR/scripts/prepare_transcript.py \\
  "$TRANSCRIPT_FILE" \\
  "$SKILL_DIR/translations/{{basename}}_ready.txt"

### Step 4: Translate to Russian
echo "STATUS: Translating to Russian (this may take a few minutes)..."
echo "HEARTBEAT: Translation in progress..."

Read the prepared file and create ONE translation file:
**translations/{{basename}}_ru.txt** (with timestamps)

Print: "STATUS: Translation complete"

### Step 4.5: Extract TTS Text (SCRIPT - saves tokens!)
echo "STATUS: Extracting TTS text from translation..."
python3 $SKILL_DIR/scripts/extract_tts_text.py \\
  "$SKILL_DIR/translations/{{basename}}_ru.txt" \\
  "$SKILL_DIR/translations/{{basename}}_ru_tts.txt"
Output: `translations/{{basename}}_ru_tts.txt` (clean Russian text, no timestamps)
Print: `SUCCESS: TTS text extracted`

### Step 5: Generate Russian TTS
echo "STATUS: Starting TTS generation..."
python3 $SKILL_DIR/scripts/generate_tts.py \\
  "$SKILL_DIR/translations/{{basename}}_ru_tts.txt" \\
  "$SKILL_DIR/audio/{{basename}}.ru.mp3" \\
  "{voice}" \\
  "{title or 'Unknown'}" \\
  "{channel or 'Unknown'}"

### Step 6: Create Output Manifest
MANIFEST_FILE="$SKILL_DIR/translations/{{basename}}_manifest.txt"

cat > "$MANIFEST_FILE" << 'EOF'
===OPENCLAW_OUTPUTS_COMPLETE===
translation:translations/{{basename}}_ru.txt
tts_text:translations/{{basename}}_ru_tts.txt
audio:audio/{{basename}}.ru.mp3
transcript:transcripts/{{basename}}.txt
base_dir:$SKILL_DIR
===OPENCLAW_OUTPUTS_END===
EOF

echo "===MANIFEST:$MANIFEST_FILE==="

### Report
Print in machine-readable format:
SUCCESS: Pipeline complete
STATUS: Russian audio: audio/{{basename}}.ru.mp3
"""

        try:
            # Run OpenClaw agent spawn command
            result = subprocess.run(
                [
                    "openclaw",
                    "agents",
                    "spawn",
                    "--runtime", "subagent",
                    "--agent-id", "podcast-translator",
                    "--timeout", "7200",  # 2 hours
                    "--",
                    youtube_url
                ],
                capture_output=True,
                text=True,
                timeout=7300,  # 2 hours + 2 min buffer
                cwd=str(self.skill_dir)
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
        # The subagent creates manifest at: translations/*_manifest.txt
        manifest_pattern = f"translations/*_{video_id}_manifest.txt"
        import glob
        manifest_files = glob.glob(str(self.skill_dir / manifest_pattern))

        if not manifest_files:
            print(f"⚠️  No manifest file found for {video_id}")
            print(f"   Searched for: {manifest_pattern}")

            # Mark as completed but without files
            self.qm.mark_completed(video_id)

            return {
                "success": True,
                "video_id": video_id,
                "warning": "No manifest file found"
            }

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
        if current_time < 830 or current_time >= 2000:
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
                "queue_status": status
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
