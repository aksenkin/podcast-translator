#!/usr/bin/env python3
"""
Generate Russian TTS using Edge TTS with proper error handling
This version fixes TypeError and handles FFmpeg errors gracefully
"""

import sys
import os
import asyncio
import tempfile
import subprocess
from edge_tts import Communicate

def load_text(file_path):
    """Load text from file"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        print(f"ERROR: File not found: {file_path}", flush=True)
        return ""
    except Exception as e:
        print(f"ERROR: Error reading file: {e}", flush=True)
        return ""

def chunk_text(text, max_chars=1000):
    """Split text into chunks for TTS"""
    lines = text.replace('. ', '.\n').replace('! ', '!\n').replace('? ', '?\n').split('\n')
    chunks = []
    current_chunk = ""

    for sentence in lines:
        if len(current_chunk) + len(sentence) + 1 <= max_chars:
            current_chunk += " " + sentence if current_chunk else sentence
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = sentence

    if current_chunk:
        chunks.append(current_chunk.strip())

    return chunks

async def generate_audio_chunks(chunks, voice, temp_dir):
    """Generate TTS audio for all chunks"""
    try:
        os.makedirs(temp_dir, exist_ok=True)
    except Exception as e:
        print(f"ERROR: Error creating temp dir: {e}", flush=True)
        return []

    audio_segments = []

    for i, chunk in enumerate(chunks, 1):
        progress = (i / len(chunks)) * 100
        print(f"STATUS: Processing chunk {i}/{len(chunks)} ({progress:.1f}%)", flush=True)

        try:
            communicate = Communicate(chunk, voice)
            chunk_file = os.path.join(temp_dir, f"chunk_{i:03d}.mp3")
            await communicate.save(chunk_file)

            if os.path.exists(chunk_file) and os.path.getsize(chunk_file) > 0:
                audio_segments.append(chunk_file)
                print(f"HEARTBEAT: Chunk {i}/{len(chunks)} done: {os.path.getsize(chunk_file) / 1024:.1f} KB", flush=True)
            else:
                print(f"ERROR: Chunk {i} failed: empty file", flush=True)
        except Exception as e:
            print(f"ERROR: Chunk {i} failed: {e}", flush=True)

    return audio_segments

def merge_with_ffmpeg(audio_files, output_file, title=None, artist=None):
    """
    Merge audio files using ffmpeg concat demuxer
    This function handles errors gracefully

    Args:
        audio_files: List of audio file paths to merge
        output_file: Path for output MP3 file
        title: Metadata title (video title)
        artist: Metadata artist (channel name)
    """
    if not audio_files:
        print("ERROR: No audio files to merge", flush=True)
        return False

    # Verify all audio files exist
    for audio_file in audio_files:
        if not os.path.exists(audio_file):
            print(f"ERROR: Audio file not found: {audio_file}", flush=True)
            return False
        if os.path.getsize(audio_file) == 0:
            print(f"ERROR: Empty audio file: {audio_file}", flush=True)
            return False

    # Create concat file
    temp_dir = os.path.dirname(audio_files[0])
    concat_file = os.path.join(temp_dir, "concat_list.txt")

    try:
        with open(concat_file, 'w', encoding='utf-8') as f:
            for audio_file in audio_files:
                abs_path = os.path.abspath(audio_file)
                f.write(f"file '{abs_path}'\n")
    except Exception as e:
        print(f"ERROR: Error creating concat file: {e}", flush=True)
        return False

    print(f"STATUS: Merge list created: {len(audio_files)} files", flush=True)

    # Run ffmpeg concat demuxer with metadata
    cmd = [
        'ffmpeg',
        '-f', 'concat',
        '-safe', '0',
        '-i', concat_file,
        '-c', 'copy',
        '-map_metadata', '0',
    ]

    # Add metadata tags if provided
    if title:
        cmd.extend(['-metadata', f"title={title}"])
        print(f"STATUS: Setting title: {title}", flush=True)
    if artist:
        cmd.extend(['-metadata', f"artist={artist}"])
        print(f"STATUS: Setting artist: {artist}", flush=True)

    cmd.extend(['-y', output_file])  # Overwrite output file

    try:
        print(f"STATUS: Running ffmpeg...", flush=True)
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        if result.returncode == 0:
            print(f"SUCCESS: Audio merged successfully: {output_file}", flush=True)
            if os.path.exists(output_file):
                file_size = os.path.getsize(output_file)
                print(f"STATUS: Final file size: {file_size / 1024:.1f} KB", flush=True)
            return True
        else:
            print(f"ERROR: FFmpeg error (code {result.returncode})", flush=True)
            print(f"ERROR: stdout: {result.stdout}", flush=True)
            print(f"ERROR: stderr: {result.stderr}", flush=True)
            return False

    except subprocess.TimeoutExpired:
        print("ERROR: FFmpeg timeout (300s)", flush=True)
        return False
    except subprocess.CalledProcessError as e:
        print(f"ERROR: FFmpeg crashed", flush=True)
        print(f"ERROR: Return code: {e.returncode}", flush=True)
        print(f"ERROR: stdout: {e.stdout}", flush=True)
        print(f"ERROR: stderr: {e.stderr}", flush=True)
        return False
    except Exception as e:
        print(f"ERROR: {e}", flush=True)
        return False
    finally:
        # Cleanup concat file
        if os.path.exists(concat_file):
            try:
                os.remove(concat_file)
            except:
                pass

async def generate_tts(text_file, output_file, voice="ru-RU-DmitryNeural", title=None, artist=None):
    """Generate Russian TTS audio with proper error handling

    Args:
        text_file: Path to input text file
        output_file: Path to output MP3 file
        voice: TTS voice to use
        title: Metadata title (video title)
        artist: Metadata artist (channel name)
    """
    text = load_text(text_file)

    if not text.strip():
        print("ERROR: Empty text file", flush=True)
        return False

    print(f"STATUS: Generating TTS for: {text_file}", flush=True)
    print(f"STATUS: Text length: {len(text)} characters", flush=True)
    print(f"STATUS: Voice: {voice}", flush=True)

    # Chunk the text
    chunks = chunk_text(text)
    print(f"STATUS: Split into {len(chunks)} chunks", flush=True)

    # Generate audio for each chunk
    temp_dir = tempfile.mkdtemp(prefix="tts_chunks_")
    print(f"STATUS: Temp dir: {temp_dir}", flush=True)

    try:
        audio_segments = await generate_audio_chunks(chunks, voice, temp_dir)

        if not audio_segments:
            print("ERROR: No audio segments generated", flush=True)
            return False

        print(f"STATUS: Generated {len(audio_segments)} audio segments", flush=True)

        # Merge with ffmpeg concat demuxer and add metadata
        success = merge_with_ffmpeg(audio_segments, output_file, title=title, artist=artist)

        return success

    finally:
        # Cleanup temp files
        print("STATUS: Cleaning up temp files...", flush=True)
        for segment in audio_segments:
            if os.path.exists(segment):
                try:
                    os.remove(segment)
                except:
                    pass

        # Remove temp directory
        try:
            os.rmdir(temp_dir)
        except:
            pass

        print(f"SUCCESS: Cleanup complete", flush=True)

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 generate_tts.py <input_text_file> <output_audio_file> [voice] [title] [artist]")
        print("")
        print("Arguments:")
        print("  input_text_file   - Path to Russian text file")
        print("  output_audio_file - Path to output MP3 file")
        print("  voice             - Optional TTS voice (default: ru-RU-DmitryNeural)")
        print("  title             - Optional metadata title (video title)")
        print("  artist            - Optional metadata artist (channel name)")
        print("")
        print("Available Russian voices:")
        print("  ru-RU-DmitryNeural  - Male voice (default)")
        print("  ru-RU-SvetlanaNeural - Female voice")
        print("")
        print("Example:")
        print("  python3 generate_tts.py translations/episode_ru.txt audio/episode_ru.mp3")
        print("  python3 generate_tts.py translations/episode_ru.txt audio/episode_ru.mp3 ru-RU-SvetlanaNeural")
        print("  python3 generate_tts.py translations/episode_ru.txt audio/episode_ru.mp3 ru-RU-DmitryNeural \"Video Title\" \"Channel Name\"")
        sys.exit(1)

    text_file = sys.argv[1]
    output_file = sys.argv[2]
    voice = sys.argv[3] if len(sys.argv) > 3 else "ru-RU-DmitryNeural"
    title = sys.argv[4] if len(sys.argv) > 4 else None
    artist = sys.argv[5] if len(sys.argv) > 5 else None

    asyncio.run(generate_tts(text_file, output_file, voice, title, artist))
