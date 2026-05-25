#!/usr/bin/env python3
"""
Transcribe audio with heartbeat logging.

Wraps the transcription process and adds heartbeat logging
to detect hung processes.

Usage:
    python3 transcribe_with_heartbeat.py <video_id> [--chunk-index N]

Logs are written to: transcription_logs/{video_id}.log
"""

import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from heartbeat import TranscriptionHeartbeat


def transcribe_audio(video_id, chunk_index=None):
    """Run transcription with heartbeat logging.
    
    Args:
        video_id: YouTube video ID
        chunk_index: Optional chunk index (for chunked audio)
    
    Returns:
        Dict with result
    """
    hb = TranscriptionHeartbeat(video_id)
    
    try:
        # Start heartbeat
        hb.start(f"Starting transcription for {video_id}")
        
        # Determine what to transcribe
        if chunk_index is not None:
            # Chunked audio
            audio_file = f"chunks/{video_id}_chunk{chunk_index:03d}.mp3"
            hb.phase("transcribing", f"Transcribing chunk {chunk_index}")
        else:
            # Full audio
            audio_file = f"input/{video_id}.mp3"
            hb.phase("transcribing", "Transcribing full audio")
        
        # Run transcription
        # This is a placeholder - replace with actual transcription command
        # For now, simulate transcription progress
        
        # In real implementation, this would call:
        # result = subprocess.run([
        #     "python3", "transcribe_cached.py",
        #     audio_file, "transcripts/", "small"
        # ], capture_output=True, text=True, timeout=3600)
        
        # Simulate progress updates
        for i in range(10):
            time.sleep(0.1)  # Simulate work
            progress = (i + 1) * 10
            hb.update_progress(progress, f"Transcription progress: {progress}%", phase="transcribing")
            hb.heartbeat(f"Transcription alive, {progress}% complete")
        
        # Mark complete
        hb.finish()
        return {"success": True, "videoId": video_id}
        
    except subprocess.TimeoutExpired:
        error = "Transcription timeout"
        hb.fail(error)
        return {"success": False, "error": error}
    except Exception as e:
        error = str(e)
        hb.fail(error)
        return {"success": False, "error": error}


def transcribe_chunks(video_id):
    """Transcribe all chunks for a video with heartbeat.
    
    Args:
        video_id: YouTube video ID
    
    Returns:
        Dict with result
    """
    hb = TranscriptionHeartbeat(video_id)
    
    try:
        hb.start(f"Starting chunk transcription for {video_id}")
        
        # Load chunks metadata
        chunks_file = Path(f"chunks/{video_id}_chunks.json")
        if not chunks_file.exists():
            error = f"Chunks file not found: {chunks_file}"
            hb.fail(error)
            return {"success": False, "error": error}
        
        chunks_data = json.loads(chunks_file.read_text())
        total_chunks = chunks_data["totalChunks"]
        
        hb.phase("transcribing", f"Transcribing {total_chunks} chunks")
        
        # Transcribe each chunk
        for i, chunk in enumerate(chunks_data["chunks"], 1):
            if chunk["status"] == "done":
                continue
            
            progress = int((i - 1) / total_chunks * 100)
            hb.update_progress(progress, f"Transcribing chunk {i} of {total_chunks}", phase="transcribing")
            
            # Run transcription for this chunk
            chunk_result = transcribe_audio(video_id, chunk_index=i)
            
            if not chunk_result["success"]:
                error = f"Chunk {i} failed: {chunk_result.get('error', 'unknown')}"
                hb.fail(error)
                return {"success": False, "error": error}
            
            # Update chunk status
            chunk["status"] = "done"
            chunks_data["chunks"] = chunks_data["chunks"]
            chunks_file.write_text(json.dumps(chunks_data, indent=2, ensure_ascii=False))
            
            hb.heartbeat(f"Chunk {i}/{total_chunks} complete")
        
        # Assemble chunks
        hb.phase("assembling", "Assembling transcription chunks")
        
        # In real implementation, call assemble_chunks.py here
        # subprocess.run(["python3", "assemble_chunks.py", video_id], ...)
        
        hb.update_progress(100, "Transcription complete", phase="complete")
        hb.finish()
        return {"success": True, "videoId": video_id}
        
    except Exception as e:
        error = str(e)
        hb.fail(error)
        return {"success": False, "error": error}


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Transcribe audio with heartbeat")
    parser.add_argument("video_id", help="YouTube video ID")
    parser.add_argument("--chunk-index", type=int, help="Chunk index (optional)")
    parser.add_argument("--all-chunks", action="store_true", help="Transcribe all chunks")
    
    args = parser.parse_args()
    
    if args.all_chunks:
        result = transcribe_chunks(args.video_id)
    else:
        result = transcribe_audio(args.video_id, args.chunk_index)
    
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    if not result["success"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
