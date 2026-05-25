#!/usr/bin/env python3
"""
Rename audio files from video ID to original YouTube title.
Usage: python3 rename_with_title.py [--dry-run] [--video-id ID]
"""
import os
import re
import sys
import shutil
import subprocess
import concurrent.futures

def sanitize_filename(text, max_length=80):
    """Convert text to safe filename."""
    # Keep only safe chars
    text = re.sub(r'[^\w\s\-–—]', '', text)
    # Replace multiple spaces
    text = re.sub(r'\s+', ' ', text).strip()
    # Truncate intelligently
    if len(text) > max_length:
        text = text[:max_length].rsplit(' ', 1)[0]
    return text

def get_youtube_title(video_id):
    """Get original YouTube video title using yt-dlp."""
    try:
        result = subprocess.run(
            ['yt-dlp', '--print', '%(title)s', 
             f'https://youtube.com/watch?v={video_id}'],
            capture_output=True, text=True, timeout=30
        )
        title = result.stdout.strip()
        if title and not title.startswith('ERROR') and len(title) > 5:
            return title
    except Exception:
        pass
    
    # Fallback: check for cached info.json
    info_file = f"input/{video_id}.info.json"
    if os.path.exists(info_file):
        try:
            with open(info_file, 'r') as f:
                import json
                data = json.load(f)
                return data.get('title')
        except Exception:
            pass
    
    return None

def get_all_titles(video_ids):
    """Fetch titles in parallel."""
    titles = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        future_to_id = {executor.submit(get_youtube_title, vid): vid for vid in video_ids}
        for future in concurrent.futures.as_completed(future_to_id):
            vid = future_to_id[future]
            try:
                title = future.result()
                if title:
                    titles[vid] = title
                    print(f"  ✓ {vid}: {title[:60]}...")
                else:
                    print(f"  ✗ {vid}: Could not fetch title")
            except Exception as e:
                print(f"  ✗ {vid}: {e}")
    return titles

def rename_files(video_id, title, dry_run=True):
    """Rename audio file from ID to title."""
    audio_dir = "audio"
    
    old_path = f"{audio_dir}/{video_id}.ru.mp3"
    if not os.path.exists(old_path):
        print(f"  ❌ Audio not found: {old_path}")
        return False
    
    if not title:
        print(f"  ⚠️  No title found for {video_id}, skipping")
        return False
    
    # Create nice filename
    safe_title = sanitize_filename(title)
    new_name = f"{safe_title}.ru.mp3"
    new_path = f"{audio_dir}/{new_name}"
    
    # Handle duplicates
    counter = 1
    base_new = new_path
    while os.path.exists(new_path) and new_path != old_path:
        stem = base_new.replace('.ru.mp3', '')
        new_path = f"{stem}_{counter}.ru.mp3"
        counter += 1
    
    if new_path == old_path:
        print(f"  ℹ️  Already named correctly: {new_name}")
        return True
    
    if dry_run:
        print(f"  [DRY-RUN] Would rename:")
        print(f"    From: {video_id}.ru.mp3")
        print(f"    To:   {new_name}")
    else:
        shutil.move(old_path, new_path)
        print(f"  ✅ Renamed:")
        print(f"    From: {video_id}.ru.mp3")
        print(f"    To:   {new_name}")
    
    return True

def main():
    dry_run = "--dry-run" in sys.argv
    video_id = None
    
    # Check for --video-id
    for i, arg in enumerate(sys.argv):
        if arg == "--video-id" and i + 1 < len(sys.argv):
            video_id = sys.argv[i + 1]
    
    if dry_run:
        print("🔍 DRY RUN — no files will be changed\n")
    
    renamed = 0
    skipped = 0
    
    if video_id:
        # Single video
        print(f"Processing: {video_id}")
        title = get_youtube_title(video_id)
        if rename_files(video_id, title, dry_run):
            renamed += 1
        else:
            skipped += 1
    else:
        # All videos with audio
        audio_dir = "audio"
        if not os.path.exists(audio_dir):
            print(f"❌ Audio directory not found: {audio_dir}")
            return
        
        # Get all .ru.mp3 files that look like IDs
        files = [f for f in os.listdir(audio_dir) if f.endswith('.ru.mp3')]
        video_ids = []
        for filename in sorted(files):
            vid = filename.replace('.ru.mp3', '')
            # Only process if looks like a video ID (no spaces, alphanumeric)
            if ' ' not in vid and re.match(r'^[A-Za-z0-9_-]{5,20}$', vid):
                video_ids.append(vid)
        
        print(f"Found {len(video_ids)} video IDs to process\n")
        print("Fetching titles from YouTube...")
        
        # Fetch all titles first
        titles = get_all_titles(video_ids)
        
        print(f"\nGot {len(titles)} titles\n")
        
        # Now rename
        for vid in video_ids:
            title = titles.get(vid)
            print(f"\nProcessing: {vid}")
            if rename_files(vid, title, dry_run):
                renamed += 1
            else:
                skipped += 1
    
    print(f"\n📊 Summary:")
    print(f"   Renamed: {renamed}")
    print(f"   Skipped: {skipped}")
    
    if dry_run and renamed > 0:
        print(f"\n💡 Run without --dry-run to actually rename files")

if __name__ == "__main__":
    main()
