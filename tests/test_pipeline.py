#!/usr/bin/env python3
"""
Test pipeline steps: download → chunk → transcribe.
Tests run against the real test video (~27 min podcast).

Markers:
    @pytest.mark.download  — requires network, downloads from YouTube
    @pytest.mark.slow       — takes >10 sec (transcription, chunking)
    @pytest.mark.whisper    — loads whisper model (CPU-intensive)
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
    TRANSLATIONS_DIR, AUDIO_DIR, CHUNKS_DIR, LOGS_DIR,
    TEST_VIDEO_URL, TEST_VIDEO_ID, TEST_VIDEO_TITLE,
    TEST_VIDEO_DURATION_SEC
)


# ─── Download ────────────────────────────────────────────────────────────────

class TestDownload:
    """Test Step 1: Download audio from YouTube."""

    @pytest.mark.download
    @pytest.mark.slow
    def test_download_audio(self, clean_dirs):
        """Download test video as MP3 and verify file exists."""
        output_path = INPUT_DIR / f"test_{TEST_VIDEO_ID}.mp3"

        result = subprocess.run(
            [
                "yt-dlp",
                "-x", "--audio-format", "mp3", "--audio-quality", "0",
                "--js-runtimes", "node:/home/dmaxy/.nvm/versions/node/v22.19.0/bin/node",
                "--remote-components", "ejs:github",
                "-o", str(output_path),
                TEST_VIDEO_URL
            ],
            capture_output=True, text=True, timeout=120
        )

        assert result.returncode == 0, f"yt-dlp failed: {result.stderr[:300]}"

        # File should exist
        downloaded = list(INPUT_DIR.glob(f"test_{TEST_VIDEO_ID}.*"))
        assert downloaded, f"Downloaded file not found in {INPUT_DIR}"
        assert downloaded[0].stat().st_size > 10000, "File too small (<10KB) — probably empty"

    @pytest.mark.download
    def test_download_duration_matches(self, clean_dirs):
        """Verify downloaded audio duration is in expected range (~27 min)."""
        output_path = INPUT_DIR / f"test_{TEST_VIDEO_ID}.mp3"

        subprocess.run(
            ["yt-dlp", "-x", "--audio-format", "mp3", "--audio-quality", "0",
             "-o", str(output_path), TEST_VIDEO_URL],
            capture_output=True, text=True, timeout=120
        )

        downloaded = list(INPUT_DIR.glob(f"test_{TEST_VIDEO_ID}.*"))
        assert downloaded, "File not downloaded"

        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(downloaded[0])],
            capture_output=True, text=True, timeout=10
        )

        duration = float(result.stdout.strip())
        # 27.4 min = 1644 sec. Allow ±60 sec tolerance
        assert abs(duration - TEST_VIDEO_DURATION_SEC) < 120, \
            f"Duration {duration:.1f}s != expected {TEST_VIDEO_DURATION_SEC}s (±120s)"


# ─── Chunking ────────────────────────────────────────────────────────────────

class TestChunking:
    """Test Step 2: Split long audio into 5-minute chunks."""

    @pytest.mark.slow
    def test_chunk_audio_creates_chunks(self, session_audio_file):
        """chunk_audio.py should split ~27 min audio into ~6 chunks of 5 min."""
        result = subprocess.run(
            ["python3", str(SCRIPTS_DIR / "chunk_audio.py"), session_audio_file],
            capture_output=True, text=True, timeout=120
        )

        assert result.returncode == 0, f"chunk_audio.py failed: {result.stderr[:300]}"

        # chunk_audio.py outputs pretty-printed JSON (indent=2) — parse full stdout
        output = json.loads(result.stdout)

        assert output["chunking"] is True, "Should require chunking for 27-min audio"
        assert output["totalChunks"] >= 5, f"Expected >=5 chunks, got {output['totalChunks']}"
        assert output["totalChunks"] <= 7, f"Expected <=7 chunks, got {output['totalChunks']}"

    @pytest.mark.slow
    def test_chunk_files_exist(self, session_audio_file):
        """Verify that chunk MP3 files are actually created on disk."""
        subprocess.run(
            ["python3", str(SCRIPTS_DIR / "chunk_audio.py"), session_audio_file],
            capture_output=True, text=True, timeout=120
        )

        # video_id = audio filename stem
        video_id = Path(session_audio_file).stem

        chunks_json = CHUNKS_DIR / f"{video_id}_chunks.json"
        assert chunks_json.exists(), f"chunks.json not found: {chunks_json}"

        meta = json.loads(chunks_json.read_text())
        assert meta["totalChunks"] == len(meta["chunks"]), \
            "totalChunks doesn't match actual chunks list"

        for chunk in meta["chunks"]:
            chunk_file = CHUNKS_DIR / chunk["file"]
            assert chunk_file.exists(), f"Chunk file missing: {chunk_file}"
            assert chunk_file.stat().st_size > 1000, \
                f"Chunk file too small: {chunk_file} ({chunk_file.stat().st_size} bytes)"

    @pytest.mark.slow
    def test_chunk_json_metadata(self, session_audio_file):
        """Verify chunks.json has correct structure and offsets."""
        subprocess.run(
            ["python3", str(SCRIPTS_DIR / "chunk_audio.py"), session_audio_file],
            capture_output=True, text=True, timeout=120
        )

        video_id = Path(session_audio_file).stem
        meta = json.loads((CHUNKS_DIR / f"{video_id}_chunks.json").read_text())

        # Check structure
        assert meta["videoId"] == video_id
        assert meta["chunkDuration"] == 300  # 5 minutes
        assert meta["sourceDuration"] > 1200  # >20 min
        assert meta["status"] == "transcribing"

        # Check each chunk metadata
        for i, chunk in enumerate(meta["chunks"]):
            assert chunk["index"] == i + 1
            assert chunk["startOffset"] == i * 300, \
                f"Chunk {i+1} offset {chunk['startOffset']} != {i * 300}"
            assert chunk["status"] == "pending"

    @pytest.mark.download
    def test_short_audio_no_chunking(self, clean_dirs):
        """Short audio (<5 min) should return chunking: false."""
        # Download a short video (~1 min)
        short_url = "https://www.youtube.com/watch?v=QymmGOKO5sk"  # ~0.8 min
        output = INPUT_DIR / "test_short.mp3"

        subprocess.run(
            ["yt-dlp", "-x", "--audio-format", "mp3",
             "--js-runtimes", "node:/home/dmaxy/.nvm/versions/node/v22.19.0/bin/node",
             "--remote-components", "ejs:github",
             "-o", str(output), short_url],
            capture_output=True, text=True, timeout=60
        )

        downloaded = list(INPUT_DIR.glob("test_short.*"))
        if not downloaded:
            pytest.skip("Failed to download short test video")

        result = subprocess.run(
            ["python3", str(SCRIPTS_DIR / "chunk_audio.py"), str(downloaded[0])],
            capture_output=True, text=True, timeout=30
        )

        output_data = json.loads(result.stdout)
        assert output_data["chunking"] is False, \
            "Short audio should not require chunking"


# ─── Transcription ──────────────────────────────────────────────────────────

class TestTranscription:
    """Test Step 2b: Transcribe audio with faster-whisper.

    Uses session-scoped fixtures: download + chunk + transcribe happen ONCE.
    """

    @pytest.mark.slow
    @pytest.mark.whisper
    def test_transcribe_short_audio(self, clean_dirs):
        """Transcribe a short (~1 min) video directly via transcribe_cached.py."""
        # Use a short video for speed
        short_url = "https://www.youtube.com/watch?v=QymmGOKO5sk"  # ~0.8 min
        output = INPUT_DIR / "test_short.mp3"

        subprocess.run(
            ["yt-dlp", "-x", "--audio-format", "mp3",
             "--js-runtimes", "node:/home/dmaxy/.nvm/versions/node/v22.19.0/bin/node",
             "--remote-components", "ejs:github",
             "-o", str(output), short_url],
            capture_output=True, text=True, timeout=60
        )

        downloaded = list(INPUT_DIR.glob("test_short.*"))
        if not downloaded:
            pytest.skip("Failed to download short test video")

        result = subprocess.run(
            ["python3", str(SCRIPTS_DIR / "transcribe_cached.py"),
             str(downloaded[0]), str(TRANSCRIPTS_DIR), "tiny"],
            capture_output=True, text=True, timeout=300
        )

        assert result.returncode == 0, f"Transcription failed: {result.stderr[:300]}"

        transcript = TRANSCRIPTS_DIR / f"{Path(downloaded[0]).stem}.txt"
        assert transcript.exists(), f"Transcript not found: {transcript}"

        content = transcript.read_text(encoding="utf-8").strip()
        assert len(content) > 10, "Transcript is empty or too short"
        assert "[" in content, "Transcript should have timestamps"

    @pytest.mark.slow
    @pytest.mark.whisper
    def test_transcribe_chunked_all(self, session_chunks):
        """Transcribe all chunks with --all flag (model loaded once).

        Uses session_chunks fixture — chunks already created.
        If already transcribed (from previous run), verifies results.
        """
        video_id, meta = session_chunks

        # Check current state
        chunks_json = CHUNKS_DIR / f"{video_id}_chunks.json"
        current_meta = json.loads(chunks_json.read_text())

        # If not all done, transcribe
        if not all(c["status"] == "done" for c in current_meta["chunks"]):
            result = subprocess.run(
                ["python3", str(SCRIPTS_DIR / "transcribe_chunk.py"), "--all", video_id],
                capture_output=True, text=True, timeout=3600
            )
            assert result.returncode == 0, f"Transcription failed: {result.stderr[:500]}"
            output = json.loads(result.stdout)
            assert output.get("allDone") is True, f"Not all chunks done: {output}"

        # Verify all chunk transcripts exist
        final_meta = json.loads(chunks_json.read_text())
        assert all(c["status"] == "done" for c in final_meta["chunks"]), \
            "Not all chunks marked as done"

        for chunk in final_meta["chunks"]:
            chunk_stem = Path(chunk["file"]).stem
            chunk_txt = CHUNKS_DIR / f"{chunk_stem}.txt"
            assert chunk_txt.exists(), f"Chunk transcript missing: {chunk_txt}"
            content = chunk_txt.read_text(encoding="utf-8").strip()
            assert len(content) > 0, f"Empty transcript for chunk {chunk['index']}"

    @pytest.mark.slow
    @pytest.mark.whisper
    def test_assemble_chunks(self, session_transcription):
        """Assemble chunk transcripts into a single file.

        Uses session_transcription fixture — transcription + assembly already done.
        """
        video_id, transcript_path = session_transcription

        assert transcript_path is not None, "Transcript path is None"
        transcript = Path(transcript_path)
        assert transcript.exists(), f"Assembled transcript missing: {transcript}"

        content = transcript.read_text(encoding="utf-8")
        assert len(content) > 100, "Assembled transcript too short"

        # Verify it has timestamps
        assert "[" in content, "Transcript should have timestamps [MM:SS - MM:SS]"

        # Count segments (lines starting with [)
        segment_count = sum(1 for line in content.split("\n") if line.strip().startswith("["))
        assert segment_count > 10, f"Too few segments: {segment_count}"

        # Verify chunk files were cleaned up by assemble
        meta_json = CHUNKS_DIR / f"{video_id}_chunks.json"
        assert not meta_json.exists(), "chunks.json should be deleted after assembly"


# ─── Concurrency Lock ─────────────────────────────────────────────────────────
# CRITICAL: Only one transcription process at a time on RPi (4-core CPU)

class TestConcurrencyLock:
    """Test that PID-lock prevents parallel whisper transcription.

    On Raspberry Pi 5 (4-core ARM), running multiple whisper instances
    simultaneously would overload the CPU and cause all processes to hang.
    The PID-lock in transcribe_chunk.py MUST prevent this.
    """

    def test_lock_file_location(self):
        """Lock file should be at /tmp/transcribe_chunk.lock."""
        from scripts.transcribe_chunk import LOCK_FILE
        assert str(LOCK_FILE) == "/tmp/transcribe_chunk.lock", \
            f"Lock file at unexpected path: {LOCK_FILE}"

    def test_hermes_processor_has_own_lock(self):
        """Hermes queue processor should also have a PID-lock."""
        from hermes_queue_processor import LOCK_FILE
        assert "podcast" in str(LOCK_FILE).lower() and "lock" in str(LOCK_FILE).lower(), \
            f"Hermes processor lock file unexpected: {LOCK_FILE}"

    def test_acquire_lock_creates_file(self, tmp_path):
        """Acquiring lock should create lock file with current PID."""
        from scripts.transcribe_chunk import acquire_lock, release_lock, LOCK_FILE

        # Clean any existing lock
        release_lock()

        assert acquire_lock(), "Failed to acquire lock"
        assert LOCK_FILE.exists(), "Lock file not created"
        pid_in_file = LOCK_FILE.read_text().strip()
        assert pid_in_file == str(os.getpid()), \
            f"Lock file PID {pid_in_file} != current PID {os.getpid()}"

        release_lock()
        assert not LOCK_FILE.exists(), "Lock file not removed after release"

    def test_second_acquire_fails(self):
        """Second acquire_lock should fail (prevent parallel run)."""
        from scripts.transcribe_chunk import acquire_lock, release_lock, LOCK_FILE

        release_lock()

        # First acquire — should succeed
        assert acquire_lock(), "First lock acquire failed"

        # Second acquire — should fail (lock already held by us)
        assert not acquire_lock(), "Second lock acquire should fail!"

        release_lock()

    def test_stale_lock_is_cleaned(self):
        """Stale lock (dead PID) should be removed and lock acquired."""
        from scripts.transcribe_chunk import acquire_lock, release_lock, LOCK_FILE

        release_lock()

        # Write a stale lock with non-existent PID
        fake_pid = 999999  # very unlikely to exist
        LOCK_FILE.write_text(str(fake_pid))

        # acquire_lock should detect stale lock and acquire
        assert acquire_lock(), "Failed to acquire after stale lock cleanup"
        assert LOCK_FILE.read_text().strip() == str(os.getpid())

        release_lock()

    @pytest.mark.slow
    @pytest.mark.whisper
    def test_parallel_transcribe_blocked(self, session_audio_file):
        """CRITICAL: Running two transcribe_chunk.py simultaneously must be blocked.

        Starts two transcribe_chunk.py processes in parallel.
        The second one should exit immediately with {"error": "already_running"}.
        Only ONE whisper process should be running at any time.

        Creates fresh pending chunks so transcribe_chunk.py actually starts
        working (and holds the lock long enough to test).
        """
        import shutil

        video_id = Path(session_audio_file).stem

        # Create fresh chunks for this test (reset to pending)
        subprocess.run(
            ["python3", str(SCRIPTS_DIR / "chunk_audio.py"), session_audio_file],
            capture_output=True, text=True, timeout=120
        )

        # Reset all chunks to pending so transcribe_chunk.py has work to do
        chunks_json = CHUNKS_DIR / f"{video_id}_chunks.json"
        meta = json.loads(chunks_json.read_text())
        for c in meta["chunks"]:
            c["status"] = "pending"
        meta["status"] = "transcribing"
        chunks_json.write_text(json.dumps(meta, indent=2, ensure_ascii=False))

        # Clean any existing lock
        from scripts.transcribe_chunk import release_lock
        release_lock()

        # Start first transcription process (will load model — takes a few seconds)
        proc1 = subprocess.Popen(
            ["python3", str(SCRIPTS_DIR / "transcribe_chunk.py"), "--all", video_id],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )

        # Wait a moment for first process to acquire the lock
        # transcribe_chunk.py acquires lock early, before model loading
        time.sleep(3)

        # Check lock file exists with proc1's PID
        from scripts.transcribe_chunk import LOCK_FILE
        assert LOCK_FILE.exists(), "Lock file not created by first process"
        lock_pid = int(LOCK_FILE.read_text().strip())
        assert lock_pid == proc1.pid, \
            f"Lock PID {lock_pid} != proc1 PID {proc1.pid}"

        # Start second transcription — should be blocked
        proc2 = subprocess.run(
            ["python3", str(SCRIPTS_DIR / "transcribe_chunk.py"), "--all", video_id],
            capture_output=True, text=True, timeout=10
        )

        # Second process should exit quickly with already_running error
        assert proc2.returncode == 0, \
            "Second process should exit cleanly (not error code) when blocked by lock"

        output2 = json.loads(proc2.stdout.strip())
        assert output2.get("error") == "already_running", \
            f"Second process should return 'already_running', got: {output2}"

        # Verify only ONE whisper process is running
        pgrep_result = subprocess.run(
            ["pgrep", "-c", "-f", "transcribe_chunk"],
            capture_output=True, text=True, timeout=5
        )
        whisper_count = int(pgrep_result.stdout.strip()) if pgrep_result.returncode == 0 else 0
        assert whisper_count <= 1, \
            f"Expected <=1 transcribe_chunk process, found {whisper_count}"

        # Clean up: kill proc1 and wait
        proc1.kill()
        proc1.wait(timeout=10)
        release_lock()

    def test_hermes_processor_lock_prevents_parallel(self):
        """Hermes queue processor PID-lock prevents parallel pipeline runs."""
        from hermes_queue_processor import acquire_lock, release_lock, LOCK_FILE

        release_lock()

        assert acquire_lock(), "First acquire failed"
        assert not acquire_lock(), "Second acquire should fail"

        release_lock()
        assert not LOCK_FILE.exists(), "Lock not cleaned"