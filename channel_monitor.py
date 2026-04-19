#!/usr/bin/env python3
"""
YouTube Channel Monitor for OpenClaw

Checks configured YouTube channels for new videos and adds them to the queue.
Designed for cron job execution.

Usage:
    python3 channel_monitor.py [--videos-per-channel N] [--channels-file PATH]

Environment:
    SKILL_DIR: Auto-detected as script directory
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse, parse_qs

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))
from queue_manager import QueueManager


class YouTubeChannelMonitor:
    def __init__(self, skill_dir=None, channels_file=None):
        """Initialize YouTube channel monitor.

        Args:
            skill_dir: Skill directory path (default: script directory)
            channels_file: Path to channels config JSON
        """
        if skill_dir is None:
            skill_dir = Path(__file__).parent
        self.skill_dir = Path(skill_dir)
        self.qm = QueueManager(self.skill_dir / "youtube-queue.json")

        if channels_file is None:
            channels_file = self.skill_dir.parent.parent / "youtube-channels.json"
        self.channels_file = Path(channels_file)

        self.results = {
            "checked": 0,
            "added": 0,
            "skipped": 0,
            "errors": 0,
            "videos": [],
            "channels_checked": []
        }

    def load_channels(self):
        """Load channel list from config file.

        Returns:
            List of channel dicts with 'name' and 'url' keys
        """
        if not self.channels_file.exists():
            raise FileNotFoundError(f"Channels file not found: {self.channels_file}")

        with open(self.channels_file, 'r') as f:
            config = json.load(f)

        return config.get("channels", [])

    def extract_video_id(self, url):
        """Extract YouTube video ID from URL.

        Args:
            url: YouTube video URL

        Returns:
            Video ID string or None
        """
        parsed = urlparse(url)

        if parsed.hostname in ('youtu.be', 'www.youtu.be'):
            return parsed.path[1:]

        if parsed.hostname in ('youtube.com', 'www.youtube.com', 'm.youtube.com'):
            if parsed.path == '/watch':
                return parse_qs(parsed.query).get('v', [None])[0]
            if parsed.path.startswith('/embed/'):
                return parsed.path.split('/')[2]
            if parsed.path.startswith('/v/'):
                return parsed.path.split('/')[2]

        return None

    def get_channel_videos(self, channel_url, max_videos=3):
        """Fetch latest videos from a YouTube channel.

        Args:
            channel_url: Channel URL (e.g., https://www.youtube.com/@username)
            max_videos: Maximum number of videos to fetch

        Returns:
            List of video dicts with 'videoId', 'title', 'url' keys
        """
        print(f"   📡 Fetching videos from {channel_url}")

        try:
            # Use yt-dlp to get channel videos
            cmd = [
                "yt-dlp",
                "--flat-playlist",
                "--print", "%(id)s|||%(title)s",
                "--playlist-end", str(max_videos),
                channel_url
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
                cwd=str(self.skill_dir)
            )

            if result.returncode != 0:
                print(f"   ⚠️  yt-dlp failed: {result.stderr}")
                return []

            # Parse output
            videos = []
            for line in result.stdout.strip().split('\n'):
                if '|||' in line:
                    video_id, title = line.split('|||', 1)
                    videos.append({
                        'videoId': video_id,
                        'title': title.strip(),
                        'url': f"https://www.youtube.com/watch?v={video_id}"
                    })

            print(f"   ✅ Found {len(videos)} videos")
            return videos

        except subprocess.TimeoutExpired:
            print(f"   ⚠️  Timeout fetching videos")
            return []
        except Exception as e:
            print(f"   ❌ Error: {e}")
            return []

    def add_youtube_videos_to_queue(self, channels=None, videos_per_channel=3):
        """Check YouTube channels and add new videos to queue.

        Args:
            channels: List of channel dicts (default: load from config)
            videos_per_channel: Max videos to check per channel

        Returns:
            Dict with results: checked, added, skipped, errors, videos
        """
        if channels is None:
            channels = self.load_channels()

        print(f"📺 Checking {len(channels)} channel(s)")
        print(f"⏰ Started at: {datetime.now().strftime('%H:%M:%S')}\n")

        all_videos = []

        for channel in channels:
            channel_name = channel.get('name', 'Unknown')
            channel_url = channel.get('url')

            if not channel_url:
                print(f"⚠️  Skipping {channel_name}: no URL")
                continue

            print(f"🔍 Channel: {channel_name}")
            print(f"   URL: {channel_url}")

            # Get videos from channel
            videos = self.get_channel_videos(channel_url, videos_per_channel)

            # Add channel info to each video
            for video in videos:
                video['channel'] = channel_name
                all_videos.append(video)

            self.results['channels_checked'].append({
                'name': channel_name,
                'url': channel_url,
                'videos_found': len(videos)
            })

            self.results['checked'] += 1

        # Add all videos to queue (QueueManager handles duplicates)
        print(f"\n📝 Adding {len(all_videos)} videos to queue...")

        added_count = self.qm.add_videos(all_videos)
        skipped_count = len(all_videos) - added_count

        self.results['added'] = added_count
        self.results['skipped'] = skipped_count
        self.results['videos'] = all_videos

        print(f"   ✅ Added: {added_count}")
        print(f"   ⏭️  Skipped (duplicates): {skipped_count}")

        # Show final queue status
        status = self.qm.get_status()
        print(f"\n📊 Queue Status:")
        print(f"   Pending: {status['pending']}")
        print(f"   Processing: {status['processing']}")
        print(f"   Completed: {status['completed']}")
        print(f"   Failed: {status['failed']}")

        # Launch queue_processor immediately if videos were added
        if added_count > 0:
            try:
                print(f"\n🚀 Launching queue_processor...")
                subprocess.Popen(
                    ["python3", str(self.skill_dir / "queue_processor.py"), "--max-videos", "1"],
                    cwd=str(self.skill_dir),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True
                )
                print(f"✅ queue_processor started in background")
            except Exception as e:
                print(f"⚠️  Failed to launch queue_processor: {e}")

        return self.results

    def run(self, videos_per_channel=3):
        """Run channel monitor check.

        Args:
            videos_per_channel: Max videos to check per channel

        Returns:
            Dict with results
        """
        start_time = datetime.now()
        print(f"🚀 YouTube Channel Monitor Started")
        print(f"⏰ Time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"📁 Skill Dir: {self.skill_dir}\n")

        try:
            # Load config and check channels
            result = self.add_youtube_videos_to_queue(
                videos_per_channel=videos_per_channel
            )

            elapsed = (datetime.now() - start_time).total_seconds()

            print(f"\n{'='*60}")
            print(f"📊 SUMMARY")
            print(f"{'='*60}")
            print(f"⏱️  Elapsed: {elapsed:.1f} seconds")
            print(f"📺 Channels checked: {result['checked']}")
            print(f"📹 Videos added: {result['added']}")
            print(f"⏭️  Videos skipped: {result['skipped']}")

            return result

        except FileNotFoundError as e:
            print(f"❌ Config file not found: {e}")
            self.results['errors'] += 1
            return self.results
        except Exception as e:
            print(f"❌ Error: {e}")
            self.results['errors'] += 1
            return self.results


def main():
    """Main entry point for channel monitor."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Check YouTube channels for new videos"
    )
    parser.add_argument(
        "--videos-per-channel",
        type=int,
        default=3,
        help="Max videos to check per channel (default: 3)"
    )
    parser.add_argument(
        "--channels-file",
        type=str,
        default=None,
        help="Path to channels config JSON"
    )
    parser.add_argument(
        "--json-output",
        action="store_true",
        help="Output results in JSON format"
    )

    args = parser.parse_args()

    monitor = YouTubeChannelMonitor(channels_file=args.channels_file)
    result = monitor.run(videos_per_channel=args.videos_per_channel)

    if args.json_output:
        print(f"\nRESULT: {json.dumps(result, indent=2, ensure_ascii=False)}")

    # Exit with error if there were errors
    if result.get('errors', 0) > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
