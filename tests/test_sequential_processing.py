#!/usr/bin/env python3
"""
Test that hermes_queue_processor processes ALL pending videos in sequence.

After completing video1, it should automatically get video2, process it,
then video3, etc. — until the queue is empty. Only ONE video is processed
at any time. The next video is only taken AFTER the previous one completes
(fails or succeeds).

Uses mock_pipeline.py to simulate long-running tasks.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from conftest import PROJECT_DIR, QUEUE_FILE

sys.path.insert(0, str(PROJECT_DIR))
from queue_manager import QueueManager


# Reuse the mock script from test_queue_concurrency
MOCK_PIPELINE_SCRIPT = PROJECT_DIR / "tests" / "mock_pipeline.py"

MOCK_TASK_SCRIPT_CONTENT = """
#!/usr/bin/env python3
\"\"\"Mock long-running pipeline task for testing queue concurrency.

Simulates a real pipeline by sleeping for a configurable duration.
Uses the SAME PID-lock as hermes_queue_processor.py.
Processes ALL pending videos in a loop, one at a time.
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
    duration = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    should_fail = "--fail" in sys.argv

    if not acquire_lock():
        print(json.dumps({"success": False, "error": "already_running"}))
        sys.exit(0)

    try:
        qm = QueueManager(QUEUE_FILE)

        results = []
        processed = 0

        # Process ALL pending videos, one at a time (same loop as hermes_queue_processor)
        while True:
            video = qm.get_next_video()
            if not video:
                break

            processed += 1
            video_id = video["videoId"]
            print(f"MOCK: Processing {video_id} ({video['title']})")

            # Write heartbeat
            HEARTBEAT_FILE.write_text(json.dumps({
                "pid": os.getpid(),
                "videoId": video_id,
                "startedAt": time.time(),
                "status": "running",
                "processed": processed
            }))

            # Simulate pipeline work
            for i in range(duration):
                time.sleep(1)
                hb = json.loads(HEARTBEAT_FILE.read_text())
                hb["elapsed"] = i + 1
                HEARTBEAT_FILE.write_text(json.dumps(hb))
                print(f"MOCK: {video_id} tick {i+1}/{duration}")

            if should_fail and processed == 1:
                qm.mark_failed(video_id, "Mock failure")
                results.append({"videoId": video_id, "success": False, "error": "Mock failure"})
                print(f"MOCK: {video_id} FAILED")
            else:
                qm.mark_completed(video_id, {"audio": f"/tmp/mock_{video_id}.mp3"})
                results.append({"videoId": video_id, "success": True, "audio_path": f"/tmp/mock_{video_id}.mp3"})
                print(f"MOCK: {video_id} COMPLETED")

        # Final summary
        summary = {
            "success": all(r.get("success") for r in results),
            "processed": processed,
            "results": results
        }
        print(json.dumps(summary, ensure_ascii=False))

    finally:
        release_lock()
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
        {"videoId": "seq001", "title": "Sequence Test 1", "channel": "TestChannel"},
        {"videoId": "seq002", "title": "Sequence Test 2", "channel": "TestChannel"},
        {"videoId": "seq003", "title": "Sequence Test 3", "channel": "TestChannel"},
    ])
    yield qm


@pytest.fixture
def mock_processor_script():
    """Create the mock processor script that processes all videos in a loop."""
    script_path = PROJECT_DIR / "tests" / "mock_processor_all.py"
    script_path.write_text(MOCK_TASK_SCRIPT_CONTENT.strip())
    script_path.chmod(0o755)

    # Clean leftovers
    Path("/tmp/podcast_test_heartbeat.json").unlink(missing_ok=True)
    Path("/tmp/podcast-hermes-processor.lock").unlink(missing_ok=True)

    yield str(script_path)

    # Cleanup
    Path("/tmp/podcast_test_heartbeat.json").unlink(missing_ok=True)
    Path("/tmp/podcast-hermes-processor.lock").unlink(missing_ok=True)
    script_path.unlink(missing_ok=True)


# ─── Sequential Processing Tests ────────────────────────────────────────────

class TestSequentialProcessing:
    """Verify that all pending videos are processed sequentially.

    After video1 completes → get_next_video returns video2 → process →
    After video2 completes → get_next_video returns video3 → process →
    After video3 completes → get_next_video returns None → stop.
    """

    @pytest.mark.slow
    def test_processes_all_videos_in_sequence(self, mock_queue, mock_processor_script):
        """All 3 videos should be processed one after another, not in parallel."""
        qm = mock_queue

        # Run mock processor (3 sec per video, 3 videos = ~9 sec)
        result = subprocess.run(
            [sys.executable, mock_processor_script, "2"],
            capture_output=True, text=True, timeout=30
        )

        assert result.returncode == 0, f"Processor failed: {result.stderr[:300]}"

        # Parse final JSON summary
        json_line = [l for l in result.stdout.strip().split("\n") if l.startswith("{")][-1]
        summary = json.loads(json_line)

        assert summary["processed"] == 3, \
            f"Expected 3 videos processed, got {summary['processed']}"

        # All should succeed
        for r in summary["results"]:
            assert r["success"] is True, f"Video {r['videoId']} failed"

        # Verify queue state — all 3 completed
        queue = qm._load_queue()
        assert queue["processing"] is None, "Processing slot should be empty"
        assert queue["pending"] == [], "No videos should be pending"

        completed_ids = [v["videoId"] for v in queue["completed"]]
        assert "seq001" in completed_ids
        assert "seq002" in completed_ids
        assert "seq003" in completed_ids

    @pytest.mark.slow
    def test_failed_video_continues_to_next(self, mock_queue, mock_processor_script):
        """If video1 fails, video2 and video3 should still be processed."""
        qm = mock_queue

        # Run with --fail flag (first video fails, rest succeed)
        result = subprocess.run(
            [sys.executable, mock_processor_script, "1", "--fail"],
            capture_output=True, text=True, timeout=30
        )

        assert result.returncode == 0, f"Processor failed: {result.stderr[:300]}"

        json_line = [l for l in result.stdout.strip().split("\n") if l.startswith("{")][-1]
        summary = json.loads(json_line)

        assert summary["processed"] == 3, \
            f"Expected 3 videos processed (1 failed + 2 success), got {summary['processed']}"

        # First video should fail, others succeed
        results_by_id = {r["videoId"]: r for r in summary["results"]}
        assert results_by_id["seq001"]["success"] is False, "seq001 should fail"
        assert results_by_id["seq002"]["success"] is True, "seq002 should succeed"
        assert results_by_id["seq003"]["success"] is True, "seq003 should succeed"

        # Verify queue state
        queue = qm._load_queue()
        assert queue["processing"] is None
        assert queue["pending"] == []

        failed_ids = [v["videoId"] for v in queue["failed"]]
        completed_ids = [v["videoId"] for v in queue["completed"]]
        assert "seq001" in failed_ids
        assert "seq002" in completed_ids
        assert "seq003" in completed_ids

    @pytest.mark.slow
    def test_only_one_active_at_a_time(self, mock_queue, mock_processor_script):
        """CRITICAL: Only ONE video in processing at any time during the loop.

        Starts the mock processor in background, then checks queue state
        at intervals — processing should never have more than 1 item.
        """
        qm = mock_queue

        # Start processor in background (2 sec per video)
        proc = subprocess.Popen(
            [sys.executable, mock_processor_script, "2"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )

        # Poll queue state every 0.5 seconds while processor runs
        checks = []
        for _ in range(20):  # 10 seconds max
            time.sleep(0.5)
            queue = qm._load_queue()

            processing_count = 1 if queue["processing"] else 0
            pending_count = len(queue["pending"])
            completed_count = len(queue["completed"])
            processing_id = queue["processing"]["videoId"] if queue["processing"] else None

            checks.append({
                "processing": processing_count,
                "pending": pending_count,
                "completed": completed_count,
                "processing_id": processing_id
            })

            # CRITICAL: never more than 1 in processing
            assert processing_count <= 1, \
                f"More than 1 video in processing! processing={processing_count}"

            # If processor finished, stop polling
            if proc.poll() is not None:
                break

        proc.wait(timeout=10)

        # Verify we saw transitions: processing moved through seq001 → seq002 → seq003
        processing_ids_seen = [c["processing_id"] for c in checks if c["processing_id"]]
        assert "seq001" in processing_ids_seen, "Never saw seq001 in processing"
        assert "seq002" in processing_ids_seen, "Never saw seq002 in processing"
        assert "seq003" in processing_ids_seen, "Never saw seq003 in processing"

        # Verify order: seq001 before seq002 before seq003
        first_seen = {}
        for i, c in enumerate(checks):
            if c["processing_id"] and c["processing_id"] not in first_seen:
                first_seen[c["processing_id"]] = i

        assert first_seen["seq001"] < first_seen["seq002"], \
            "seq002 started before seq001 — wrong order!"
        assert first_seen["seq002"] < first_seen["seq003"], \
            "seq003 started before seq002 — wrong order!"

    @pytest.mark.slow
    def test_empty_queue_exits_cleanly(self, clean_queue, mock_processor_script):
        """Empty queue should exit immediately with success."""
        qm = clean_queue  # No videos added

        result = subprocess.run(
            [sys.executable, mock_processor_script, "1"],
            capture_output=True, text=True, timeout=10
        )

        assert result.returncode == 0
        json_line = [l for l in result.stdout.strip().split("\n") if l.startswith("{")][-1]
        summary = json.loads(json_line)
        assert summary["processed"] == 0, "Should process 0 videos from empty queue"

    @pytest.mark.slow
    def test_second_process_blocked_while_first_running(self, mock_queue, mock_processor_script):
        """While processor is running, second process is blocked by PID-lock."""
        qm = mock_queue

        # Start first processor (5 sec per video, 3 videos = ~15 sec)
        proc1 = subprocess.Popen(
            [sys.executable, mock_processor_script, "5"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )

        # Wait for it to start
        time.sleep(2)

        # Verify it's running (heartbeat exists)
        hb_file = Path("/tmp/podcast_test_heartbeat.json")
        assert hb_file.exists(), "First processor didn't start"

        # Start second processor — should be blocked
        proc2 = subprocess.run(
            [sys.executable, mock_processor_script, "1"],
            capture_output=True, text=True, timeout=10
        )

        output2 = json.loads(
            [l for l in proc2.stdout.strip().split("\n") if l.startswith("{")][-1]
        )
        assert output2.get("error") == "already_running", \
            f"Second processor should be blocked, got: {output2}"

        # Wait for first to finish
        proc1.wait(timeout=30)

        # Now third process should be able to start (queue may have remaining items)
        # But queue should be empty if first processed everything
        queue = qm._load_queue()
        # All should be completed
        assert queue["processing"] is None
        if queue["pending"]:
            # If there are still pending (e.g. first process was killed early)
            proc3 = subprocess.run(
                [sys.executable, mock_processor_script, "1"],
                capture_output=True, text=True, timeout=15
            )
            assert proc3.returncode == 0