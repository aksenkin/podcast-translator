#!/usr/bin/env python3
"""
Transcribe audio file using faster-whisper (CACHED VERSION - CLI-OPTIMIZED)

- Checks if model exists in cache before downloading
- Uses explicit cache directory
- Machine-readable progress output for CLI agents
- CPU-optimized settings
"""

import sys
import os
import time
from pathlib import Path

# Disable proxy (faster download)
os.environ.pop('ALL_PROXY', None)
os.environ.pop('all_proxy', None)
os.environ.pop('http_proxy', None)
os.environ.pop('https_proxy', None)

# Model cache directory
CACHE_DIR = Path.home() / ".cache" / "huggingface" / "hub"
MODEL_DIR = CACHE_DIR / "models--Systran--faster-whisper"

try:
    from faster_whisper import WhisperModel
except ImportError:
    print("Error: faster-whisper not found")
    print("Installing...")
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "faster-whisper", "--break-system-packages"])
    print("Please run this script again after installation")
    sys.exit(1)

def check_model_cached(model_size):
    """Check if model is already downloaded and cached"""
    # faster-whisper models are stored in:
    # ~/.cache/huggingface/hub/models--Systran--faster-whisper-{size}/
    model_name = f"models--Systran--faster-whisper-{model_size}"
    model_path = CACHE_DIR / model_name

    if model_path.exists() and (model_path / "snapshots").exists():
        snapshots = list((model_path / "snapshots").iterdir())
        if snapshots:
            return True, snapshots[0]
    return False, None

class ProgressReporter:
    """Machine-readable progress output for CLI agents"""

    def __init__(self):
        self.last_heartbeat = time.time()
        self.heartbeat_interval = 10  # seconds
        self.segments_processed = 0
        self.estimated_total = 0

    def heartbeat(self, message: str = ""):
        """Print heartbeat every 10 seconds so CLI agent knows process is alive"""
        now = time.time()
        if now - self.last_heartbeat >= self.heartbeat_interval:
            if self.estimated_total > 0:
                progress = min(100, (self.segments_processed / self.estimated_total) * 100)
                print(f"HEARTBEAT: {progress:.1f}% | segments: {self.segments_processed} | {message}", flush=True)
            else:
                print(f"HEARTBEAT: processing segment {self.segments_processed} | {message}", flush=True)
            self.last_heartbeat = now

    def status(self, message: str):
        """Print status update"""
        print(f"STATUS: {message}", flush=True)

    def error(self, message: str):
        """Print error"""
        print(f"ERROR: {message}", flush=True)

    def success(self, message: str):
        """Print success"""
        print(f"SUCCESS: {message}", flush=True)


def transcribe_audio(audio_file, output_dir, model_size="small"):
    """Transcribe audio using faster-whisper (CPU-optimized)"""

    reporter = ProgressReporter()

    # Check if model is cached
    is_cached, model_path = check_model_cached(model_size)

    if is_cached:
        reporter.status(f"Using cached model: {model_size}")
    else:
        reporter.status(f"Downloading Whisper model ({model_size}) from HuggingFace...")

    try:
        # Load model (will download if not cached)
        # CPU-optimized: int8 quantization, no GPU
        model = WhisperModel(
            model_size,
            device="cpu",
            compute_type="int8",
            download_root=str(CACHE_DIR),
            # CPU threads optimization for 4-core ARM
            cpu_threads=4,
            num_workers=2
        )
    except Exception as e:
        reporter.error(f"Failed to load model: {e}")
        return None

    reporter.status(f"Starting transcription: {audio_file}")

    # Get audio duration first for better progress estimation
    try:
        import subprocess
        result = subprocess.run([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", audio_file
        ], capture_output=True, text=True, timeout=30)
        duration = float(result.stdout.strip())
        # Rough estimate: ~1 segment per 2 seconds of audio
        reporter.estimated_total = max(1, int(duration / 2))
        reporter.status(f"Audio duration: {duration:.1f}s, estimated segments: {reporter.estimated_total}")
    except:
        reporter.estimated_total = 100  # fallback
        reporter.status("Could not get duration, using default estimate")

    try:
        # CPU-optimized transcription settings
        segments, info = model.transcribe(
            audio_file,
            # CPU optimization: lower beam size = faster
            beam_size=1,
            # Disable VAD for speed (can be enabled if needed)
            vad_filter=False,
            # No word timestamps for speed
            word_timestamps=False,
            # Language detection is fine
            language=None
        )
    except Exception as e:
        reporter.error(f"Error during transcription: {e}")
        return None

    # Check if transcription succeeded
    if not info:
        reporter.error("Transcription failed - no info object")
        return None

    reporter.status(f"Language detected: {info.language}, duration: {info.duration:.1f}s")

    # Save full transcript
    transcript_file = os.path.join(
        output_dir,
        os.path.basename(audio_file).replace('.mp3', '.txt').replace('.webm', '.txt')
    )

    with open(transcript_file, 'w', encoding='utf-8') as f:
        for segment in segments:
            reporter.segments_processed += 1

            start_time = segment.start
            end_time = segment.end
            text = segment.text

            # Format timestamp
            minutes_start = int(start_time // 60)
            seconds_start = int(start_time % 60)
            minutes_end = int(end_time // 60)
            seconds_end = int(end_time % 60)

            f.write(f"[{minutes_start:02d}:{seconds_start:02d} - {minutes_end:02d}:{seconds_end:02d}] {text}\n")

            # Send heartbeat every segment for long transcriptions
            reporter.heartbeat(f"current time: {minutes_start:02d}:{seconds_start:02d}")

            # Progress update every 10 segments
            if reporter.segments_processed % 10 == 0:
                if reporter.estimated_total > 0:
                    progress = min(100, (reporter.segments_processed / reporter.estimated_total) * 100)
                    reporter.status(f"Progress: {reporter.segments_processed} segments (~{progress:.1f}%)")
                else:
                    reporter.status(f"Progress: {reporter.segments_processed} segments")

    reporter.success(f"Transcript saved: {transcript_file}")
    reporter.status(f"Duration: {info.duration:.2f}s, Language: {info.language}, Segments: {reporter.segments_processed}")

    return transcript_file

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 transcribe_cached.py <audio_file> <output_dir> [model_size]")
        print("")
        print("Example:")
        print("  python3 transcribe_cached.py audio.mp3 transcripts/ small")
        print("")
        print("Model sizes: tiny, base, small, medium, large-v3")
        print("")
        print("CLI Output Format:")
        print("  STATUS: <message>      - Status updates")
        print("  HEARTBEAT: X% | ...    - Progress heartbeat every 10s")
        print("  SUCCESS: <message>     - Transcription completed")
        print("  ERROR: <message>       - Error occurred")
        print("")
        print("Exit codes: 0 = success, 1 = error")
        sys.exit(1)

    audio_file = sys.argv[1]
    output_dir = sys.argv[2]
    model_size = sys.argv[3] if len(sys.argv) > 3 else "small"

    result = transcribe_audio(audio_file, output_dir, model_size)

    if result:
        sys.exit(0)
    else:
        sys.exit(1)
