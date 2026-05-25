#!/usr/bin/env python3
"""
Generate Russian TTS using Edge TTS with chunking and FFmpeg merge.

Splits long text into ~1000-char chunks, generates audio for each,
then merges with ffmpeg. Edge TTS silently truncates long texts,
so chunking is required for files over ~5000 chars.

Usage:
    python3 generate_tts.py <text_file> <output_file> [voice] [title] [artist]

Progress output:
    STATUS: Step updates
    SUCCESS: Completion confirmation
    ERROR: Failure indication
"""

import sys
import os
import asyncio
import tempfile
import subprocess
from pathlib import Path
from edge_tts import Communicate

sys.path.insert(0, str(Path(__file__).parent))
from heartbeat import TranscriptionHeartbeat

MAX_CHARS = 1000


def load_text(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        return f.read().strip()


def chunk_text(text, max_chars=MAX_CHARS):
    """Split text into chunks at sentence boundaries."""
    lines = text.replace('. ', '.\n').replace('! ', '!\n').replace('? ', '?\n').split('\n')
    chunks = []
    current = ""

    for line in lines:
        if len(current) + len(line) + 1 <= max_chars:
            current += (" " + line) if current else line
        else:
            if current:
                chunks.append(current.strip())
            current = line

    if current:
        chunks.append(current.strip())

    return chunks


async def generate_chunk(chunk_text, voice, output_path):
    """Generate TTS for a single chunk."""
    communicate = Communicate(chunk_text, voice)
    await communicate.save(output_path)


def merge_audio(chunk_files, output_file):
    """Merge chunk audio files with ffmpeg."""
    list_file = output_file + ".list.txt"
    with open(list_file, 'w') as f:
        for cf in chunk_files:
            f.write(f"file '{cf}'\n")

    result = subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_file,
         "-c", "copy", output_file],
        capture_output=True, text=True
    )

    os.unlink(list_file)
    return result.returncode == 0


async def generate_tts(text_file, output_file, voice="ru-RU-DmitryNeural",
                       title=None, artist=None, video_id=None):
    """Generate TTS audio from text file with chunking and heartbeat."""
    
    # Initialize heartbeat for TTS phase
    hb = TranscriptionHeartbeat(video_id) if video_id else None
    
    if hb:
        hb.phase("tts", f"Starting TTS generation: {os.path.basename(text_file)}")
    
    text = load_text(text_file)
    if not text:
        print("ERROR: Empty text file", flush=True)
        if hb:
            hb.fail("Empty text file")
        return False

    print(f"STATUS: TTS generating — {len(text)} chars, voice: {voice}", flush=True)
    if hb:
        hb.heartbeat(f"Text loaded: {len(text)} chars")
    
    chunks = chunk_text(text)
    print(f"STATUS: Split into {len(chunks)} chunks", flush=True)
    if hb:
        hb.update_progress(5, f"Split into {len(chunks)} TTS chunks", phase="tts")

    with tempfile.TemporaryDirectory() as tmp_dir:
        chunk_files = []

        for i, chunk in enumerate(chunks, 1):
            chunk_path = os.path.join(tmp_dir, f"chunk_{i:04d}.mp3")
            print(f"STATUS: Generating chunk {i}/{len(chunks)} ({len(chunk)} chars)", flush=True)
            
            if hb:
                progress = int((i / len(chunks)) * 90)  # 5-95%
                hb.update_progress(progress, f"TTS chunk {i}/{len(chunks)}", phase="tts")

            try:
                await generate_chunk(chunk, voice, chunk_path)
                if os.path.exists(chunk_path) and os.path.getsize(chunk_path) > 0:
                    chunk_files.append(chunk_path)
                    if hb:
                        hb.heartbeat(f"TTS chunk {i}/{len(chunks)} generated")
                else:
                    error = f"Chunk {i} produced empty audio"
                    print(f"ERROR: {error}", flush=True)
                    if hb:
                        hb.fail(error)
                    return False
            except Exception as e:
                error = f"Chunk {i} failed: {e}"
                print(f"ERROR: {error}", flush=True)
                if hb:
                    hb.fail(error)
                return False

        if not chunk_files:
            error = "No audio chunks generated"
            print(f"ERROR: {error}", flush=True)
            if hb:
                hb.fail(error)
            return False

        if len(chunk_files) == 1:
            # Single chunk — just copy
            import shutil
            shutil.copy2(chunk_files[0], output_file)
            if hb:
                hb.heartbeat("Single TTS chunk copied")
        else:
            # Merge chunks
            print(f"STATUS: Merging {len(chunk_files)} chunks with ffmpeg", flush=True)
            if hb:
                hb.update_progress(95, "Merging TTS chunks with ffmpeg", phase="tts")
            if not merge_audio(chunk_files, output_file):
                error = "ffmpeg merge failed"
                print(f"ERROR: {error}", flush=True)
                if hb:
                    hb.fail(error)
                return False
            if hb:
                hb.heartbeat("TTS chunks merged")

    # Add metadata if provided
    if title or artist:
        if hb:
            hb.heartbeat("Adding metadata")
        meta_path = output_file + ".meta.mp3"
        cmd = ["ffmpeg", "-y", "-i", output_file]
        if title:
            cmd.extend(["-metadata", f"title={title}"])
        if artist:
            cmd.extend(["-metadata", f"artist={artist}"])
        cmd.extend(["-c", "copy", meta_path])

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            os.replace(meta_path, output_file)
        else:
            # Non-fatal — audio still works without metadata
            if os.path.exists(meta_path):
                os.unlink(meta_path)

    duration_cmd = ["ffprobe", "-i", output_file,
                    "-show_entries", "format=duration",
                    "-v", "quiet", "-of", "csv=p=0"]
    dur_result = subprocess.run(duration_cmd, capture_output=True, text=True)
    duration = float(dur_result.stdout.strip()) if dur_result.returncode == 0 else 0

    print(f"SUCCESS: TTS audio saved to {output_file} ({duration:.0f}s)", flush=True)
    
    # TTS complete — finish heartbeat
    if hb:
        hb.update_progress(100, f"TTS complete: {duration:.0f}s", phase="complete")
        hb.finish()
    
    return True


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: generate_tts.py <text_file> <output_file> [voice] [title] [artist]")
        print("")
        print("Voice options (default: ru-RU-DmitryNeural):")
        print("  - ru-RU-DmitryNeural (male)")
        print("  - ru-RU-SvetlanaNeural (female)")
        print("  - ru-RU-DariyaNeural (female)")
        sys.exit(1)

    text_file = sys.argv[1]
    output_file = sys.argv[2]
    voice = sys.argv[3] if len(sys.argv) > 3 else "ru-RU-DmitryNeural"
    title = sys.argv[4] if len(sys.argv) > 4 else None
    artist = sys.argv[5] if len(sys.argv) > 5 else None
    video_id = sys.argv[6] if len(sys.argv) > 6 else None

    success = asyncio.run(generate_tts(text_file, output_file, voice, title, artist, video_id))
    sys.exit(0 if success else 1)