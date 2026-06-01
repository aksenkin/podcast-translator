#!/usr/bin/env python3
"""
Create queue-processor lock with PID inside.
Usage: python3 create_lock.py
"""

import os

LOCK_FILE = "/tmp/queue-processor.lock"

def create_lock():
    with open(LOCK_FILE, 'w') as f:
        f.write(str(os.getpid()))
    print(f"Lock created: {LOCK_FILE} (pid={os.getpid()})")

if __name__ == "__main__":
    create_lock()
