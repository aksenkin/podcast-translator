#!/usr/bin/env python3
"""
Migrate failed videos from old format to new retry-enabled format.

Old format: videos with 'failedAt' and 'error' in 'completed' list
New format: separate 'failed' list with 'attempts' and 'lastError'
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timezone


def migrate_failed_videos(queue_file):
    """Migrate old failed video entries to new format."""
    
    with open(queue_file, 'r') as f:
        data = json.load(f)
    
    # Ensure new fields exist
    if 'failed' not in data:
        data['failed'] = []
    if 'notified' not in data:
        data['notified'] = []
    
    # Find videos with failedAt in completed list (old format)
    old_completed = data['completed']
    new_completed = []
    migrated_count = 0
    
    for video in old_completed:
        if 'failedAt' in video:
            # Convert to new format
            new_failed = {
                'videoId': video['videoId'],
                'title': video['title'],
                'url': video.get('url', f"https://www.youtube.com/watch?v={video['videoId']}"),
                'channel': video.get('channel', 'Unknown'),
                'addedAt': video.get('addedAt', ''),
                'failedAt': video['failedAt'],
                'error': video.get('error', 'Unknown error'),
                'attempts': video.get('attempts', 1),  # Default 1 attempt
                'lastError': video.get('error', 'Unknown error'),
                'statusHistory': [
                    {
                        'status': 'failed',
                        'timestamp': video['failedAt'],
                        'error': video.get('error', 'Unknown error')
                    }
                ]
            }
            data['failed'].append(new_failed)
            migrated_count += 1
            print(f"Migrated: {video['title']} ({video['videoId']})")
            print(f"  Error: {video.get('error', 'Unknown error')[:80]}...")
        else:
            new_completed.append(video)
    
    data['completed'] = new_completed
    
    # Save back
    with open(queue_file, 'w') as f:
        json.dump(data, indent=2, ensure_ascii=False, fp=f)
    
    print(f"\n✅ Migration complete:")
    print(f"  Migrated: {migrated_count} failed videos")
    print(f"  Completed (success): {len(new_completed)}")
    print(f"  Failed (new list): {len(data['failed'])}")
    print(f"  Pending: {len(data['pending'])}")
    
    return migrated_count


def show_failed_videos(queue_file):
    """Show all failed videos with their details."""
    
    with open(queue_file, 'r') as f:
        data = json.load(f)
    
    failed = data.get('failed', [])
    
    if not failed:
        print("No failed videos found.")
        return
    
    print(f"\n❌ Failed videos ({len(failed)}):")
    print("="*80)
    
    for i, video in enumerate(failed, 1):
        print(f"\n{i}. \"{video['title']}\"")
        print(f"   Video ID: {video['videoId']}")
        print(f"   URL: {video.get('url', 'N/A')}")
        print(f"   Channel: {video.get('channel', 'N/A')}")
        print(f"   Attempts: {video.get('attempts', 1)}")
        print(f"   Last Error: {video.get('lastError', 'N/A')[:100]}...")
        print(f"   Failed at: {video.get('failedAt', 'N/A')}")


def retry_all_failed(queue_file, queue_manager_path=None):
    """Return all failed videos to pending queue for retry."""
    
    sys.path.insert(0, str(Path(queue_file).parent))
    from queue_manager import QueueManager
    
    qm = QueueManager(queue_file)
    
    with open(queue_file, 'r') as f:
        data = json.load(f)
    
    failed = data.get('failed', [])
    if not failed:
        print("No failed videos to retry.")
        return 0
    
    retry_count = 0
    still_failed = []
    
    for video in failed:
        # Check if video has < 3 attempts
        attempts = video.get('attempts', 1)
        
        if attempts < 3:
            # Return to pending
            video['attempts'] = attempts
            video['lastError'] = video.get('error', 'Previous failure')
            # Remove timestamps that will be regenerated
            video.pop('failedAt', None)
            video.pop('statusHistory', None)
            
            data['pending'].insert(0, video)
            retry_count += 1
            print(f"🔄 Returned to pending: {video['title']} (attempt {attempts}/3)")
        else:
            # Keep in failed
            still_failed.append(video)
            print(f"❌ Kept in failed (3+ attempts): {video['title']}")
    
    data['failed'] = still_failed
    
    with open(queue_file, 'w') as f:
        json.dump(data, indent=2, ensure_ascii=False, fp=f)
    
    print(f"\n✅ Retry complete:")
    print(f"  Returned to pending: {retry_count}")
    print(f"  Still failed (3+ attempts): {len(still_failed)}")
    
    return retry_count


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Migrate and manage failed videos in queue"
    )
    parser.add_argument(
        "command",
        choices=["migrate", "show", "retry"],
        help="Command: migrate old format, show failed, retry all"
    )
    parser.add_argument(
        "--queue-file",
        default="youtube-queue.json",
        help="Path to queue JSON file"
    )
    
    args = parser.parse_args()
    
    queue_file = Path(args.queue_file)
    if not queue_file.is_absolute():
        queue_file = Path(__file__).parent / queue_file
    
    if not queue_file.exists():
        print(f"❌ Queue file not found: {queue_file}")
        sys.exit(1)
    
    if args.command == "migrate":
        print(f"🔄 Migrating failed videos in {queue_file}...")
        migrate_failed_videos(queue_file)
    
    elif args.command == "show":
        show_failed_videos(queue_file)
    
    elif args.command == "retry":
        print(f"🔄 Returning failed videos to pending queue...")
        retry_all_failed(queue_file)


if __name__ == "__main__":
    main()
