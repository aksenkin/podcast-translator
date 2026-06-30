#!/usr/bin/env python3
"""
Test environment setup and dependencies.

Verifies that all required tools and Python packages are installed
before running pipeline tests.
"""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import (
    PROJECT_DIR, SCRIPTS_DIR, INPUT_DIR, TRANSCRIPTS_DIR,
    TRANSLATIONS_DIR, AUDIO_DIR, CHUNKS_DIR, LOGS_DIR
)


# ─── Binary Dependencies ─────────────────────────────────────────────────────

class TestBinaries:
    """Check that required command-line tools are installed."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.required_bins = ["yt-dlp", "ffmpeg", "ffprobe", "python3"]

    def test_yt_dlp_installed(self):
        assert shutil.which("yt-dlp"), "yt-dlp not found in PATH"

    def test_ffmpeg_installed(self):
        assert shutil.which("ffmpeg"), "ffmpeg not found in PATH"

    def test_ffprobe_installed(self):
        assert shutil.which("ffprobe"), "ffprobe not found in PATH"

    def test_python3_installed(self):
        assert shutil.which("python3"), "python3 not found in PATH"

    def test_all_bins_at_once(self):
        """Quick check all binaries in one test."""
        missing = [b for b in self.required_bins if not shutil.which(b)]
        assert not missing, f"Missing binaries: {missing}"


# ─── Python Dependencies ────────────────────────────────────────────────────

class TestPythonPackages:
    """Check that required Python packages are installed."""

    def test_faster_whisper(self):
        from faster_whisper import WhisperModel
        assert WhisperModel is not None

    def test_edge_tts(self):
        from edge_tts import Communicate
        assert Communicate is not None

    def test_deep_translator(self):
        from deep_translator import GoogleTranslator
        assert GoogleTranslator is not None

    def test_ctranslate2(self):
        """faster-whisper backend — ctranslate2."""
        import ctranslate2
        assert ctranslate2 is not None


# ─── Directory Structure ────────────────────────────────────────────────────

class TestDirectories:
    """Check that project directories exist."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.expected_dirs = [
            SCRIPTS_DIR,
            INPUT_DIR,
            TRANSCRIPTS_DIR,
            TRANSLATIONS_DIR,
            AUDIO_DIR,
            CHUNKS_DIR,
            LOGS_DIR,
        ]

    def test_project_dir_exists(self):
        assert PROJECT_DIR.exists(), f"Project dir not found: {PROJECT_DIR}"

    def test_scripts_dir_exists(self):
        assert SCRIPTS_DIR.exists(), f"Scripts dir not found: {SCRIPTS_DIR}"

    def test_all_dirs_exist(self):
        for d in self.expected_dirs:
            assert d.exists(), f"Directory not found: {d}"

    def test_all_dirs_writable(self):
        """Ensure we can write to output directories."""
        for d in self.expected_dirs:
            test_file = d / ".write_test"
            try:
                test_file.write_text("test")
                test_file.unlink()
            except OSError as e:
                pytest.fail(f"Cannot write to {d}: {e}")


# ─── Script Files ────────────────────────────────────────────────────────────

class TestScripts:
    """Check that all required scripts exist."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.required_scripts = [
            "chunk_audio.py",
            "transcribe_cached.py",
            "transcribe_chunk.py",
            "assemble_chunks.py",
            "prepare_transcript.py",
            "generate_tts.py",
            "extract_tts_text.py",
            "log_helper.py",
        ]
        self.required_modules = [
            "queue_manager.py",
            "channel_monitor.py",
            "hermes_queue_processor.py",
            "run_pipeline.py",
        ]

    def test_all_scripts_exist(self):
        for name in self.required_scripts:
            path = SCRIPTS_DIR / name
            assert path.exists(), f"Script not found: {path}"

    def test_all_modules_exist(self):
        for name in self.required_modules:
            path = PROJECT_DIR / name
            assert path.exists(), f"Module not found: {path}"

    def test_scripts_are_python(self):
        """Verify scripts are valid Python."""
        import ast
        for name in self.required_scripts:
            path = SCRIPTS_DIR / name
            with open(path) as f:
                try:
                    ast.parse(f.read())
                except SyntaxError as e:
                    pytest.fail(f"Syntax error in {name}: {e}")

    def test_modules_are_python(self):
        """Verify modules are valid Python."""
        import ast
        for name in self.required_modules:
            path = PROJECT_DIR / name
            with open(path) as f:
                try:
                    ast.parse(f.read())
                except SyntaxError as e:
                    pytest.fail(f"Syntax error in {name}: {e}")


# ─── No os.nice(10) ──────────────────────────────────────────────────────────

class TestNoNice10:
    """Ensure os.nice(10) is not used — it freezes whisper on 4-core RPi."""

    def test_no_nice_in_hermes_processor(self):
        content = (PROJECT_DIR / "hermes_queue_processor.py").read_text()
        assert "os.nice(10)" not in content, \
            "os.nice(10) found in hermes_queue_processor.py — this freezes whisper on RPi!"

    def test_no_nice_in_transcribe_chunk(self):
        content = (SCRIPTS_DIR / "transcribe_chunk.py").read_text()
        assert "os.nice(10)" not in content, \
            "os.nice(10) found in transcribe_chunk.py — this freezes whisper on RPi!"

    def test_no_nice_in_transcribe_cached(self):
        content = (SCRIPTS_DIR / "transcribe_cached.py").read_text()
        assert "os.nice(10)" not in content, \
            "os.nice(10) found in transcribe_cached.py — this freezes whisper on RPi!"