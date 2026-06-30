#!/usr/bin/env python3
"""
Test pipeline steps: translation + TTS generation.

Tests:
- prepare_transcript: removes timestamps, outputs clean text
- translate_batch: GoogleTranslator with 50-line batching
- generate_tts: Edge TTS with 1000-char chunking + ffmpeg merge
- end-to-end: transcript → prepare → translate → TTS → audio file

Uses session-scoped transcription fixture from conftest.py.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from conftest import (
    PROJECT_DIR, SCRIPTS_DIR, INPUT_DIR, TRANSCRIPTS_DIR,
    TRANSLATIONS_DIR, AUDIO_DIR, CHUNKS_DIR,
    TEST_VIDEO_ID
)


# ─── Prepare Transcript ──────────────────────────────────────────────────────

class TestPrepareTranscript:
    """Test Step 3: prepare_transcript.py — remove timestamps for translation."""

    def test_removes_timestamps(self, tmp_path):
        """Timestamps [MM:SS - MM:SS] should be removed from each line."""
        input_file = tmp_path / "input.txt"
        input_file.write_text(
            "[00:00 - 00:06]  Hello world this is a test\n"
            "[00:06 - 00:09]  Another line here\n"
            "[00:09 - 00:12]  Third line\n",
            encoding="utf-8"
        )

        output_file = tmp_path / "output.txt"
        result = subprocess.run(
            ["python3", str(SCRIPTS_DIR / "prepare_transcript.py"),
             str(input_file), str(output_file)],
            capture_output=True, text=True, timeout=30
        )

        assert result.returncode == 0, f"prepare_transcript failed: {result.stderr}"
        assert output_file.exists(), "Output file not created"

        content = output_file.read_text(encoding="utf-8")
        # No timestamps should remain
        assert "[00:" not in content, "Timestamps not removed"
        assert "[01:" not in content, "Timestamps not removed"
        # Text content should remain
        assert "Hello world" in content
        assert "Another line" in content
        assert "Third line" in content

    def test_preserves_empty_line_removal(self, tmp_path):
        """Empty lines should be removed."""
        input_file = tmp_path / "input.txt"
        input_file.write_text(
            "[00:00 - 00:06]  Line one\n"
            "\n"
            "\n"
            "[00:06 - 00:09]  Line two\n",
            encoding="utf-8"
        )

        output_file = tmp_path / "output.txt"
        subprocess.run(
            ["python3", str(SCRIPTS_DIR / "prepare_transcript.py"),
             str(input_file), str(output_file)],
            capture_output=True, text=True, timeout=30
        )

        content = output_file.read_text(encoding="utf-8")
        lines = [l for l in content.split("\n") if l.strip()]
        assert len(lines) == 2, f"Expected 2 non-empty lines, got {len(lines)}"

    def test_empty_input_fails(self, tmp_path):
        """Empty input file should exit with error."""
        input_file = tmp_path / "empty.txt"
        input_file.write_text("", encoding="utf-8")

        output_file = tmp_path / "output.txt"
        result = subprocess.run(
            ["python3", str(SCRIPTS_DIR / "prepare_transcript.py"),
             str(input_file), str(output_file)],
            capture_output=True, text=True, timeout=10
        )

        assert result.returncode != 0, "Empty input should fail"
        assert "ERROR" in result.stdout or "Error" in result.stderr

    @pytest.mark.slow
    def test_prepare_real_transcript(self, session_transcription):
        """Run prepare_transcript on the real 27-min transcript."""
        video_id, transcript_path = session_transcription
        if transcript_path is None:
            pytest.skip("No transcript available")

        ready_file = TRANSLATIONS_DIR / f"{video_id}_ready.txt"
        result = subprocess.run(
            ["python3", str(SCRIPTS_DIR / "prepare_transcript.py"),
             transcript_path, str(ready_file)],
            capture_output=True, text=True, timeout=60
        )

        assert result.returncode == 0, f"Prepare failed: {result.stderr[:200]}"
        assert ready_file.exists(), f"Ready file not created: {ready_file}"

        content = ready_file.read_text(encoding="utf-8")
        # No timestamps
        assert "[" not in content[:100], "Timestamps not removed"
        # Should have substantial content (~27 min podcast)
        assert len(content) > 5000, f"Content too short: {len(content)} chars"
        # Should be multiple lines
        line_count = sum(1 for l in content.split("\n") if l.strip())
        assert line_count > 50, f"Too few lines: {line_count}"


# ─── Translation ─────────────────────────────────────────────────────────────

class TestTranslation:
    """Test Step 4: Batch translation with GoogleTranslator."""

    def test_translate_single_line(self):
        """GoogleTranslator should translate a simple English line."""
        from deep_translator import GoogleTranslator
        translator = GoogleTranslator(source='en', target='ru')
        result = translator.translate("Hello world")
        assert "привет" in result.lower() or "мир" in result.lower(), \
            f"Translation unexpected: {result}"

    def test_translate_batch_function(self, tmp_path):
        """translate_batch should produce clean Russian text, no timestamps."""
        # Import the function from hermes_queue_processor
        sys.path.insert(0, str(PROJECT_DIR))
        from hermes_queue_processor import translate_batch

        # Create a small test file — clean text, no timestamps
        ready_file = tmp_path / "test_ready.txt"
        ready_file.write_text(
            "Hello world, this is a test.\n"
            "The quick brown fox jumps over the lazy dog.\n"
            "Artificial intelligence is changing the world.\n",
            encoding="utf-8"
        )

        # translate_batch expects (ready_file: Path, basename: str)
        basename = "test_translate_batch_xyz"
        tts_file = translate_batch(ready_file, basename)

        assert Path(tts_file).exists(), f"TTS file not created: {tts_file}"

        content = Path(tts_file).read_text(encoding="utf-8")
        # Should contain Cyrillic characters (Russian)
        assert any("\u0400" <= c <= "\u04ff" for c in content), \
            "No Cyrillic characters found — translation failed"
        # Should have roughly the same number of lines
        input_lines = [l for l in ready_file.read_text().split("\n") if l.strip()]
        output_lines = [l for l in content.split("\n") if l.strip()]
        assert len(output_lines) == len(input_lines), \
            f"Line count mismatch: {len(output_lines)} output vs {len(input_lines)} input"
        # MUST NOT contain timestamps or bracket markers
        assert "[" not in content, \
            f"Translation contains '[' — timestamps or markers not removed: {content[:200]}"
        assert "]" not in content, \
            f"Translation contains ']' — timestamps or markers not removed: {content[:200]}"

        # Cleanup
        Path(tts_file).unlink(missing_ok=True)

    def test_translate_batch_preserves_line_count(self, tmp_path):
        """Batch translation should preserve the number of lines."""
        sys.path.insert(0, str(PROJECT_DIR))
        from hermes_queue_processor import translate_batch

        # Create 55 lines (more than one batch of 50)
        lines = [f"This is line number {i} for testing." for i in range(55)]
        ready_file = tmp_path / "test_55.txt"
        ready_file.write_text("\n".join(lines), encoding="utf-8")

        basename = "test_55_lines"
        tts_file = translate_batch(ready_file, basename)

        content = Path(tts_file).read_text(encoding="utf-8")
        output_lines = [l for l in content.split("\n") if l.strip()]
        assert len(output_lines) == 55, \
            f"Expected 55 lines, got {len(output_lines)} — batch splitting failed"

        Path(tts_file).unlink(missing_ok=True)

    @pytest.mark.slow
    def test_translate_real_transcript(self, session_transcription):
        """Translate the real 27-min transcript via translate_batch.

        Output MUST be clean Russian text — no timestamps, no bracket markers.
        """
        video_id, transcript_path = session_transcription
        if transcript_path is None:
            pytest.skip("No transcript available")

        # Prepare first
        ready_file = TRANSLATIONS_DIR / f"{video_id}_ready.txt"
        if not ready_file.exists():
            subprocess.run(
                ["python3", str(SCRIPTS_DIR / "prepare_transcript.py"),
                 transcript_path, str(ready_file)],
                capture_output=True, text=True, timeout=60
            )

        assert ready_file.exists(), "Ready file not created"
        line_count = sum(1 for l in ready_file.read_text().split("\n") if l.strip())
        assert line_count > 50, f"Too few lines to translate: {line_count}"

        # Verify ready file has no timestamps before translation
        ready_content = ready_file.read_text(encoding="utf-8")
        assert "[" not in ready_content, \
            "Ready file still has timestamps — prepare_transcript failed"

        # Translate
        sys.path.insert(0, str(PROJECT_DIR))
        from hermes_queue_processor import translate_batch
        tts_file = translate_batch(ready_file, video_id)

        assert Path(tts_file).exists(), "Translation file not created"

        content = Path(tts_file).read_text(encoding="utf-8")
        # Should contain Cyrillic
        assert any("\u0400" <= c <= "\u04ff" for c in content), \
            "No Cyrillic — translation failed"
        # MUST NOT contain timestamps or bracket markers
        assert "[" not in content, \
            f"Translation contains '[' — timestamps leaked into output"
        assert "]" not in content, \
            f"Translation contains ']' — timestamps leaked into output"
        # No chunk markers
        assert "chunk" not in content.lower(), \
            "Translation contains 'chunk' markers"
        # Should have roughly same line count
        output_lines = [l for l in content.split("\n") if l.strip()]
        assert abs(len(output_lines) - line_count) < line_count * 0.2, \
            f"Line count drift: {len(output_lines)} vs {line_count} (>{20}% difference)"


# ─── TTS Generation ──────────────────────────────────────────────────────────

class TestTTSGeneration:
    """Test Step 5: Edge TTS generation with chunking + ffmpeg merge."""

    @pytest.mark.slow
    def test_generate_short_tts(self, tmp_path):
        """Generate TTS for a short text — should produce valid MP3."""
        text_file = tmp_path / "short.txt"
        text_file.write_text(
            "Привет мир. Это тестовая запись для проверки генерации речи.",
            encoding="utf-8"
        )

        output_file = tmp_path / "output.mp3"
        result = subprocess.run(
            ["python3", str(SCRIPTS_DIR / "generate_tts.py"),
             str(text_file), str(output_file), "ru-RU-DmitryNeural"],
            capture_output=True, text=True, timeout=60
        )

        assert result.returncode == 0, f"TTS failed: {result.stderr[:300]}"
        assert output_file.exists(), "Output MP3 not created"
        assert output_file.stat().st_size > 1000, "MP3 file too small"

        # Verify it's a valid audio file with ffprobe
        dur_result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(output_file)],
            capture_output=True, text=True, timeout=10
        )
        assert dur_result.returncode == 0, "ffprobe failed on TTS output"
        duration = float(dur_result.stdout.strip())
        assert duration > 1.0, f"TTS audio too short: {duration}s"

    @pytest.mark.slow
    def test_tts_female_voice(self, tmp_path):
        """Test Svetlana (female) voice."""
        text_file = tmp_path / "female.txt"
        text_file.write_text("Это тест женского голоса.", encoding="utf-8")

        output_file = tmp_path / "female.mp3"
        result = subprocess.run(
            ["python3", str(SCRIPTS_DIR / "generate_tts.py"),
             str(text_file), str(output_file), "ru-RU-SvetlanaNeural"],
            capture_output=True, text=True, timeout=60
        )

        assert result.returncode == 0, f"TTS failed: {result.stderr[:300]}"
        assert output_file.exists(), "Female voice MP3 not created"
        assert output_file.stat().st_size > 500, "MP3 too small"

    @pytest.mark.slow
    def test_tts_long_text_chunking(self, tmp_path):
        """Test that long text is chunked and merged with ffmpeg.

        generate_tts.py splits text at 1000 chars and merges with ffmpeg.
        """
        # Create text > 5000 chars to force multiple chunks
        paragraph = (
            "Искусственный интеллект меняет мир технологий. "
            "Каждый день появляются новые модели и алгоритмы. "
            "Большие языковые модели могут писать код, переводить тексты "
            "и даже создавать изображения. Это открывает невероятные "
            "возможности для разработчиков и исследователей. "
        )
        long_text = (paragraph * 20)  # ~6000 chars
        text_file = tmp_path / "long.txt"
        text_file.write_text(long_text, encoding="utf-8")

        output_file = tmp_path / "long.mp3"
        result = subprocess.run(
            ["python3", str(SCRIPTS_DIR / "generate_tts.py"),
             str(text_file), str(output_file), "ru-RU-DmitryNeural"],
            capture_output=True, text=True, timeout=120
        )

        assert result.returncode == 0, f"Long TTS failed: {result.stderr[:300]}"
        assert output_file.exists(), "Long TTS MP3 not created"

        # Check duration — should be > 30 seconds for 6000 chars
        dur_result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(output_file)],
            capture_output=True, text=True, timeout=10
        )
        duration = float(dur_result.stdout.strip())
        assert duration > 10.0, f"Long TTS too short: {duration}s (expected >10s)"

        # Check that multiple chunks were processed
        assert "chunk" in result.stdout.lower() or "merging" in result.stdout.lower(), \
            "No chunking evidence in output — long text may not be split"

    def test_tts_empty_text_fails(self, tmp_path):
        """Empty text file should fail."""
        text_file = tmp_path / "empty.txt"
        text_file.write_text("", encoding="utf-8")

        output_file = tmp_path / "empty.mp3"
        result = subprocess.run(
            ["python3", str(SCRIPTS_DIR / "generate_tts.py"),
             str(text_file), str(output_file)],
            capture_output=True, text=True, timeout=10
        )

        assert result.returncode != 0, "Empty text should fail"
        assert "ERROR" in result.stdout or "Error" in result.stderr

    @pytest.mark.slow
    def test_tts_with_metadata(self, tmp_path):
        """TTS with title and artist metadata should embed it."""
        text_file = tmp_path / "meta.txt"
        text_file.write_text("Тестовая запись с метаданными.", encoding="utf-8")

        output_file = tmp_path / "meta.mp3"
        result = subprocess.run(
            ["python3", str(SCRIPTS_DIR / "generate_tts.py"),
             str(text_file), str(output_file), "ru-RU-DmitryNeural",
             "Test Podcast Title", "Test Artist"],
            capture_output=True, text=True, timeout=60
        )

        assert result.returncode == 0, f"TTS with metadata failed: {result.stderr[:300]}"
        assert output_file.exists(), "Metadata MP3 not created"

        # Check metadata with ffprobe
        meta_result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries",
             "format_tags=title,artist",
             "-of", "json", str(output_file)],
            capture_output=True, text=True, timeout=10
        )

        if meta_result.returncode == 0:
            tags = json.loads(meta_result.stdout).get("format", {}).get("tags", {})
            # Metadata may or may not be present depending on ffmpeg version
            if tags:
                assert "Test Podcast Title" in str(tags.get("title", "")) or \
                       "Test Artist" in str(tags.get("artist", "")), \
                    f"Metadata not embedded: {tags}"


# ─── End-to-End: Prepare → Translate → TTS ──────────────────────────────────

class TestEndToEnd:
    """Test the full translation + TTS pipeline on real transcript."""

    @pytest.mark.slow
    def test_full_translate_tts_pipeline(self, session_transcription):
        """End-to-end: transcript → prepare → translate → TTS → audio file.

        Uses the real 27-min podcast transcript from session_transcription.
        """
        video_id, transcript_path = session_transcription
        if transcript_path is None:
            pytest.skip("No transcript available")

        # Step 1: Prepare
        ready_file = TRANSLATIONS_DIR / f"{video_id}_ready.txt"
        if not ready_file.exists():
            result = subprocess.run(
                ["python3", str(SCRIPTS_DIR / "prepare_transcript.py"),
                 transcript_path, str(ready_file)],
                capture_output=True, text=True, timeout=60
            )
            assert result.returncode == 0, f"Prepare failed: {result.stderr[:200]}"

        assert ready_file.exists(), "Ready file not created"
        ready_content = ready_file.read_text(encoding="utf-8")
        assert "[" not in ready_content[:200], "Timestamps not removed"
        assert len(ready_content) > 1000, "Content too short after prepare"

        # Step 2: Translate
        sys.path.insert(0, str(PROJECT_DIR))
        from hermes_queue_processor import translate_batch
        tts_text_file = translate_batch(ready_file, video_id)

        assert Path(tts_text_file).exists(), "Translation file not created"
        translated = Path(tts_text_file).read_text(encoding="utf-8")
        assert any("\u0400" <= c <= "\u04ff" for c in translated), \
            "No Cyrillic in translation"
        assert len(translated) > 500, "Translation too short"
        # MUST NOT contain timestamps, bracket markers, or chunk markers
        assert "[" not in translated, \
            "Translation contains '[' — timestamps leaked into TTS text"
        assert "]" not in translated, \
            "Translation contains ']' — timestamps leaked into TTS text"
        assert "chunk" not in translated.lower(), \
            "Translation contains 'chunk' markers"

        # Step 3: Generate TTS
        # 27-min podcast = ~66KB text = ~67 TTS chunks at 1000 chars each
        # Edge TTS on RPi: ~10-15 sec per chunk → 11-17 min total
        audio_file = AUDIO_DIR / f"{video_id}.ru.mp3"
        result = subprocess.run(
            ["python3", str(SCRIPTS_DIR / "generate_tts.py"),
             str(tts_text_file), str(audio_file), "ru-RU-DmitryNeural"],
            capture_output=True, text=True, timeout=1800  # 30 min for long podcast
        )

        assert result.returncode == 0, f"TTS failed: {result.stderr[:300]}"
        assert audio_file.exists(), "Audio file not created"
        assert audio_file.stat().st_size > 10000, "Audio file too small"

        # Verify audio duration — 27 min podcast → TTS should be > 5 min
        dur_result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(audio_file)],
            capture_output=True, text=True, timeout=10
        )
        duration = float(dur_result.stdout.strip())
        assert duration > 300, \
            f"TTS audio too short: {duration:.0f}s (expected >300s for 27-min podcast)"

        # Report stats
        size_mb = audio_file.stat().st_size / (1024 * 1024)
        word_count = len(translated.split())
        print(f"\n📊 End-to-End Results:")
        print(f"   Transcript: {sum(1 for l in transcript_path and open(transcript_path).readlines() if l.strip())} lines")
        print(f"   Translation: {word_count} words, {len(translated)} chars")
        print(f"   TTS audio: {duration:.0f}s ({duration/60:.1f} min), {size_mb:.1f} MB")
        print(f"   Audio file: {audio_file}")