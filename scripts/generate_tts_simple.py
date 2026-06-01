#!/usr/bin/env python3
"""
Split large TTS text file into smaller chunks and generate audio for each.
Then merge all chunks into a single output file.
"""
import sys
import os
import asyncio
import subprocess
from pathlib import Path
from edge_tts import Communicate

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


async def main():
    text_file = sys.argv[1]
    output_file = sys.argv[2]
    voice = sys.argv[3] if len(sys.argv) > 3 else "ru-RU-DmitryNeural"
    
    text = load_text(text_file)
    chunks = chunk_text(text)
    
    print(f"Text: {len(text)} chars, {len(chunks)} chunks")
    
    chunk_dir = "/tmp/tts_oxerUfMFuCU"
    os.makedirs(chunk_dir, exist_ok=True)
    
    chunk_files = []
    for i, chunk in enumerate(chunks, 1):
        chunk_path = os.path.join(chunk_dir, f"chunk_{i:04d}.mp3")
        
        if os.path.exists(chunk_path) and os.path.getsize(chunk_path) > 1000:
            print(f"Chunk {i}/{len(chunks)} already exists, skipping")
            chunk_files.append(chunk_path)
            continue
            
        print(f"Generating chunk {i}/{len(chunks)} ({len(chunk)} chars)...", flush=True)
        try:
            await generate_chunk(chunk, voice, chunk_path)
            if os.path.exists(chunk_path) and os.path.getsize(chunk_path) > 0:
                chunk_files.append(chunk_path)
                print(f"  -> done", flush=True)
            else:
                print(f"  -> empty audio!", flush=True)
                return 1
        except Exception as e:
            print(f"  -> error: {e}", flush=True)
            return 1
    
    print(f"Merging {len(chunk_files)} chunks...", flush=True)
    if not merge_audio(chunk_files, output_file):
        print("ffmpeg merge failed", flush=True)
        return 1
    
    print(f"SUCCESS: {output_file}", flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
