#!/usr/bin/env python3
"""
YouTube Video Queue Processor

Processes videos from the queue one at a time.
This script is designed for cron jobs.
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from datetime import datetime
from deep_translator import GoogleTranslator

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))
from queue_manager import QueueManager


class QueueProcessor:
    def __init__(self, skill_dir=None):
        """Initialize queue processor."""
        if skill_dir is None:
            skill_dir = Path(__file__).parent
        self.skill_dir = Path(skill_dir)
        self.qm = QueueManager(self.skill_dir / "youtube-queue.json")

    def add_youtube_videos_to_queue(self, channels):
        """Check YouTube channels for new videos and add to queue.

        Args:
            channels: List of dicts with 'url' and 'name' keys

        Returns:
            Dict with count of added videos and video info
        """
        all_videos = []

        for channel in channels:
            try:
                result = subprocess.run(
                    [
                        "yt-dlp",
                        "--get-id",
                        "--get-title",
                        "--playlist-end", "3",
                        channel["url"]
                    ],
                    capture_output=True,
                    text=True,
                    timeout=60
                )

                if result.returncode == 0:
                    lines = result.stdout.strip().split("\n")
                    # Output format: title on odd lines, id on even lines
                    for i in range(0, len(lines), 2):
                        if i + 1 < len(lines):
                            title = lines[i].strip()
                            video_id = lines[i + 1].strip()
                            if video_id and video_id != "%{id}":
                                all_videos.append({
                                    "videoId": video_id,
                                    "title": title,
                                    "channel": channel["name"]
                                })

            except subprocess.TimeoutExpired:
                print(f"Timeout checking channel: {channel['name']}")
            except Exception as e:
                print(f"Error checking channel {channel['name']}: {e}")

        # Add to queue (duplicates are filtered automatically)
        added_count = self.qm.add_videos(all_videos)

        return {
            "checked": len(all_videos),
            "added": added_count,
            "videos": all_videos
        }

    def process_next_video(self):
        """Process the next video in the queue.

        Returns:
            Dict with processing result
        """
        video = self.qm.get_next_video()

        if not video:
            return {
                "success": True,
                "message": "No videos in queue to process"
            }

        youtube_url = f"https://www.youtube.com/watch?v={video['videoId']}"

        print(f"🎙️ Processing: {video['title']}")
        print(f"📹 Video ID: {video['videoId']}")
        print(f"📺 Channel: {video['channel']}")
        print(f"🔗 URL: {youtube_url}")

        try:
            # Generate timestamp for this run
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            basename = f"podcast_{timestamp}"

            # Step 1: Download audio
            print("\n📥 Step 1: Downloading audio...")
            download_result = subprocess.run(
                [
                    "yt-dlp",
                    "-x",
                    "--audio-format", "mp3",
                    "--audio-quality", "0",
                    "-o", f"{self.skill_dir}/input/{basename}.%(ext)s",
                    youtube_url
                ],
                capture_output=True,
                text=True,
                timeout=300
            )

            if download_result.returncode != 0:
                raise Exception(f"Download failed: {download_result.stderr}")

            # Find the downloaded file
            input_dir = self.skill_dir / "input"
            input_files = list(input_dir.glob(f"{basename}.*"))
            if not input_files:
                raise Exception(f"Downloaded file not found: {basename}.*")
            input_file = input_files[0]
            print(f"✅ Downloaded: {input_file.name}")

            # Step 2: Transcribe
            print("\n⏱️ Step 2: Transcribing...")
            transcribe_result = subprocess.run(
                [
                    "python3",
                    str(self.skill_dir / "scripts" / "transcribe_cached.py"),
                    str(input_file),
                    str(self.skill_dir / "transcripts"),
                    "small"
                ],
                capture_output=True,
                text=True,
                timeout=7200  # 2 hours for transcription on ARM
            )

            if transcribe_result.returncode != 0:
                raise Exception(f"Transcription failed: {transcribe_result.stderr}")

            transcript_file = self.skill_dir / "transcripts" / f"{basename}.txt"
            print(f"✅ Transcribed: {transcript_file.name}")

            # Step 3: Prepare for translation
            print("\n📝 Step 3: Preparing for translation...")
            prepare_result = subprocess.run(
                [
                    "python3",
                    str(self.skill_dir / "scripts" / "prepare_transcript.py"),
                    str(transcript_file),
                    str(self.skill_dir / "translations" / f"{basename}_ready.txt")
                ],
                capture_output=True,
                text=True,
                timeout=60
            )

            if prepare_result.returncode != 0:
                raise Exception(f"Prepare failed: {prepare_result.stderr}")

            print("✅ Prepared for translation")

            # Step 4: Translate to Russian (via agent - need to read file and create translation)
            print("\n🌐 Step 4: Translating to Russian...")

            ready_file = self.skill_dir / "translations" / f"{basename}_ready.txt"
            if not ready_file.exists():
                raise Exception(f"Ready file not found: {ready_file}")

            # Read transcript
            transcript_content = ready_file.read_text(encoding='utf-8')

            # Initialize translator
            translator = GoogleTranslator(source='en', target='ru')

            # Create translation with timestamps preserved
            translation_lines = []
            print("   Translating text...")
            for line in transcript_content.split("\n"):
                if line.strip():
                    # Preserve timestamp format [00:00 - 00:05]
                    if line.startswith("[") and "]" in line:
                        timestamp_end = line.index("]") + 1
                        timestamp = line[:timestamp_end]
                        text = line[timestamp_end:].strip()
                        if text:
                            # Translate text to Russian
                            try:
                                translated_text = translator.translate(text)
                                translation_lines.append(f"{timestamp} {translated_text}")
                            except Exception as e:
                                print(f"   Translation error for segment: {e}")
                                translation_lines.append(f"{timestamp} {text}")
                    else:
                        translation_lines.append(line)

            # Write translation file
            translation_file = self.skill_dir / "translations" / f"{basename}_ru.txt"
            translation_file.write_text("\n".join(translation_lines), encoding='utf-8')

            print(f"✅ Translation: {translation_file.name}")

            # Step 5: Extract TTS text
            print("\n🎤 Step 5: Extracting TTS text...")
            extract_result = subprocess.run(
                [
                    "python3",
                    str(self.skill_dir / "scripts" / "extract_tts_text.py"),
                    str(translation_file),
                    str(self.skill_dir / "translations" / f"{basename}_ru_tts.txt")
                ],
                capture_output=True,
                text=True,
                timeout=60
            )

            if extract_result.returncode != 0:
                raise Exception(f"Extract TTS failed: {extract_result.stderr}")

            tts_file = self.skill_dir / "translations" / f"{basename}_ru_tts.txt"
            print(f"✅ TTS text: {tts_file.name}")

            # Step 6: Generate Russian TTS
            print("\n🔊 Step 6: Generating Russian TTS...")
            tts_result = subprocess.run(
                [
                    "python3",
                    str(self.skill_dir / "scripts" / "generate_tts.py"),
                    str(tts_file),
                    str(self.skill_dir / "audio" / f"{basename}.ru.mp3"),
                    "ru-RU-DmitryNeural"
                ],
                capture_output=True,
                text=True,
                timeout=600
            )

            if tts_result.returncode != 0:
                raise Exception(f"TTS generation failed: {tts_result.stderr}")

            output_audio = self.skill_dir / "audio" / f"{basename}.ru.mp3"
            print(f"✅ Russian audio: {output_audio.name}")

            # Mark as completed
            self.qm.mark_completed(
                video["videoId"],
                {
                    "audio": str(output_audio),
                    "translation": str(translation_file),
                    "ttsText": str(tts_file),
                    "transcript": str(transcript_file)
                }
            )

            print(f"\n✅ Successfully processed: {video['title']}")

            return {
                "success": True,
                "video": video,
                "output_files": {
                    "audio": str(output_audio),
                    "translation": str(translation_file),
                    "tts_text": str(tts_file)
                }
            }

        except Exception as e:
            print(f"\n❌ Error processing video: {e}")
            self.qm.mark_failed(video["videoId"], str(e))

            return {
                "success": False,
                "video": video,
                "error": str(e)
            }

    def run_once(self, channels):
        """Run one complete cycle: check channels, process one video.

        Args:
            channels: List of YouTube channels to check

        Returns:
            Dict with results
        """
        print(f"🔍 Checking YouTube channels at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        # Step 1: Check for new videos
        check_result = self.add_youtube_videos_to_queue(channels)

        print(f"\n📊 Check results:")
        print(f"  Videos found: {check_result['checked']}")
        print(f"  Added to queue: {check_result['added']}")

        # Step 2: Get queue status
        status = self.qm.get_status()
        print(f"\n📋 Queue status:")
        print(f"  Pending: {status['pending']}")
        print(f"  Completed: {status['completed']}")
        print(f"  Failed: {status['failed']}")

        # Step 3: Process next video (if any)
        if status['pending'] > 0:
            print(f"\n🎬 Processing next video...")
            process_result = self.process_next_video()
            return process_result
        else:
            return {
                "success": True,
                "message": "No new videos to process"
            }


def main():
    """Main entry point."""
    # YouTube channels to monitor
    channels = [
        {
            "url": "https://www.youtube.com/@AIDailyBrief/videos",
            "name": "AIDailyBrief"
        },
        {
            "url": "https://www.youtube.com/@mreflow/videos",
            "name": "mreflow"
        }
    ]

    processor = QueueProcessor()

    # Run one complete cycle
    result = processor.run_once(channels)

    if result["success"]:
        if "video" in result:
            print(f"\n✅ Completed: {result['video']['title']}")
        else:
            print(f"\n✅ {result['message']}")
    else:
        print(f"\n❌ Failed: {result['error']}")


if __name__ == "__main__":
    main()
