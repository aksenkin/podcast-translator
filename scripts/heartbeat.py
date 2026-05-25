#!/usr/bin/env python3
"""
Heartbeat logger for transcription process.

Creates and updates log files to track transcription progress,
which can be monitored to detect hung processes.

Usage:
    from heartbeat import TranscriptionHeartbeat
    
    hb = TranscriptionHeartbeat(video_id)
    hb.start("Downloading audio...")
    
    # During transcription
    hb.update_progress(50, "Transcribing chunk 5 of 10")
    
    # When done
    hb.finish()
    
    # If failed
    hb.fail("Transcription timeout")

Log files are created in: transcription_logs/{video_id}.log
After successful completion, log is automatically deleted.
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path


LOGS_DIR = Path(__file__).parent.parent / "transcription_logs"


class TranscriptionHeartbeat:
    """Heartbeat logger for transcription processes."""
    
    def __init__(self, video_id):
        """Initialize heartbeat for a video.
        
        Args:
            video_id: YouTube video ID
        """
        self.video_id = video_id
        self.log_file = LOGS_DIR / f"{video_id}.log"
        self.start_time = time.time()
        
        # Ensure logs directory exists
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
    
    def _write(self, status, message, progress=None, phase=None):
        """Write heartbeat entry to log file."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "videoId": self.video_id,
            "status": status,
            "message": message,
            "elapsed_seconds": round(time.time() - self.start_time, 1)
        }
        
        if progress is not None:
            entry["progress_percent"] = progress
        
        if phase:
            entry["phase"] = phase
        
        # Write as JSON line (append mode)
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')
    
    def start(self, message="Starting transcription"):
        """Mark start of transcription process."""
        self._write("started", message, phase="init")
    
    def update_progress(self, percent, message, phase="transcribing"):
        """Update progress during transcription.
        
        Args:
            percent: Progress percentage (0-100)
            message: Status message
            phase: Current phase (init, downloading, chunking, transcribing, assembling, translating, tts, complete)
        """
        self._write("progress", message, progress=percent, phase=phase)
    
    def phase(self, phase_name, message=None):
        """Mark transition to a new phase.
        
        Args:
            phase_name: Phase name (downloading, chunking, transcribing, assembling, translating, tts)
            message: Optional message
        """
        if message is None:
            message = f"Entering phase: {phase_name}"
        self._write("phase", message, phase=phase_name)
    
    def finish(self):
        """Mark successful completion.
        
        Writes completion status to log. Log file is kept until
        next health check confirms completion.
        """
        self._write("completed", "All phases completed successfully", progress=100, phase="complete")

    def cleanup_completed(self):
        """Remove log file for completed transcriptions.
        
        Called by health monitor after verifying completion.
        """
        try:
            if self.log_file.exists():
                # Verify it's actually completed
                with open(self.log_file, 'r') as f:
                    lines = f.readlines()
                if lines:
                    last_entry = json.loads(lines[-1])
                    if last_entry.get("status") == "completed":
                        self.log_file.unlink()
                        return True
        except (OSError, json.JSONDecodeError):
            pass
        return False
    
    def fail(self, error_message):
        """Mark failure.
        
        Args:
            error_message: Error description
        """
        self._write("failed", error_message, phase="failed")
    
    def heartbeat(self, message="Process alive"):
        """Send periodic heartbeat to show process is not hung.
        
        Call this periodically (e.g., every 30-60 seconds) during long operations.
        """
        self._write("heartbeat", message)
    
    @staticmethod
    def get_active_logs():
        """Get list of active (incomplete) transcription logs.
        
        Returns:
            List of dicts with video_id, last_update, status
        """
        if not LOGS_DIR.exists():
            return []
        
        active = []
        for log_file in LOGS_DIR.glob("*.log"):
            try:
                # Read last line
                with open(log_file, 'r') as f:
                    lines = f.readlines()
                
                if not lines:
                    continue
                
                last_entry = json.loads(lines[-1])
                
                active.append({
                    "videoId": last_entry.get("videoId", log_file.stem),
                    "lastUpdate": last_entry.get("timestamp", ""),
                    "status": last_entry.get("status", "unknown"),
                    "phase": last_entry.get("phase", "unknown"),
                    "progress": last_entry.get("progress_percent"),
                    "message": last_entry.get("message", ""),
                    "elapsedSeconds": last_entry.get("elapsed_seconds", 0)
                })
            except (json.JSONDecodeError, OSError):
                continue
        
        return active
    
    @staticmethod
    def check_stale(max_seconds=300):
        """Check for stale transcription processes.
        
        Args:
            max_seconds: Maximum allowed time since last heartbeat (default 5 min)
        
        Returns:
            List of stale video IDs
        """
        active = TranscriptionHeartbeat.get_active_logs()
        stale = []
        completed_to_cleanup = []
        
        for log in active:
            try:
                last_update = datetime.fromisoformat(log["lastUpdate"])
                elapsed = (datetime.now() - last_update).total_seconds()
                
                # Check if completed
                if log.get("status") == "completed":
                    # Mark for cleanup
                    completed_to_cleanup.append(log["videoId"])
                    continue
                
                # Check if stale
                if elapsed > max_seconds:
                    stale.append({
                        "videoId": log["videoId"],
                        "lastUpdate": log["lastUpdate"],
                        "phase": log["phase"],
                        "message": log["message"],
                        "staleSeconds": round(elapsed)
                    })
            except (ValueError, TypeError):
                continue
        
        # Cleanup completed logs
        for video_id in completed_to_cleanup:
            hb = TranscriptionHeartbeat(video_id)
            hb.cleanup_completed()
        
        return stale


def main():
    """CLI for checking transcription status."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Transcription heartbeat monitor")
    parser.add_argument("command", choices=["status", "stale"], help="Command")
    parser.add_argument("--max-seconds", type=int, default=300, help="Stale threshold")
    
    args = parser.parse_args()
    
    if args.command == "status":
        active = TranscriptionHeartbeat.get_active_logs()
        if active:
            print(f"Active transcriptions: {len(active)}")
            for log in active:
                print(f"\n  Video: {log['videoId']}")
                print(f"  Status: {log['status']} ({log['phase']})")
                print(f"  Progress: {log['progress']}%")
                print(f"  Last update: {log['lastUpdate']}")
                print(f"  Elapsed: {log['elapsedSeconds']}s")
                print(f"  Message: {log['message'][:80]}")
        else:
            print("No active transcriptions")
    
    elif args.command == "stale":
        stale = TranscriptionHeartbeat.check_stale(args.max_seconds)
        if stale:
            print(f"Stale transcriptions ({len(stale)}):")
            for s in stale:
                print(f"\n  Video: {s['videoId']}")
                print(f"  Phase: {s['phase']}")
                print(f"  Stale for: {s['staleSeconds']}s")
                print(f"  Last message: {s['message'][:80]}")
        else:
            print("No stale transcriptions")


if __name__ == "__main__":
    main()
