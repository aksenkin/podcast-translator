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
        print(f"❌ Error: File not found: {file_path}")
        return ""
    except Exception as e:
        print(f"❌ Error reading file: {e}")
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
        print(f"❌ Error creating temp dir: {e}")
        return []

    audio_segments = []

    for i, chunk in enumerate(chunks, 1):
        print(f"Processing chunk {i}/{len(chunks)}...")

        try:
            communicate = Communicate(chunk, voice)
            chunk_file = os.path.join(temp_dir, f"chunk_{i:03d}.mp3")
            await communicate.save(chunk_file)

            if os.path.exists(chunk_file) and os.path.getsize(chunk_file) > 0:
                audio_segments.append(chunk_file)
                print(f"✓ Chunk {i} done: {os.path.getsize(chunk_file) / 1024:.1f} KB")
            else:
                print(f"❌ Chunk {i} failed: empty file")
        except Exception as e:
            print(f"❌ Chunk {i} failed: {e}")

    return audio_segments

def merge_with_ffmpeg(audio_files, output_file):
    """
    Merge audio files using ffmpeg concat demuxer
    This function handles errors gracefully
    """
    if not audio_files:
        print("❌ Error: No audio files to merge")
        return False

    # Verify all audio files exist
    for audio_file in audio_files:
        if not os.path.exists(audio_file):
            print(f"❌ Error: Audio file not found: {audio_file}")
            return False
        if os.path.getsize(audio_file) == 0:
            print(f"❌ Error: Empty audio file: {audio_file}")
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
        print(f"❌ Error creating concat file: {e}")
        return False

    print(f"✓ Merge list created: {len(audio_files)} files")

    # Run ffmpeg concat demuxer
    cmd = [
        'ffmpeg',
        '-f', 'concat',
        '-safe', '0',
        '-i', concat_file,
        '-c', 'copy',
        '-map_metadata', '0',
        '-y',  # Overwrite output file
        output_file
    ]

    try:
        print(f"🎵 Running ffmpeg...")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        if result.returncode == 0:
            print(f"✓ Audio merged successfully: {output_file}")
            if os.path.exists(output_file):
                file_size = os.path.getsize(output_file)
                print(f"📊 Final file size: {file_size / 1024:.1f} KB")
            return True
        else:
            print(f"❌ FFmpeg error (code {result.returncode})")
            print(f"   stdout: {result.stdout}")
            print(f"   stderr: {result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        print("❌ Error: FFmpeg timeout (300s)")
        return False
    except subprocess.CalledProcessError as e:
        print(f"❌ Error: FFmpeg crashed")
        print(f"   Return code: {e.returncode}")
        print(f"   stdout: {e.stdout}")
        print(f"   stderr: {e.stderr}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False
    finally:
        # Cleanup concat file
        if os.path.exists(concat_file):
            try:
                os.remove(concat_file)
            except:
                pass

async def generate_tts(text_file, output_file, voice="ru-RU-DmitryNeural"):
    """Generate Russian TTS audio with proper error handling"""
    text = load_text(text_file)

    if not text.strip():
        print("❌ Error: Empty text file")
        return False

    print(f"📄 Generating TTS for: {text_file}")
    print(f"📊 Text length: {len(text)} characters")
    print(f"🎙️  Voice: {voice}")

    # Chunk the text
    chunks = chunk_text(text)
    print(f"📝 Split into {len(chunks)} chunks")

    # Generate audio for each chunk
    temp_dir = tempfile.mkdtemp(prefix="tts_chunks_")
    print(f"📁 Temp dir: {temp_dir}")

    try:
        audio_segments = await generate_audio_chunks(chunks, voice, temp_dir)

        if not audio_segments:
            print("❌ Error: No audio segments generated")
            return False

        print(f"✓ Generated {len(audio_segments)} audio segments")

        # Merge with ffmpeg concat demuxer
        success = merge_with_ffmpeg(audio_segments, output_file)

        return success

    finally:
        # Cleanup temp files
        print("🧹 Cleaning up temp files...")
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

        print(f"✓ Cleanup complete")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 generate_tts.py <input_text_file> <output_audio_file> [voice]")
        print("")
        print("Arguments:")
        print("  input_text_file   - Path to Russian text file")
        print("  output_audio_file - Path to output MP3 file")
        print("  voice             - Optional TTS voice (default: ru-RU-DmitryNeural)")
        print("")
        print("Available Russian voices:")
        print("  ru-RU-DmitryNeural  - Male voice (default)")
        print("  ru-RU-SvetlanaNeural - Female voice")
        print("")
        print("Example:")
        print("  python3 generate_tts.py translations/episode_ru.txt audio/episode_ru.mp3")
        print("  python3 generate_tts.py translations/episode_ru.txt audio/episode_ru.mp3 ru-RU-SvetlanaNeural")
        sys.exit(1)

    text_file = sys.argv[1]
    output_file = sys.argv[2]
    voice = sys.argv[3] if len(sys.argv) > 3 else "ru-RU-DmitryNeural"

    asyncio.run(generate_tts(text_file, output_file, voice))
