#!/usr/bin/env python3
"""
Check if queue-processor lock is valid (process still alive).
Usage: python3 check_lock.py
Returns: QUEUE_BUSY (with details) or QUEUE_FREE
"""

import os
import sys
import time

LOCK_FILE = "/tmp/queue-processor.lock"
LOCK_MAX_AGE_SECONDS = 3 * 3600  # 3 hours max lock lifetime

def check_lock():
    if not os.path.exists(LOCK_FILE):
        print("QUEUE_FREE")
        return
    
    # Check lock file age
    try:
        mtime = os.path.getmtime(LOCK_FILE)
        age = time.time() - mtime
        
        if age > LOCK_MAX_AGE_SECONDS:
            # Stale lock - remove it
            os.remove(LOCK_FILE)
            print(f"QUEUE_FREE (stale lock removed, age={age:.0f}s)")
            return
    except OSError:
        pass
    
    # Check if process with that PID exists
    try:
        with open(LOCK_FILE) as f:
            pid = f.read().strip()
        
        if pid:
            pid = int(pid)
            try:
                # Check if process exists and is queue-processor
                with open(f"/proc/{pid}/cmdline") as f:
                    cmdline = f.read()
                if "queue" in cmdline.lower() or "agentTurn" in cmdline:
                    print(f"QUEUE_BUSY (pid={pid}, age={age:.0f}s)")
                    return
            except (FileNotFoundError, ProcessLookupError):
                # Process dead - remove stale lock
                os.remove(LOCK_FILE)
                print(f"QUEUE_FREE (dead pid {pid} removed)")
                return
    except (ValueError, OSError):
        pass
    
    # Lock exists but we can't verify - treat as busy to be safe
    print(f"QUEUE_BUSY (lock exists, age={age:.0f}s)")

if __name__ == "__main__":
    check_lock()
