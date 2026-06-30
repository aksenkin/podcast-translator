#!/usr/bin/env python3
"""
Test configuration and fixtures for podcast-translator.

Provides:
- Path fixtures (SKILL_DIR, SCRIPTS_DIR, etc.)
- Test video fixture (short YouTube video for pipeline testing)
- Queue cleanup fixture
"""

import json
import os
import shutil
import sys
from pathlib import Path

import pytest

# ─── Paths ────────────────────────────────────────────────────────────────────

PROJECT_DIR = Path(__file__).parent.parent
SCRIPTS_DIR = PROJECT_DIR / "scripts"
INPUT_DIR = PROJECT_DIR / "input"
TRANSCRIPTS_DIR = PROJECT_DIR / "transcripts"
TRANSLATIONS_DIR = PROJECT_DIR / "translations"
AUDIO_DIR = PROJECT_DIR / "audio"
CHUNKS_DIR = PROJECT_DIR / "chunks"
LOGS_DIR = PROJECT_DIR / "logs"
QUEUE_FILE = PROJECT_DIR / "youtube-queue.json"

# Add project dir to sys.path so we can import project modules
sys.path.insert(0, str(PROJECT_DIR))


# ─── Test Video ──────────────────────────────────────────────────────────────

# Test video: ~27 min, English podcast — tests full pipeline including chunking
# "Should We Be Scared of Anthropic's Mythos?" by AIDailyBrief
TEST_VIDEO_URL = "https://www.youtube.com/watch?v=_E7XMiVomJA"
TEST_VIDEO_ID = "_E7XMiVomJA"
TEST_VIDEO_TITLE = "Should We Be Scared of Anthropic's Mythos?"
TEST_VIDEO_DURATION_SEC = 1644  # ~27.4 min


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def project_dir():
    """Project root directory."""
    return PROJECT_DIR


@pytest.fixture
def scripts_dir():
    """Scripts directory."""
    return SCRIPTS_DIR


@pytest.fixture
def test_video_url():
    """Short YouTube video URL for testing (~30 sec)."""
    return TEST_VIDEO_URL


@pytest.fixture
def test_video_id():
    """YouTube video ID for testing."""
    return TEST_VIDEO_ID


@pytest.fixture
def clean_queue():
    """Clean queue before and after test. Returns QueueManager instance."""
    from queue_manager import QueueManager

    qm = QueueManager(QUEUE_FILE)

    # Save original queue state
    original = qm._load_queue()

    # Reset to empty
    qm._save_queue({
        "pending": [],
        "processing": None,
        "completed": [],
        "failed": []
    })

    yield qm

    # Restore original state
    qm._save_queue(original)


@pytest.fixture
def clean_dirs():
    """Clean output directories before test. Restores after."""
    dirs_to_clean = [TRANSCRIPTS_DIR, TRANSLATIONS_DIR, AUDIO_DIR, CHUNKS_DIR]

    saved = {}
    for d in dirs_to_clean:
        if d.exists():
            saved[d] = list(d.iterdir())
            # Move files to temp subdirectory
            tmp = d / "_test_backup"
            tmp.mkdir(exist_ok=True)
            for f in saved[d]:
                if f.is_file() and f.name != ".gitkeep":
                    shutil.move(str(f), str(tmp / f.name))
        else:
            saved[d] = []
            d.mkdir(parents=True, exist_ok=True)

    yield

    # Restore: remove test-generated files, move backups back
    for d in dirs_to_clean:
        if d.exists():
            # Remove test-generated files (except .gitkeep and backup)
            for f in d.iterdir():
                if f.name not in (".gitkeep", "_test_backup"):
                    if f.is_file():
                        f.unlink()
                    elif f.is_dir():
                        shutil.rmtree(f)

            # Restore backups
            tmp = d / "_test_backup"
            if tmp.exists():
                for f in tmp.iterdir():
                    shutil.move(str(f), str(d / f.name))
                tmp.rmdir()


@pytest.fixture(scope="session")
def session_audio_file():
    """Download test audio ONCE per session. Returns path to MP3.

    ~30-60 sec download. Shared across all whisper tests.
    """
    import subprocess

    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = INPUT_DIR / f"test_{TEST_VIDEO_ID}.mp3"

    # Skip if already downloaded from a previous test
    existing = list(INPUT_DIR.glob(f"test_{TEST_VIDEO_ID}.*"))
    if existing:
        yield str(existing[0])
        return

    result = subprocess.run(
        [
            "yt-dlp",
            "-x", "--audio-format", "mp3", "--audio-quality", "0",
            "-o", str(output_path),
            TEST_VIDEO_URL
        ],
        capture_output=True, text=True, timeout=120
    )

    if result.returncode != 0:
        pytest.skip(f"Failed to download test video: {result.stderr[:200]}")

    downloaded = list(INPUT_DIR.glob(f"test_{TEST_VIDEO_ID}.*"))
    if not downloaded:
        pytest.skip("Downloaded file not found")

    yield str(downloaded[0])


@pytest.fixture(scope="session")
def session_chunks(session_audio_file):
    """Create chunks ONCE per session. Returns (video_id, chunks_meta).

    ~10 sec. Reuses session_audio_file.
    """
    import subprocess

    video_id = Path(session_audio_file).stem
    chunks_json = CHUNKS_DIR / f"{video_id}_chunks.json"

    # Skip if chunks already exist from previous run
    if chunks_json.exists():
        meta = json.loads(chunks_json.read_text())
        # Check all chunks are transcribed
        if all(c["status"] == "done" for c in meta["chunks"]):
            yield video_id, meta
            return

    # Create chunks
    result = subprocess.run(
        ["python3", str(SCRIPTS_DIR / "chunk_audio.py"), session_audio_file],
        capture_output=True, text=True, timeout=120
    )

    if result.returncode != 0:
        pytest.skip(f"chunk_audio.py failed: {result.stderr[:200]}")

    meta = json.loads(result.stdout)
    yield video_id, meta


@pytest.fixture(scope="session")
def session_transcription(session_chunks):
    """Transcribe all chunks ONCE per session. Returns (video_id, transcript_path).

    ~30 min on RPi (model load + 6 chunks). This is the slowest fixture.
    Reuses session_chunks.
    """
    import subprocess

    video_id, meta = session_chunks
    chunks_json = CHUNKS_DIR / f"{video_id}_chunks.json"

    # Check if transcription already complete
    current_meta = json.loads(chunks_json.read_text())
    if all(c["status"] == "done" for c in current_meta["chunks"]):
        # Already transcribed — check transcript file exists
        transcript = TRANSCRIPTS_DIR / f"{video_id}.txt"
        if not transcript.exists():
            # Need to assemble
            subprocess.run(
                ["python3", str(SCRIPTS_DIR / "assemble_chunks.py"), video_id],
                capture_output=True, text=True, timeout=120
            )
        yield video_id, str(transcript) if transcript.exists() else None
        return

    # Transcribe all chunks
    result = subprocess.run(
        ["python3", str(SCRIPTS_DIR / "transcribe_chunk.py"), "--all", video_id],
        capture_output=True, text=True, timeout=3600
    )

    if result.returncode != 0:
        pytest.skip(f"Transcription failed: {result.stderr[:300]}")

    # Assemble
    subprocess.run(
        ["python3", str(SCRIPTS_DIR / "assemble_chunks.py"), video_id],
        capture_output=True, text=True, timeout=120
    )

    transcript = TRANSCRIPTS_DIR / f"{video_id}.txt"
    yield video_id, str(transcript) if transcript.exists() else None