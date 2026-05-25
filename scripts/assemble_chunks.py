#!/usr/bin/env python3
"""
Assemble chunk transcripts into a single transcript file.

Reads {videoId}_chunks.json, concatenates all chunk transcripts
with [chunk N/M] headers, writes to transcripts/{videoId}.txt,
then cleans up chunk files.

Usage:
    python3 assemble_chunks.py {videoId}

Output (JSON to stdout):
    {"assembled": true, "transcript": "transcripts/...txt", "segments": 980, "chunksCleaned": 7}
    {"assembled": false, "reason": "chunk 3 failed: ..."}
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from log_helper import log_event
from heartbeat import TranscriptionHeartbeat

CHUNKS_DIR = Path(__file__).parent.parent / "chunks"
TRANSCRIPTS_DIR = Path(__file__).parent.parent / "transcripts"


def load_chunks_meta(video_id):
    """Load chunks metadata JSON."""
    chunks_json = CHUNKS_DIR / f"{video_id}_chunks.json"
    if not chunks_json.exists():
        return None
    return json.loads(chunks_json.read_text())


def assemble_chunks(video_id):
    """Assemble chunk transcripts into a single file.

    Args:
        video_id: YouTube video ID

    Returns:
        Dict with result
    """
    hb = TranscriptionHeartbeat(video_id)
    
    data = load_chunks_meta(video_id)
    if data is None:
        hb.fail("no_chunks_json")
        return {"assembled": False, "reason": "no_chunks_json"}

    total = data["totalChunks"]
    hb.start(f"Assembling {total} chunks for {video_id}")

    # Check for failed chunks
    failed_chunks = [c for c in data["chunks"] if c["status"] == "failed"]
    if failed_chunks:
        reason = f"chunk {failed_chunks[0]['index']}/{total} failed"
        log_event(video_id, "ASSEMBLE_FAIL", reason=reason)
        hb.fail(reason)
        # Clean up all chunk files
        cleanup_chunks(video_id, data)
        return {"assembled": False, "reason": reason}

    # Check if all chunks are done
    done_chunks = [c for c in data["chunks"] if c["status"] == "done"]
    if len(done_chunks) < total:
        reason = f"not all chunks ready ({len(done_chunks)}/{total})"
        log_event(video_id, "ASSEMBLE_SKIP", reason=reason)
        hb.fail(reason)
        return {"assembled": False, "reason": reason}

    log_event(video_id, "ASSEMBLE_START", total=total)
    hb.phase("assembling", f"Reading {total} chunk transcripts")

    TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    transcript_file = TRANSCRIPTS_DIR / f"{video_id}.txt"

    assembled_count = 0
    with open(transcript_file, 'w', encoding='utf-8') as f:
        for i, chunk in enumerate(data["chunks"], 1):
            chunk_file = CHUNKS_DIR / f"{video_id}_chunk{chunk['index']:03d}.txt"
            if chunk_file.exists():
                # Add chunk marker (for TTS cleanup later)
                f.write(f"\n[chunk {i}/{total}]\n\n")
                content = chunk_file.read_text(encoding='utf-8')
                f.write(content)
                f.write("\n")
                assembled_count += 1
                
                progress = int((i / total) * 100)
                hb.update_progress(progress, f"Assembled chunk {i}/{total}", phase="assembling")
            else:
                log_event(video_id, "ASSEMBLE_MISSING", chunk=f"{i}/{total}", file=chunk_file.name)

    log_event(video_id, "ASSEMBLE_OK", segments=assembled_count, file=str(transcript_file))
    hb.finish()

    # Clean up chunk files
    chunks_cleaned = cleanup_chunks(video_id, data)

    return {"assembled": True, "transcript": str(transcript_file),
            "segments": assembled_count, "chunksCleaned": chunks_cleaned}

    # Check all chunks are done
    pending_chunks = [c for c in data["chunks"] if c["status"] != "done"]
    if pending_chunks:
        reason = f"chunk {pending_chunks[0]['index']}/{total} not done (status: {pending_chunks[0]['status']})"
        return {"assembled": False, "reason": reason}

    log_event(video_id, "ASSEMBLE_START", chunks=total)

    # Concatenate transcripts
    TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    output_file = TRANSCRIPTS_DIR / f"{video_id}.txt"
    total_segments = 0

    with open(output_file, 'w', encoding='utf-8') as out:
        for chunk in data["chunks"]:
            chunk_stem = Path(chunk["file"]).stem  # e.g. "jblguhXunZs_chunk001"
            chunk_txt = CHUNKS_DIR / f"{chunk_stem}.txt"

            if chunk_txt.exists():
                content = chunk_txt.read_text(encoding='utf-8')
                segment_count = len([l for l in content.split('\n') if l.strip() and l.startswith('[')])
                total_segments += segment_count
                out.write(content)
                if not content.endswith('\n'):
                    out.write('\n')
            else:
                log_event(video_id, "ASSEMBLE_WARN", chunk=chunk['index'], reason="transcript missing")

    log_event(video_id, "ASSEMBLE_OK",
              output=str(output_file),
              total_segments=total_segments)

    # Clean up chunk files
    files_cleaned = cleanup_chunks(video_id, data)

    log_event(video_id, "CHUNKS_CLEANUP", deleted=files_cleaned)

    return {
        "assembled": True,
        "transcript": str(output_file),
        "segments": total_segments,
        "chunksCleaned": files_cleaned
    }


def cleanup_chunks(video_id, data):
    """Delete chunk audio files, chunk transcripts, and _chunks.json.

    Args:
        video_id: YouTube video ID
        data: Chunks metadata dict

    Returns:
        Number of files deleted
    """
    deleted = 0

    for chunk in data["chunks"]:
        # Delete chunk audio
        chunk_audio = CHUNKS_DIR / chunk["file"]
        if chunk_audio.exists():
            chunk_audio.unlink()
            deleted += 1

        # Delete chunk transcript
        chunk_stem = Path(chunk["file"]).stem
        chunk_txt = CHUNKS_DIR / f"{chunk_stem}.txt"
        if chunk_txt.exists():
            chunk_txt.unlink()
            deleted += 1

    # Delete chunks metadata
    chunks_json = CHUNKS_DIR / f"{video_id}_chunks.json"
    if chunks_json.exists():
        chunks_json.unlink()
        deleted += 1

    return deleted


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 assemble_chunks.py <videoId>")
        print("")
        print("Assembles chunk transcripts into a single file.")
        print("Output: JSON with assembly result.")
        sys.exit(1)

    video_id = sys.argv[1]
    result = assemble_chunks(video_id)
    print(json.dumps(result, indent=2, ensure_ascii=False))

    if not result.get("assembled"):
        sys.exit(1)