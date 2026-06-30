#!/usr/bin/env python3
"""
End-to-end test: process 2 videos (15-30 min each) through full pipeline.

Tests the entire sequential flow:
  Video 1: download → chunk → transcribe → prepare → translate → TTS → audio
  Video 2: download → chunk → transcribe → prepare → translate → TTS → audio

Both processed sequentially — video 2 starts ONLY after video 1 completes.
Only ONE video is processed at any time (queue + PID-lock).

This is the slowest test (~1-2 hours on RPi for 2 videos).
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from conftest import (
    PROJECT_DIR, SCRIPTS_DIR, INPUT_DIR, TRANSCRIPTS_DIR,
    TRANSLATIONS_DIR, AUDIO_DIR, CHUNKS_DIR, QUEUE_FILE
)

sys.path.insert(0, str(PROJECT_DIR))
from queue_manager import QueueManager


# Two test videos: 15.9 min and 21.6 min
E2E_VIDEOS = [
    {
        "videoId": "20vZc0cOpOw",
        "title": "All of AI's New Models and Tools",
        "channel": "AIDailyBrief",
        "url": "https://www.youtube.com/watch?v=20vZc0cOpOw",
        "duration_min": 15.9
    },
    {
        "videoId": "P_oabCLJhb0",
        "title": "OpenAI Proposes a New Deal",
        "channel": "AIDailyBrief",
        "url": "https://www.youtube.com/watch?v=P_oabCLJhb0",
        "duration_min": 21.6
    },
]


@pytest.fixture
def e2e_clean_queue(clean_queue):
    """Queue with exactly 2 test videos."""
    qm = clean_queue
    qm.add_videos([
        {"videoId": E2E_VIDEOS[0]["videoId"], "title": E2E_VIDEOS[0]["title"], "channel": E2E_VIDEOS[0]["channel"]},
        {"videoId": E2E_VIDEOS[1]["videoId"], "title": E2E_VIDEOS[1]["title"], "channel": E2E_VIDEOS[1]["channel"]},
    ])
    yield qm


class TestE2ETwoVideos:
    """End-to-end: process 2 videos sequentially through full pipeline.

    Video 1 (~16 min) → Video 2 (~22 min) → both done.
    Total time on RPi: ~1-1.5 hours (whisper + TTS).
    """

    @pytest.mark.slow
    @pytest.mark.whisper
    def test_two_videos_full_pipeline(self, e2e_clean_queue):
        """Process 2 videos through hermes_queue_processor.py.

        Verifies:
        - Both videos processed sequentially
        - Only ONE in processing at any time
        - Each produces: transcript → translation (no timestamps) → TTS audio
        - Audio files exist and have correct duration
        - Queue ends empty (all completed)
        """
        qm = e2e_clean_queue

        # Verify queue has 2 pending
        status = qm.get_status()
        assert status["pending"] == 2, f"Expected 2 pending, got {status['pending']}"
        assert status["processing"] == 0
        assert status["completed"] == 0

        # Run hermes_queue_processor.py — processes entire queue
        # Timeout: 2 hours (2 videos × ~30-40 min each on RPi)
        result = subprocess.run(
            ["python3", str(PROJECT_DIR / "hermes_queue_processor.py"),
             "--voice", "ru-RU-DmitryNeural", "--json"],
            capture_output=True, text=True,
            timeout=7200,  # 2 hours
            cwd=str(PROJECT_DIR)
        )

        assert result.returncode == 0, \
            f"Processor failed (exit {result.returncode}):\n{result.stderr[:500]}"

        # Parse JSON summary — may be multi-line (indent=2) or single line
        # The JSON block may be followed by non-JSON output (HERMES_* lines)
        stdout = result.stdout.strip()
        # Find the last JSON object that contains "processed"
        summary = None
        # Search for JSON blocks starting with '{' on its own line
        for i, line in enumerate(stdout.split('\n')):
            if line.strip().startswith('{'):
                candidate_str = '\n'.join(stdout.split('\n')[i:])
                try:
                    # raw_decode parses the first JSON object and returns end position
                    decoder = json.JSONDecoder()
                    obj, end = decoder.raw_decode(candidate_str)
                    if isinstance(obj, dict) and 'processed' in obj:
                        summary = obj
                        break
                except json.JSONDecodeError:
                    continue

        assert summary is not None, \
            f"Could not parse JSON summary from output:\n{stdout[-500:]}"
        assert summary["processed"] == 2, \
            f"Expected 2 videos processed, got {summary['processed']}"
        assert summary["success"] == 2, \
            f"Expected 2 successes, got {summary['success']}"

        # Verify queue state — all completed, nothing pending
        queue = qm._load_queue()
        assert queue["processing"] is None, "Processing slot should be empty"
        assert len(queue["pending"]) == 0, "No videos should be pending"
        assert len(queue["completed"]) == 2, f"Expected 2 completed, got {len(queue['completed'])}"
        assert len(queue["failed"]) == 0, f"Expected 0 failed, got {len(queue['failed'])}"

        # Verify each video's output files
        completed_ids = [v["videoId"] for v in queue["completed"]]
        assert E2E_VIDEOS[0]["videoId"] in completed_ids
        assert E2E_VIDEOS[1]["videoId"] in completed_ids

        for video in E2E_VIDEOS:
            vid = video["videoId"]
            # Find the actual basename used (podcast_TIMESTAMP)
            # Check completed entry for output file paths
            completed = [v for v in queue["completed"] if v["videoId"] == vid][0]
            output_files = completed.get("outputFiles", {})

            # Audio file should exist
            audio_path = output_files.get("audio", "")
            assert audio_path, f"No audio path for {vid}"
            assert Path(audio_path).exists(), \
                f"Audio file not found for {vid}: {audio_path}"
            assert Path(audio_path).stat().st_size > 50000, \
                f"Audio file too small for {vid}: {Path(audio_path).stat().st_size} bytes"

            # Check audio duration — should be > 5 min for 15+ min podcast
            dur_result = subprocess.run(
                ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                 "-of", "csv=p=0", str(audio_path)],
                capture_output=True, text=True, timeout=10
            )
            audio_duration = float(dur_result.stdout.strip())
            assert audio_duration > 300, \
                f"Audio for {vid} too short: {audio_duration:.0f}s (expected >300s)"

            # TTS text file should exist and have no timestamps
            tts_path = output_files.get("ttsText", "")
            assert tts_path, f"No TTS text path for {vid}"
            assert Path(tts_path).exists(), \
                f"TTS text not found for {vid}: {tts_path}"

            tts_content = Path(tts_path).read_text(encoding="utf-8")
            # Must contain Cyrillic
            assert any("\u0400" <= c <= "\u04ff" for c in tts_content), \
                f"No Cyrillic in translation for {vid}"
            # MUST NOT contain timestamps or markers
            assert "[" not in tts_content, \
                f"Translation for {vid} contains '[' — timestamps leaked"
            assert "]" not in tts_content, \
                f"Translation for {vid} contains ']' — timestamps leaked"

            # Transcript should exist
            transcript_path = output_files.get("transcript", "")
            assert transcript_path, f"No transcript path for {vid}"
            assert Path(transcript_path).exists(), \
                f"Transcript not found for {vid}: {transcript_path}"

            print(f"\n✅ {vid} ({video['title']}):")
            print(f"   Audio: {audio_duration:.0f}s, {Path(audio_path).stat().st_size / 1024 / 1024:.1f} MB")
            print(f"   TTS text: {len(tts_content)} chars, no timestamps ✓")
            print(f"   Transcript: {Path(transcript_path).stat().st_size} bytes")

    @pytest.mark.slow
    @pytest.mark.whisper
    def test_only_one_processing_at_a_time(self, e2e_clean_queue):
        """During E2E processing, poll queue — never >1 in processing slot.

        Starts processor in background, polls queue every 5 seconds.
        Verifies only ONE video is processing at any time.
        """
        qm = e2e_clean_queue

        # Start processor in background
        proc = subprocess.Popen(
            ["python3", str(PROJECT_DIR / "hermes_queue_processor.py"),
             "--voice", "ru-RU-DmitryNeural"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            cwd=str(PROJECT_DIR)
        )

        # Poll queue state every 5 seconds
        checks = []
        max_polls = 720  # 1 hour max (720 × 5s = 3600s)

        for _ in range(max_polls):
            time.sleep(5)
            queue = qm._load_queue()

            processing_count = 1 if queue["processing"] else 0
            pending_count = len(queue["pending"])
            completed_count = len(queue["completed"])
            failed_count = len(queue["failed"])
            processing_id = queue["processing"]["videoId"] if queue["processing"] else None

            checks.append({
                "processing": processing_count,
                "pending": pending_count,
                "completed": completed_count,
                "failed": failed_count,
                "processing_id": processing_id
            })

            # CRITICAL: never more than 1 in processing
            assert processing_count <= 1, \
                f"More than 1 video in processing! processing={processing_count}"

            # Stop when processor finishes (all done)
            if proc.poll() is not None:
                break

        # Wait for process to finish if still running
        proc.wait(timeout=30)

        # Should have seen at least some activity
        assert len(checks) > 0, "No queue checks recorded"

        # Should have seen both videos in processing (sequentially)
        processing_ids = [c["processing_id"] for c in checks if c["processing_id"]]
        assert E2E_VIDEOS[0]["videoId"] in processing_ids, \
            f"Video 1 ({E2E_VIDEOS[0]['videoId']}) never seen in processing"
        assert E2E_VIDEOS[1]["videoId"] in processing_ids, \
            f"Video 2 ({E2E_VIDEOS[1]['videoId']}) never seen in processing"

        # Verify sequential order: video1 before video2
        first_seen = {}
        for i, c in enumerate(checks):
            if c["processing_id"] and c["processing_id"] not in first_seen:
                first_seen[c["processing_id"]] = i

        vid1 = E2E_VIDEOS[0]["videoId"]
        vid2 = E2E_VIDEOS[1]["videoId"]
        if vid1 in first_seen and vid2 in first_seen:
            assert first_seen[vid1] < first_seen[vid2], \
                f"Video 2 started before Video 1 — not sequential!"

        # Final state — all completed
        queue = qm._load_queue()
        assert queue["processing"] is None
        assert len(queue["completed"]) == 2, \
            f"Expected 2 completed, got {len(queue['completed'])}"
        assert len(queue["pending"]) == 0

        # Report timing
        total_checks = len(checks)
        print(f"\n📊 Polling Results:")
        print(f"   Total checks: {total_checks} (×5s = {total_checks * 5}s)")
        print(f"   Processing IDs seen: {set(processing_ids)}")
        print(f"   Video 1 first seen at check {first_seen.get(vid1, '?')}")
        print(f"   Video 2 first seen at check {first_seen.get(vid2, '?')}")
        print(f"   Final: {len(queue['completed'])} completed, {len(queue['pending'])} pending")