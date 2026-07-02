#!/usr/bin/env python3
"""
Hermes Queue Processor — processes videos from the queue sequentially.

Optimized for Raspberry Pi:
- Whisper model loaded ONCE, held in memory for entire queue
- Chunking for long audio (5-min chunks, single model instance)
- Batch translation (GoogleTranslator with batching)
- PID-lock prevents parallel processes
- Progress heartbeat for long operations
- Disk space check before chunking

Usage:
    python3 hermes_queue_processor.py [--max-videos N] [--voice VOICE]
"""

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from datetime import datetime

SKILL_DIR = Path(__file__).parent
sys.path.insert(0, str(SKILL_DIR))
sys.path.insert(0, str(SKILL_DIR / "scripts"))
from queue_manager import QueueManager
from log_helper import log_event
from transcribe_chunk import transcribe_chunk_with_model

# Whisper model cache (loaded once, reused for all videos)
_model = None
CACHE_DIR = Path.home() / ".cache" / "huggingface" / "hub"

LOCK_FILE = Path("/tmp/podcast-hermes-processor.lock")
TIMEOUT_TRANSCRIBE_ALL = 7200   # 2 hours for --all chunked transcription
TIMEOUT_TRANSCRIBE_SHORT = 1800 # 30 min for short video transcription
TIMEOUT_DOWNLOAD = 300          # 5 min for yt-dlp
TIMEOUT_TTS = 600               # 10 min for TTS generation
TIMEOUT_PREPARE = 60            # 1 min for prepare_transcript


def acquire_lock():
    """Acquire PID-lock to prevent parallel pipeline runs."""
    if LOCK_FILE.exists():
        try:
            old_pid = int(LOCK_FILE.read_text().strip())
            os.kill(old_pid, 0)
            print(f"STATUS: Pipeline already running (PID {old_pid})")
            return False
        except (OSError, ProcessLookupError, ValueError):
            LOCK_FILE.unlink(missing_ok=True)
    LOCK_FILE.write_text(str(os.getpid()))
    return True


def release_lock():
    """Release PID-lock."""
    try:
        LOCK_FILE.unlink(missing_ok=True)
    except OSError:
        pass


def check_disk_space(required_mb=500):
    """Check if there's enough disk space."""
    try:
        stat = os.statvfs(str(SKILL_DIR))
        available_mb = (stat.f_bavail * stat.f_frsize) / (1024 * 1024)
        if available_mb < required_mb:
            print(f"ERROR: Not enough disk space: {available_mb:.0f}MB < {required_mb}MB required")
            return False
        return True
    except Exception:
        return True  # Skip check if we can't determine


def run_with_progress(cmd, timeout, step_name, line_callback=None):
    """Run subprocess with line-by-line output (prevents buffer overflow).

    Prints progress lines as they come, with heartbeat every 10 seconds.
    """
    print(f"STATUS: {step_name}...", flush=True)
    start = time.time()
    last_heartbeat = time.time()

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True
    )

    output_lines = []
    try:
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                output_lines.append(line)
                # Print progress lines
                if line.startswith(("STATUS:", "HEARTBEAT:", "SUCCESS:", "ERROR:")):
                    print(f"  {line}", flush=True)
                elif line_callback:
                    line_callback(line)

                # Heartbeat for long operations
                now = time.time()
                if now - last_heartbeat >= 10:
                    elapsed = now - start
                    print(f"HEARTBEAT: {step_name} — {elapsed:.0f}s elapsed", flush=True)
                    last_heartbeat = now
    except KeyboardInterrupt:
        proc.kill()
        raise
    finally:
        proc.wait(timeout=30)

    elapsed = time.time() - start
    if proc.returncode != 0:
        # Include last 5 lines of output as error context
        tail = "\n".join(output_lines[-5:])
        raise Exception(f"{step_name} failed (exit {proc.returncode}, {elapsed:.0f}s):\n{tail}")

    print(f"SUCCESS: {step_name} completed ({elapsed:.0f}s)", flush=True)
    return output_lines


def get_whisper_model(model_size="small"):
    """Load whisper model ONCE and cache it in memory.

    First call: loads model (~7 min cold, ~2 sec warm from HF cache).
    Subsequent calls: returns cached instance.

    Uses local snapshot path from HF cache to avoid network calls that
    can hang for 20+ minutes on RPi (see Pitfall #24).

    Returns:
        WhisperModel instance
    """
    global _model
    if _model is not None:
        return _model

    from faster_whisper import WhisperModel

    # Find the local model snapshot path to avoid HuggingFace network calls
    model_path = model_size
    try:
        cache_snapshots = CACHE_DIR / f"models--Systran--faster-whisper-{model_size}" / "snapshots"
        if cache_snapshots.exists():
            snapshots = list(cache_snapshots.iterdir())
            if snapshots:
                # Verify the snapshot has model.bin
                for snap in snapshots:
                    if (snap / "model.bin").exists():
                        model_path = str(snap)
                        print(f"STATUS: Using cached model: {model_path}", flush=True)
                        break
    except Exception as e:
        print(f"STATUS: Cache lookup failed ({e}), falling back to download", flush=True)

    print(f"STATUS: Loading Whisper model ({model_size})...", flush=True)
    start = time.time()

    _model = WhisperModel(
        model_path,
        device="cpu",
        compute_type="int8",
        cpu_threads=4,
        num_workers=2
    )

    elapsed = time.time() - start
    print(f"STATUS: Model loaded in {elapsed:.1f}s", flush=True)
    return _model


def transcribe_audio_inprocess(audio_file, output_dir, model, video_id=None):
    """Transcribe audio using a pre-loaded model (no subprocess).

    Writes transcript with timestamps [MM:SS - MM:SS] to output_dir/{name}.txt.

    Args:
        audio_file: Path to audio file
        output_dir: Directory for transcript output
        model: Pre-loaded WhisperModel instance
        video_id: Optional video ID for logging

    Returns:
        Path to transcript file, or None on failure
    """
    audio_path = Path(audio_file)
    transcript_file = Path(output_dir) / (audio_path.stem + ".txt")

    print(f"STATUS: Transcribing {audio_path.name}...", flush=True)

    try:
        segments, info = model.transcribe(
            str(audio_file),
            beam_size=1,
            vad_filter=False,
            word_timestamps=False,
            language=None
        )
    except Exception as e:
        print(f"ERROR: Transcription failed: {e}", flush=True)
        return None

    if not info:
        print("ERROR: No info returned from transcription", flush=True)
        return None

    print(f"STATUS: Language: {info.language}, Duration: {info.duration:.1f}s", flush=True)

    segment_count = 0
    last_heartbeat = time.time()

    with open(transcript_file, 'w', encoding='utf-8') as f:
        for segment in segments:
            segment_count += 1
            minutes_start = int(segment.start // 60)
            seconds_start = int(segment.start % 60)
            minutes_end = int(segment.end // 60)
            seconds_end = int(segment.end % 60)
            f.write(f"[{minutes_start:02d}:{seconds_start:02d} - {minutes_end:02d}:{seconds_end:02d}] {segment.text}\n")

            # Heartbeat every 10 seconds
            now = time.time()
            if now - last_heartbeat >= 10:
                print(f"HEARTBEAT: {segment_count} segments, time {minutes_start:02d}:{seconds_start:02d}", flush=True)
                last_heartbeat = now

    print(f"SUCCESS: {segment_count} segments → {transcript_file.name}", flush=True)
    return str(transcript_file)


def transcribe_chunks_inprocess(video_id, model):
    """Transcribe all pending chunks using a pre-loaded model.

    Reads {video_id}_chunks.json, transcribes all pending chunks sequentially,
    writes transcripts to chunks/ dir, updates chunk status.

    Args:
        video_id: Video ID (used to find chunks JSON)
        model: Pre-loaded WhisperModel instance

    Returns:
        Dict with result (allDone: True on success)
    """
    CHUNKS_DIR = SKILL_DIR / "chunks"
    chunks_json = CHUNKS_DIR / f"{video_id}_chunks.json"

    if not chunks_json.exists():
        return {"error": "no_chunks_json", "videoId": video_id}

    data = json.loads(chunks_json.read_text())
    pending = [c for c in data["chunks"] if c["status"] == "pending"]

    if not pending:
        return {"allDone": True, "videoId": video_id, "totalChunks": data["totalChunks"]}

    total = data["totalChunks"]
    print(f"STATUS: Transcribing {len(pending)} chunks (model already loaded)", flush=True)

    for chunk in pending:
        chunk_idx = chunk["index"]
        chunk_file = CHUNKS_DIR / chunk["file"]

        chunk["status"] = "transcribing"
        chunks_json.write_text(json.dumps(data, indent=2, ensure_ascii=False))

        print(f"STATUS: Chunk {chunk_idx}/{total} — {chunk['file']}", flush=True)
        start = time.time()

        success, segments, error = transcribe_chunk_with_model(model, chunk_file, str(CHUNKS_DIR))
        elapsed = time.time() - start

        if success:
            chunk["status"] = "done"
            log_event(video_id, "TRANSCRIBE_OK", chunk=f"{chunk_idx}/{total}",
                     duration=f"{elapsed:.0f}s", segments=segments)
            print(f"SUCCESS: Chunk {chunk_idx}/{total} done ({elapsed:.0f}s, {segments} segments)", flush=True)
        else:
            chunk["status"] = "failed"
            data["status"] = "failed"
            chunks_json.write_text(json.dumps(data, indent=2, ensure_ascii=False))
            log_event(video_id, "TRANSCRIBE_FAIL", chunk=f"{chunk_idx}/{total}", error=error)
            return {"error": "chunk_failed", "videoId": video_id, "failedChunk": chunk_idx}

        chunks_json.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    all_done = all(c["status"] == "done" for c in data["chunks"])
    if all_done:
        data["status"] = "assembling"
        chunks_json.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        return {"allDone": True, "videoId": video_id, "totalChunks": total}

    return {"videoId": video_id, "transcribed": len(pending)}


def run_pipeline_for_video(video, voice="ru-RU-DmitryNeural"):
    """Run the full podcast translation pipeline for one video.

    Optimized for Raspberry Pi:
    - Chunking for long audio (>5 min)
    - Model loaded once for all chunks
    - Batch translation to reduce API calls
    """
    video_id = video['videoId']
    youtube_url = video.get('url', f"https://www.youtube.com/watch?v={video_id}")
    # Use video title as basename (sanitized for filesystem safety)
    import re as _re
    safe_title = _re.sub(r'[\\/:*?"<>|]', '', video['title'])  # remove invalid chars
    safe_title = safe_title.strip().replace(' ', '_')[:80]  # spaces to underscores, max 80 chars
    basename = safe_title if safe_title else f"podcast_{video_id}"

    print(f"\n{'='*60}")
    print(f"🎙️ Processing: {video['title']}")
    print(f"📹 Video ID: {video_id}")
    print(f"🔗 URL: {youtube_url}")
    print(f"🎤 Voice: {voice}")
    print(f"{'='*60}\n")

    # Check disk space
    if not check_disk_space(500):
        raise Exception("Not enough disk space (need 500MB)")

    # Step 1: Download audio
    print("\n📥 Step 1: Downloading audio...")
    # Find node.js for yt-dlp JS runtime (YouTube requires it)
    import shutil as _shutil
    node_path = None
    for candidate in [
        "/home/dmaxy/.nvm/versions/node/v22.19.0/bin/node",
        "/usr/bin/node", "/usr/local/bin/node",
    ]:
        if Path(candidate).exists():
            node_path = candidate
            break
    if not node_path:
        # Try finding node via PATH
        node_path = _shutil.which("node")

    download_cmd = [
        "yt-dlp",
        "-x", "--audio-format", "mp3", "--audio-quality", "0",
        "-o", f"{SKILL_DIR}/input/{basename}.%(ext)s",
    ]
    if node_path:
        download_cmd += ["--js-runtimes", f"node:{node_path}", "--remote-components", "ejs:github"]
    download_cmd.append(youtube_url)
    run_with_progress(download_cmd, TIMEOUT_DOWNLOAD, "Downloading audio")

    # Find the downloaded file
    input_dir = SKILL_DIR / "input"
    input_files = list(input_dir.glob(f"{basename}.*"))
    if not input_files:
        raise Exception(f"Downloaded file not found: {basename}.*")
    input_file = input_files[0]
    print(f"✅ Downloaded: {input_file.name}")

    # Step 2: Chunk + Transcribe
    print("\n⏱️ Step 2: Chunking and transcribing...")

    # Check if chunking is needed
    chunk_cmd = ["python3", str(SKILL_DIR / "scripts" / "chunk_audio.py"), str(input_file)]
    chunk_output = run_with_progress(chunk_cmd, 120, "Checking audio duration")

    # Parse chunk result — chunk_audio.py outputs pretty-printed JSON (indent=2)
    # so individual lines are not valid JSON. Join all output and parse.
    chunk_data = None
    full_output = "\n".join(chunk_output)
    try:
        chunk_data = json.loads(full_output)
    except json.JSONDecodeError:
        # Try finding JSON block in output
        for i in range(len(chunk_output)):
            try:
                chunk_data = json.loads("\n".join(chunk_output[i:]))
                break
            except json.JSONDecodeError:
                continue

    if chunk_data is None:
        chunk_data = {"chunking": False}

    if chunk_data.get("chunking"):
        total_chunks = chunk_data['totalChunks']
        print(f"📦 Audio chunked into {total_chunks} parts (5-min each)")

        # Transcribe all chunks in-process (model loaded ONCE, held in memory)
        model = get_whisper_model("small")
        result = transcribe_chunks_inprocess(basename, model)
        if result.get("error"):
            raise Exception(f"Chunk transcription failed: {result}")

        # Assemble chunks into single transcript
        assemble_cmd = ["python3", str(SKILL_DIR / "scripts" / "assemble_chunks.py"), basename]
        run_with_progress(assemble_cmd, 120, "Assembling chunks")
    else:
        print("📝 Short audio, transcribing directly...")
        # Transcribe in-process (no subprocess — model stays in memory)
        model = get_whisper_model("small")
        transcript_path = transcribe_audio_inprocess(input_file, str(SKILL_DIR / "transcripts"), model)
        if not transcript_path:
            raise Exception("Direct transcription failed")

    transcript_file = SKILL_DIR / "transcripts" / f"{basename}.txt"
    if not transcript_file.exists():
        raise Exception(f"Transcript file not found: {transcript_file}")
    print(f"✅ Transcribed: {transcript_file.name}")

    # Step 3: Prepare for translation (remove timestamps)
    print("\n📝 Step 3: Preparing for translation...")
    ready_file = SKILL_DIR / "translations" / f"{basename}_ready.txt"
    prepare_cmd = [
        "python3", str(SKILL_DIR / "scripts" / "prepare_transcript.py"),
        str(transcript_file), str(ready_file)
    ]
    run_with_progress(prepare_cmd, TIMEOUT_PREPARE, "Preparing transcript")

    if not ready_file.exists():
        raise Exception(f"Ready file not found: {ready_file}")

    # Step 4: Translate to Russian (batch translation)
    print("\n🌐 Step 4: Translating to Russian...")
    tts_file = translate_batch(ready_file, basename)
    print(f"✅ Translation: {tts_file.name}")

    # Step 5: Generate TTS
    print("\n🔊 Step 5: Generating Russian TTS...")
    output_audio = SKILL_DIR / "audio" / f"{basename}.ru.mp3"
    tts_cmd = [
        "python3", str(SKILL_DIR / "scripts" / "generate_tts.py"),
        str(tts_file), str(output_audio), voice,
        video['title'],           # title metadata
        video.get('channel', ''),  # artist metadata
    ]
    run_with_progress(tts_cmd, TIMEOUT_TTS, "Generating TTS")

    if not output_audio.exists():
        raise Exception(f"TTS audio file not found: {output_audio}")

    # Embed cover art from YouTube thumbnail + full metadata
    try:
        import urllib.request
        thumb_path = SKILL_DIR / "input" / f"{basename}_thumb.jpg"
        # Try thumbnail qualities in order of preference
        thumb_downloaded = False
        for quality in ['maxresdefault', 'hqdefault', 'mqdefault']:
            thumb_url = f"https://img.youtube.com/vi/{video_id}/{quality}.jpg"
            try:
                urllib.request.urlretrieve(thumb_url, str(thumb_path))
                if thumb_path.exists() and thumb_path.stat().st_size > 1000:
                    thumb_downloaded = True
                    print(f"🖼️ Thumbnail: {quality}.jpg ({thumb_path.stat().st_size} bytes)")
                    break
            except Exception:
                continue

        if thumb_downloaded:
            # Embed cover art + full metadata using ffmpeg
            meta_cmd = [
                "ffmpeg", "-y", "-i", str(output_audio),
                "-i", str(thumb_path),
                "-map", "0:a", "-map", "1:v",
                "-c:a", "copy", "-c:v", "mjpeg",
                "-metadata", f"title={video['title']}",
                "-metadata", f"artist={video.get('channel', '')}",
                "-metadata", "album=Podcast Translation",
                "-metadata", "genre=Podcast",
                "-metadata", f"date={datetime.now().strftime('%Y-%m-%d')}",
                "-disposition:v:0", "attached_pic",
                str(output_audio).replace('.ru.mp3', '.meta.ru.mp3')
            ]
            result = subprocess.run(meta_cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                meta_file = Path(str(output_audio).replace('.ru.mp3', '.meta.ru.mp3'))
                if meta_file.exists():
                    os.replace(str(meta_file), str(output_audio))
                    print("✅ Cover art + metadata embedded")
            else:
                print(f"⚠️ Cover art embedding failed (non-fatal): {result.stderr[:200]}")
            thumb_path.unlink(missing_ok=True)
        else:
            print("⚠️ No thumbnail available (non-fatal)")
    except Exception as e:
        print(f"⚠️ Cover art skipped (non-fatal): {e}")

    # Get audio duration and size
    dur_result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(output_audio)],
        capture_output=True, text=True, timeout=10
    )
    duration = float(dur_result.stdout.strip()) if dur_result.returncode == 0 else 0
    size_mb = output_audio.stat().st_size / (1024 * 1024)

    # Clean up input file to save disk space
    try:
        input_file.unlink()
        print(f"🧹 Cleaned up: {input_file.name}")
    except OSError:
        pass

    print(f"\n✅ Russian audio: {output_audio.name} ({duration:.0f}s, {size_mb:.1f} MB)")

    return {
        "success": True,
        "video": video,
        "audio_path": str(output_audio),
        "tts_text_path": str(tts_file),
        "transcript_path": str(transcript_file),
        "duration": duration,
        "size_mb": size_mb,
        "word_count": len(tts_file.read_text(encoding='utf-8').split())
    }


def translate_batch(ready_file, basename):
    """Translate using GoogleTranslator with batch processing.

    Groups lines into batches of ~50 lines to reduce API calls.
    Joins with newlines, translates as a block, then splits back.

    Args:
        ready_file: Path to _ready.txt file (no timestamps)
        basename: Base name for output file

    Returns:
        Path to _ru_tts.txt file
    """
    from deep_translator import GoogleTranslator

    content = ready_file.read_text(encoding='utf-8')
    lines = [l.strip() for l in content.split("\n") if l.strip()]

    print(f"STATUS: Translating {len(lines)} lines (batch mode)...")

    translator = GoogleTranslator(source='en', target='ru')

    BATCH_SIZE = 50  # Lines per API call
    translated_lines = []
    total_batches = (len(lines) + BATCH_SIZE - 1) // BATCH_SIZE

    for i in range(0, len(lines), BATCH_SIZE):
        batch_num = i // BATCH_SIZE + 1
        batch = lines[i:i + BATCH_SIZE]
        batch_text = "\n".join(batch)

        try:
            # Translate entire batch as one block
            translated = translator.translate(batch_text)

            # Split back into lines (Google Translate preserves newlines)
            translated_parts = translated.split("\n") if "\n" in translated else [translated]

            # Ensure we get the same number of lines back
            if len(translated_parts) == len(batch):
                translated_lines.extend(translated_parts)
            else:
                # Fallback: translate line by line for this batch
                print(f"  ⚠️ Batch {batch_num}/{total_batches}: line count mismatch, falling back")
                for line in batch:
                    try:
                        translated_lines.append(translator.translate(line))
                    except Exception:
                        translated_lines.append(line)
        except Exception as e:
            print(f"  ⚠️ Batch {batch_num}/{total_batches} failed: {e}, falling back to line-by-line")
            for line in batch:
                try:
                    translated_lines.append(translator.translate(line))
                except Exception:
                    translated_lines.append(line)

        if batch_num % 5 == 0 or batch_num == total_batches:
            print(f"HEARTBEAT: Translated {batch_num}/{total_batches} batches ({i + len(batch)}/{len(lines)} lines)")

    # Write TTS-ready text
    tts_file = SKILL_DIR / "translations" / f"{basename}_ru_tts.txt"
    tts_file.write_text("\n".join(translated_lines), encoding='utf-8')

    return tts_file


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Process podcast queue for Hermes")
    parser.add_argument("--max-videos", type=int, default=0,
                       help="Max videos to process (0 = unlimited, process entire queue)")
    parser.add_argument("--voice", default="ru-RU-DmitryNeural",
                       help="TTS voice (ru-RU-DmitryNeural, ru-RU-SvetlanaNeural, ru-RU-DariyaNeural)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    # Acquire PID-lock
    if not acquire_lock():
        if args.json:
            print(json.dumps({"success": False, "error": "already_running"}))
        sys.exit(0)

    try:
        qm = QueueManager(SKILL_DIR / "youtube-queue.json")

        # Reset stale videos first
        qm.reset_stale()

        # Show queue status
        status = qm.get_status()
        print(f"📊 Queue: {status['pending']} pending, {status['processing']} processing, "
              f"{status['completed']} completed, {status['failed']} failed")

        if status['pending'] == 0:
            print("✅ Queue is empty")
            if args.json:
                print(json.dumps({"success": True, "message": "Queue empty", "processed": 0}))
            return

        results = []
        processed_count = 0
        max_videos = args.max_videos  # 0 = unlimited

        # Process ALL pending videos, one at a time
        # Each iteration: get_next_video → run pipeline → mark completed/failed → repeat
        # Loop ends when: queue empty, max_videos reached, or get_next_video returns None
        while True:
            if max_videos > 0 and processed_count >= max_videos:
                print(f"📊 Reached max-videos limit ({max_videos})")
                break

            video = qm.get_next_video()
            if not video:
                break

            processed_count += 1

            try:
                result = run_pipeline_for_video(video, args.voice)

                if result["success"]:
                    qm.mark_completed(video["videoId"], {
                        "audio": result["audio_path"],
                        "ttsText": result["tts_text_path"],
                        "transcript": result["transcript_path"]
                    })
                else:
                    qm.mark_failed(video["videoId"], result.get("error", "Unknown error"))

            except Exception as e:
                print(f"\n❌ Pipeline error: {e}")
                qm.mark_failed(video["videoId"], str(e))
                result = {"success": False, "video": video, "error": str(e)}

            results.append(result)

        # Output summary
        if args.json:
            summary = {
                "processed": len(results),
                "success": sum(1 for r in results if r.get("success")),
                "failed": sum(1 for r in results if not r.get("success")),
                "results": [{"videoId": r["video"]["videoId"],
                            "title": r["video"]["title"],
                            "success": r.get("success", False),
                            "audio_path": r.get("audio_path", ""),
                            "error": r.get("error", "")}
                           for r in results]
            }
            print(json.dumps(summary, indent=2, ensure_ascii=False))

        # Print audio file paths for Hermes to deliver
        for r in results:
            if r.get("success"):
                print(f"\nHERMES_AUDIO_FILE:{r['audio_path']}")
                print(f"HERMES_VIDEO_TITLE:{r['video']['title']}")
                print(f"HERMES_DURATION:{r['duration']:.0f}")
                print(f"HERMES_SIZE_MB:{r['size_mb']:.1f}")
                print(f"HERMES_WORDS:{r['word_count']}")

    finally:
        release_lock()


if __name__ == "__main__":
    main()