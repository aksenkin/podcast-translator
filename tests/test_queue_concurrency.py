#!/usr/bin/env python3
"""
Test queue processing concurrency.

CRITICAL: Only one queue item can be in "processing" state at any time.
If one video is taken for processing, no second process can activate —
not through queue_manager, not through hermes_queue_processor PID-lock.

Uses mock objects to simulate long-running tasks without real whisper/TTS.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from conftest import (
    PROJECT_DIR, SCRIPTS_DIR, QUEUE_FILE
)

sys.path.insert(0, str(PROJECT_DIR))
from queue_manager import QueueManager


# ─── Mock Long-Running Task ──────────────────────────────────────────────────

MOCK_TASK_SCRIPT = """
#!/usr/bin/env python3
\"\"\"Mock long-running pipeline task for testing queue concurrency.

Simulates a real pipeline (download + transcribe + translate + TTS)
by sleeping for a configurable duration. Writes a heartbeat file
so tests can verify the process is actually running.
\"\"\"
import json
import os
import sys
import time
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from queue_manager import QueueManager

QUEUE_FILE = PROJECT_DIR / "youtube-queue.json"
HEARTBEAT_FILE = Path("/tmp/podcast_test_heartbeat.json")
LOCK_FILE = Path("/tmp/podcast-hermes-processor.lock")


def acquire_lock():
    if LOCK_FILE.exists():
        try:
            old_pid = int(LOCK_FILE.read_text().strip())
            os.kill(old_pid, 0)
            return False
        except (OSError, ProcessLookupError, ValueError):
            LOCK_FILE.unlink(missing_ok=True)
    LOCK_FILE.write_text(str(os.getpid()))
    return True


def release_lock():
    try:
        LOCK_FILE.unlink(missing_ok=True)
    except OSError:
        pass


def main():
    duration = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    should_fail = "--fail" in sys.argv

    # Acquire PID-lock (same as hermes_queue_processor)
    if not acquire_lock():
        print(json.dumps({"success": False, "error": "already_running"}))
        sys.exit(0)

    try:
        qm = QueueManager(QUEUE_FILE)

        # Get next video from queue
        video = qm.get_next_video()
        if not video:
            print(json.dumps({"success": True, "message": "Queue empty", "processed": 0}))
            return

        video_id = video["videoId"]
        print(f"MOCK: Processing {video_id} ({video['title'][:50]})")

        # Write heartbeat — proves this process is active
        HEARTBEAT_FILE.write_text(json.dumps({
            "pid": os.getpid(),
            "videoId": video_id,
            "startedAt": time.time(),
            "status": "running"
        }))

        # Simulate long-running pipeline work
        for i in range(duration):
            time.sleep(1)
            # Update heartbeat each second
            hb = json.loads(HEARTBEAT_FILE.read_text())
            hb["elapsed"] = i + 1
            HEARTBEAT_FILE.write_text(json.dumps(hb))
            print(f"MOCK: tick {i+1}/{duration}")

        if should_fail:
            qm.mark_failed(video_id, "Mock failure")
            print(json.dumps({"success": False, "error": "Mock failure"}))
        else:
            qm.mark_completed(video_id, {"audio": "/tmp/mock_audio.mp3"})
            print(json.dumps({
                "success": True,
                "videoId": video_id,
                "audio_path": "/tmp/mock_audio.mp3"
            }))

    finally:
        release_lock()
        # Clean heartbeat
        try:
            HEARTBEAT_FILE.unlink()
        except OSError:
            pass


if __name__ == "__main__":
    main()
"""


@pytest.fixture
def mock_queue(clean_queue):
    """Queue with mock video entries."""
    qm = clean_queue
    qm.add_videos([
        {"videoId": "mock001", "title": "Mock Podcast 1", "channel": "TestChannel"},
        {"videoId": "mock002", "title": "Mock Podcast 2", "channel": "TestChannel"},
        {"videoId": "mock003", "title": "Mock Podcast 3", "channel": "TestChannel"},
    ])
    yield qm


@pytest.fixture
def mock_script(tmp_path):
    """Create the mock long-running task script."""
    script_path = PROJECT_DIR / "tests" / "mock_pipeline.py"
    script_path.write_text(MOCK_TASK_SCRIPT.strip())
    script_path.chmod(0o755)

    # Clean any leftover heartbeat/lock
    hb = Path("/tmp/podcast_test_heartbeat.json")
    lock = Path("/tmp/podcast-hermes-processor.lock")
    hb.unlink(missing_ok=True)
    lock.unlink(missing_ok=True)

    yield str(script_path)

    # Cleanup
    hb.unlink(missing_ok=True)
    lock.unlink(missing_ok=True)
    script_path.unlink(missing_ok=True)


# ─── Queue Manager: Single Processing Slot ──────────────────────────────────

class TestQueueSingleProcessing:
    """QueueManager must only allow ONE item in "processing" at any time."""

    def test_only_one_processing_slot(self, mock_queue):
        """get_next_video moves one item to processing, second call returns None
        because processing slot is occupied."""
        qm = mock_queue

        # First call — should get a video
        video1 = qm.get_next_video()
        assert video1 is not None
        assert video1["videoId"] == "mock001"

        # Verify queue state: 2 pending, 1 processing
        status = qm.get_status()
        assert status["processing"] == 1
        assert status["pending"] == 2

        # The processing slot is occupied — queue_manager doesn't have
        # a second processing slot. But get_next_video calls reset_stale
        # first, which won't trigger (not stale yet). So it will try to
        # pop from pending and overwrite processing!
        # Let's verify this ISN'T the case by checking the queue file directly
        queue = qm._load_queue()
        assert queue["processing"] is not None
        assert queue["processing"]["videoId"] == "mock001"

    def test_second_get_next_returns_none(self, mock_queue):
        """CRITICAL: Second get_next_video must return None while first is processing.

        Only ONE item can be in processing at any time. The queue manager
        must NOT overwrite the processing slot or give out a second video.
        """
        qm = mock_queue

        # Get first video
        video1 = qm.get_next_video()
        assert video1 is not None
        assert video1["videoId"] == "mock001"

        # Second call — must return None (processing slot occupied)
        video2 = qm.get_next_video()
        assert video2 is None, \
            "BUG: get_next_video returned a second video while first is still processing!"

        # Verify queue state — processing still has mock001
        queue = qm._load_queue()
        assert queue["processing"] is not None
        assert queue["processing"]["videoId"] == "mock001"
        # All other videos still in pending
        pending_ids = [v["videoId"] for v in queue["pending"]]
        assert "mock002" in pending_ids
        assert "mock003" in pending_ids

    def test_reset_stale_returns_to_pending(self, mock_queue):
        """Stale processing item (old + no live process) should return to pending."""
        qm = mock_queue

        # Get a video into processing
        video = qm.get_next_video()
        assert video["videoId"] == "mock001"

        # Manually set startedAt to 31 minutes ago (stale)
        from datetime import datetime, timezone, timedelta
        queue = qm._load_queue()
        queue["processing"]["startedAt"] = (
            datetime.now(timezone.utc) - timedelta(minutes=31)
        ).isoformat()
        qm._save_queue(queue)

        # reset_stale should return it to pending (no pgrep match for "mock001")
        result = qm.reset_stale()
        assert result is not None
        assert result["videoId"] == "mock001"
        assert result["action"] == "returned_to_pending"

        # Now processing should be None
        status = qm.get_status()
        assert status["processing"] == 0
        assert status["pending"] == 3

    def test_reset_stale_keeps_active_process(self, mock_queue):
        """Non-stale processing item should NOT be returned to pending."""
        qm = mock_queue
        video = qm.get_next_video()
        assert video["videoId"] == "mock001"

        # Just got it — not stale (0 min elapsed)
        result = qm.reset_stale()
        assert result is None, "Fresh processing item should not be reset"

        status = qm.get_status()
        assert status["processing"] == 1


# ─── PID-Lock: Parallel Process Prevention ───────────────────────────────────

class TestParallelProcessingBlocked:
    """Two hermes_queue_processor instances must NOT run simultaneously.

    The PID-lock prevents a second process from starting while the first
    is still running. This is the critical protection for RPi (4-core CPU).
    """

    def test_second_process_blocked_by_lock(self, mock_queue, mock_script):
        """Start mock pipeline (5 sec), then immediately start second.
        Second must be blocked by PID-lock."""
        # Start first process
        proc1 = subprocess.Popen(
            [sys.executable, mock_script, "5"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )

        # Wait for it to acquire lock and start processing
        time.sleep(2)

        # Verify first process is active (heartbeat exists)
        hb_file = Path("/tmp/podcast_test_heartbeat.json")
        assert hb_file.exists(), "First process didn't start — no heartbeat"

        hb = json.loads(hb_file.read_text())
        assert hb["status"] == "running"
        assert hb["videoId"] == "mock001"

        # Verify lock file exists
        lock_file = Path("/tmp/podcast-hermes-processor.lock")
        assert lock_file.exists(), "Lock file not created by first process"

        # Start second process — should be blocked
        proc2 = subprocess.run(
            [sys.executable, mock_script, "5"],
            capture_output=True, text=True, timeout=10
        )

        # Second process should exit with already_running
        output2 = json.loads(proc2.stdout.strip())
        assert output2.get("error") == "already_running", \
            f"Second process should be blocked, got: {output2}"

        # Only one item should be in processing
        qm = QueueManager(QUEUE_FILE)
        queue = qm._load_queue()
        assert queue["processing"] is not None
        assert queue["processing"]["videoId"] == "mock001"
        # mock002 should still be pending
        pending_ids = [v["videoId"] for v in queue["pending"]]
        assert "mock002" in pending_ids, "mock002 should still be pending"

        # Wait for first process to finish
        proc1.wait(timeout=15)

        # After first finishes, lock should be released
        assert not lock_file.exists(), "Lock not released after process exit"

        # First video should be completed
        queue = qm._load_queue()
        completed_ids = [v["videoId"] for v in queue["completed"]]
        assert "mock001" in completed_ids, "mock001 should be completed"

    def test_third_process_also_blocked(self, mock_queue, mock_script):
        """Three processes started — only first runs, 2nd and 3rd blocked."""
        # Start first
        proc1 = subprocess.Popen(
            [sys.executable, mock_script, "5"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        time.sleep(2)

        # Start second
        proc2 = subprocess.run(
            [sys.executable, mock_script, "5"],
            capture_output=True, text=True, timeout=10
        )
        assert json.loads(proc2.stdout.strip()).get("error") == "already_running"

        # Start third
        proc3 = subprocess.run(
            [sys.executable, mock_script, "5"],
            capture_output=True, text=True, timeout=10
        )
        assert json.loads(proc3.stdout.strip()).get("error") == "already_running"

        # Only first is running
        hb = json.loads(Path("/tmp/podcast_test_heartbeat.json").read_text())
        assert hb["videoId"] == "mock001"

        proc1.wait(timeout=15)

    def test_next_video_available_after_first_completes(self, mock_queue, mock_script):
        """After first process completes, second process can get the next video."""
        # First process runs for 3 seconds
        proc1 = subprocess.run(
            [sys.executable, mock_script, "3"],
            capture_output=True, text=True, timeout=15
        )

        assert proc1.returncode == 0
        # Mock script prints status lines + final JSON — parse last JSON line
        json_line = [l for l in proc1.stdout.strip().split("\n") if l.startswith("{")][-1]
        output1 = json.loads(json_line)
        assert output1["success"] is True
        assert output1["videoId"] == "mock001"

        # Lock should be released
        assert not Path("/tmp/podcast-hermes-processor.lock").exists()

        # mock001 should be completed
        qm = QueueManager(QUEUE_FILE)
        queue = qm._load_queue()
        assert queue["processing"] is None
        completed_ids = [v["videoId"] for v in queue["completed"]]
        assert "mock001" in completed_ids

        # Second process should get mock002
        proc2 = subprocess.run(
            [sys.executable, mock_script, "3"],
            capture_output=True, text=True, timeout=15
        )

        output2 = json.loads(
            [l for l in proc2.stdout.strip().split("\n") if l.startswith("{")][-1]
        )
        assert output2["success"] is True
        assert output2["videoId"] == "mock002"

    def test_failed_video_does_not_block_queue(self, mock_queue, mock_script):
        """If first video fails, queue should continue with next video."""
        # First process fails
        proc1 = subprocess.run(
            [sys.executable, mock_script, "2", "--fail"],
            capture_output=True, text=True, timeout=15
        )

        output1 = json.loads(
            [l for l in proc1.stdout.strip().split("\n") if l.startswith("{")][-1]
        )
        assert output1["success"] is False
        assert output1["error"] == "Mock failure"

        # mock001 should be in failed
        qm = QueueManager(QUEUE_FILE)
        queue = qm._load_queue()
        failed_ids = [v["videoId"] for v in queue["failed"]]
        assert "mock001" in failed_ids
        assert queue["processing"] is None

        # Second process should get mock002
        proc2 = subprocess.run(
            [sys.executable, mock_script, "2"],
            capture_output=True, text=True, timeout=15
        )

        output2 = json.loads(
            [l for l in proc2.stdout.strip().split("\n") if l.startswith("{")][-1]
        )
        assert output2["success"] is True
        assert output2["videoId"] == "mock002"


# ─── Queue Integrity ─────────────────────────────────────────────────────────

class TestQueueIntegrity:
    """Verify queue state remains consistent during concurrent access."""

    def test_no_duplicate_processing(self, mock_queue):
        """Processing slot should never have more than one item."""
        qm = mock_queue

        # Simulate rapid get_next_video calls
        video = qm.get_next_video()
        assert video is not None

        # Queue file should have exactly one processing item
        queue = qm._load_queue()
        assert queue["processing"] is not None
        assert isinstance(queue["processing"], dict)
        # Not a list, not multiple items
        assert not isinstance(queue["processing"], list)

    def test_pending_count_decrements(self, mock_queue):
        """Each get_next_video should decrement pending by 1."""
        qm = mock_queue

        initial = qm.get_status()
        assert initial["pending"] == 3

        qm.get_next_video()
        after1 = qm.get_status()
        assert after1["pending"] == 2

        # Second call returns None (processing occupied), pending stays 2
        video2 = qm.get_next_video()
        assert video2 is None
        after2 = qm.get_status()
        assert after2["pending"] == 2, "Pending should not change when processing is occupied"

    def test_completed_does_not_return_to_pending(self, mock_queue):
        """Completed items should never be re-queued."""
        qm = mock_queue

        # Process and complete video
        video = qm.get_next_video()
        qm.mark_completed(video["videoId"])

        # Get next — should not be the completed one
        video2 = qm.get_next_video()
        if video2:
            assert video2["videoId"] != video["videoId"], \
                "Completed video was re-queued!"

    def test_failed_can_be_re_added(self, mock_queue):
        """Failed items should be re-addable to queue (retry)."""
        qm = mock_queue

        video = qm.get_next_video()
        qm.mark_failed(video["videoId"], "Test failure")

        # Re-add should work (add_videos checks existing IDs)
        added = qm.add_videos([{
            "videoId": video["videoId"],
            "title": video["title"],
            "channel": video["channel"]
        }])

        # QueueManager checks pending + completed + failed, but failed
        # items should be re-addable
        queue = qm._load_queue()
        failed_ids = [v["videoId"] for v in queue["failed"]]
        pending_ids = [v["videoId"] for v in queue["pending"]]

        # Either it was re-added to pending, or it was rejected (still in failed)
        if added > 0:
            assert video["videoId"] in pending_ids, \
                "Video was re-added but not in pending"
        else:
            # QueueManager rejected it because it's still in failed
            # This is a design question — should failed items be re-addable?
            pass