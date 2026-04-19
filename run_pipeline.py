#!/usr/bin/env python3
"""
Podcast Pipeline Launcher with PID-lock concurrency control.

Prevents concurrent runs of the queue-processor cron job.
Can be called manually or from other cron jobs (e.g., youtube-collector).

Usage:
    python3 run_pipeline.py              # Trigger queue-processor cron job
    python3 run_pipeline.py --status     # Check if pipeline is running
    python3 run_pipeline.py --force       # Force run even if lock exists
"""

import atexit
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

LOCK_FILE = "/tmp/podcast-queue.lock"
CRON_JOB_ID = "a79e58b0-f9bd-4911-86a7-44c01a1ae572"
TIMEOUT_SECONDS = 1800  # 30 minutes


def read_lock():
    """Read PID from lock file. Returns PID or None."""
    try:
        if os.path.exists(LOCK_FILE):
            content = Path(LOCK_FILE).read_text().strip()
            if content.isdigit():
                return int(content)
    except (OSError, ValueError):
        pass
    return None


def is_pid_alive(pid):
    """Check if a process with given PID is alive."""
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def acquire_lock(force=False):
    """Acquire the pipeline lock. Returns True if lock acquired."""
    existing_pid = read_lock()

    if existing_pid is not None:
        if not force and is_pid_alive(existing_pid):
            print(f"STATUS: Pipeline already running (PID {existing_pid})")
            return False
        else:
            # Stale lock or force — clean it up
            print(f"STATUS: Removing stale lock (PID {existing_pid})")
            release_lock()

    # Write our PID
    Path(LOCK_FILE).write_text(str(os.getpid()))
    return True


def release_lock():
    """Release the pipeline lock."""
    try:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
    except OSError:
        pass


def handle_timeout(signum, frame):
    """Handle timeout signal."""
    print("ERROR: Pipeline timed out after 30 minutes")
    release_lock()
    sys.exit(2)


def run_pipeline():
    """Trigger the queue-processor cron job."""
    print(f"STATUS: Starting pipeline at {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"STATUS: Cron job ID: {CRON_JOB_ID}")

    try:
        result = subprocess.run(
            ["openclaw", "cron", "run", CRON_JOB_ID],
            timeout=TIMEOUT_SECONDS,
            capture_output=False
        )

        if result.returncode == 0:
            print(f"SUCCESS: Pipeline completed")
        else:
            print(f"ERROR: Pipeline exited with code {result.returncode}")

        return result.returncode

    except subprocess.TimeoutExpired:
        print("ERROR: Pipeline timed out after 30 minutes")
        return 2
    except Exception as e:
        print(f"ERROR: Pipeline failed: {e}")
        return 1


def show_status():
    """Show current pipeline lock status."""
    pid = read_lock()
    if pid is not None and is_pid_alive(pid):
        print(f"Pipeline is RUNNING (PID {pid})")
        return 0
    elif pid is not None:
        print(f"Pipeline lock is STALE (PID {pid} is dead)")
        return 1
    else:
        print("Pipeline is NOT running")
        return 0


def main():
    # Register cleanup
    atexit.register(release_lock)

    # Handle SIGTERM
    signal.signal(signal.SIGTERM, lambda s, f: (release_lock(), sys.exit(130)))

    # Parse args
    force = "--force" in sys.argv
    if "--status" in sys.argv:
        sys.exit(show_status())

    # Acquire lock
    if not acquire_lock(force=force):
        sys.exit(0)

    # Run pipeline
    exit_code = run_pipeline()

    # Release lock (also done by atexit, but explicit is better)
    release_lock()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()