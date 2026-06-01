#!/usr/bin/env python3
"""
Transcribe all chunks for a video using a single model load.
Writes progress to a status file and stdout.
"""
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

CHUNKS_DIR = Path(__file__).parent.parent / "chunks"
CACHE_DIR = Path.home() / ".cache" / "huggingface" / "hub"


def load_chunks_meta(video_id):
    chunks_json = CHUNKS_DIR / f"{video_id}_chunks.json"
    if not chunks_json.exists():
        return None
    return json.loads(chunks_json.read_text())


def save_chunks_meta(video_id, data):
    chunks_json = CHUNKS_DIR / f"{video_id}_chunks.json"
    chunks_json.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def transcribe_all(video_id):
    data = load_chunks_meta(video_id)
    if data is None:
        print(json.dumps({"error": "no_chunks_json"}))
        return

    pending = [c for c in data["chunks"] if c["status"] == "pending"]
    if not pending:
        all_done = all(c["status"] == "done" for c in data["chunks"])
        if all_done:
            data["status"] = "assembling"
            save_chunks_meta(video_id, data)
            print(json.dumps({"allDone": True, "videoId": video_id, "totalChunks": data["totalChunks"]}))
        else:
            print(json.dumps({"error": "all_chunks_processed"}))
        return

    from faster_whisper import WhisperModel

    print(f"Loading model for {len(pending)} chunks...", flush=True)
    model = WhisperModel(
        "tiny", device="cpu", compute_type="int8",
        download_root=str(CACHE_DIR), cpu_threads=4, num_workers=2
    )
    print("Model loaded. Starting transcription...", flush=True)

    total = data["totalChunks"]
    done_count = 0

    for chunk in pending:
        chunk_idx = chunk["index"]
        chunk_file = CHUNKS_DIR / chunk["file"]

        print(f"Processing chunk {chunk_idx}/{total}...", flush=True)
        chunk["status"] = "transcribing"
        save_chunks_meta(video_id, data)

        try:
            segments, info = model.transcribe(
                str(chunk_file),
                beam_size=1,
                vad_filter=False,
                word_timestamps=False,
                language="en"
            )

            chunk_basename = chunk_file.stem
            transcript_file = CHUNKS_DIR / f"{chunk_basename}.txt"
            segment_count = 0

            with open(transcript_file, 'w', encoding='utf-8') as f:
                for segment in segments:
                    segment_count += 1
                    minutes_start = int(segment.start // 60)
                    seconds_start = int(segment.start % 60)
                    minutes_end = int(segment.end // 60)
                    seconds_end = int(segment.end % 60)
                    f.write(f"[{minutes_start:02d}:{seconds_start:02d} - {minutes_end:02d}:{seconds_end:02d}] {segment.text}\n")

            chunk["status"] = "done"
            done_count += 1
            print(f"Chunk {chunk_idx}/{total} done ({segment_count} segments)", flush=True)

        except Exception as e:
            chunk["status"] = "failed"
            data["status"] = "failed"
            save_chunks_meta(video_id, data)
            print(f"Chunk {chunk_idx} failed: {e}", flush=True)
            print(json.dumps({"error": "chunk_failed", "failedChunk": chunk_idx, "message": str(e)}))
            return

    save_chunks_meta(video_id, data)

    all_done = all(c["status"] == "done" for c in data["chunks"])
    if all_done:
        data["status"] = "assembling"
        save_chunks_meta(video_id, data)
        print(json.dumps({"allDone": True, "videoId": video_id, "totalChunks": total, "transcribed": done_count}))
    else:
        print(json.dumps({"videoId": video_id, "transcribed": done_count, "totalChunks": total}))


if __name__ == "__main__":
    os.nice(10)
    if len(sys.argv) < 2:
        print("Usage: python3 transcribe_all_chunks.py <videoId>")
        sys.exit(1)
    transcribe_all(sys.argv[1])
