#!/bin/bash
# Download and process a specific YouTube video (FIXED - use transcribe_noproxy.py)

set -e

URL="$1"
EPISODE_NAME="podcast_$(date +%Y%m%d_%H%M%S)"

PROJECT_DIR="/home/clawd/work/podcast-translator"
INPUT_DIR="$PROJECT_DIR/input"
TRANSCRIPT_DIR="$PROJECT_DIR/transcripts"
TRANSLATION_DIR="$PROJECT_DIR/translations"
AUDIO_DIR="$PROJECT_DIR/audio"

echo "🎙️  Podcast Translation (FIXED v2)"
echo "========================================="
echo ""
echo "📋 URL: $URL"
echo "📂 Episode: $EPISODE_NAME"
echo ""

# Step 1: Download audio
echo "📹 Step 1: Downloading audio..."
yt-dlp -x --audio-format mp3 --audio-quality 0 -o "$INPUT_DIR/${EPISODE_NAME}.mp3" "$URL"

if [ ! -f "$INPUT_DIR/${EPISODE_NAME}.mp3" ]; then
    echo "❌ Failed to download audio"
    exit 1
fi
echo "✓ Audio downloaded: $INPUT_DIR/${EPISODE_NAME}.mp3"

# Step 2: Transcribe using MP3 (cached model)
echo ""
echo "🎤 Step 2: Transcribing (MP3, cached model)..."
python3 "$PROJECT_DIR/scripts/transcribe_cached.py" "$INPUT_DIR/${EPISODE_NAME}.mp3" "$TRANSCRIPT_DIR" "small"

TRANSCRIPT_FILE="$TRANSCRIPT_DIR/${EPISODE_NAME}.txt"

if [ ! -f "$TRANSCRIPT_FILE" ]; then
    echo "❌ Transcription failed"
    exit 1
fi
echo "✓ Transcript saved: $TRANSCRIPT_FILE"

# Step 3: Prepare for translation
echo ""
echo "🌍 Step 3: Preparing for AI translation..."
python3 "$PROJECT_DIR/scripts/prepare_transcript.py" "$TRANSCRIPT_FILE" "$TRANSLATION_DIR/${EPISODE_NAME}_ready.txt"

if [ ! -f "$TRANSLATION_DIR/${EPISODE_NAME}_ready.txt" ]; then
    echo "❌ Preparation failed"
    exit 1
fi
echo "✓ Ready for translation: $TRANSLATION_DIR/${EPISODE_NAME}_ready.txt"

# Step 4: Translate to Russian (use podcast-translator skill or translate manually)
echo ""
echo "🇷🇺 Step 4: Ready for translation!"
echo "   Use the podcast-translator skill or translate manually:"
echo "   Input:  $TRANSLATION_DIR/${EPISODE_NAME}_ready.txt"
echo "   Output: $TRANSLATION_DIR/${EPISODE_NAME}_ru.txt"
echo ""
echo "   After translation, press Enter to continue to TTS generation..."
read

if [ ! -f "$TRANSLATION_DIR/${EPISODE_NAME}_ru.txt" ]; then
    echo "❌ Translation failed"
    exit 1
fi
echo "✓ Translation saved: $TRANSLATION_DIR/${EPISODE_NAME}_ru.txt"

# Step 5: Generate TTS
echo ""
echo "🔊 Step 5: Generating Russian TTS..."
python3 "$PROJECT_DIR/scripts/generate_tts.py" "$TRANSLATION_DIR/${EPISODE_NAME}_ru.txt" "$AUDIO_DIR/${EPISODE_NAME}.ru.mp3"

if [ ! -f "$AUDIO_DIR/${EPISODE_NAME}.ru.mp3" ]; then
    echo "❌ TTS generation failed"
    exit 1
fi
echo "✓ Audio generated: $AUDIO_DIR/${EPISODE_NAME}.ru.mp3"

# Done
echo ""
echo "🎉 Complete!"
echo ""
echo "📂 Files created:"
echo "   - $INPUT_DIR/${EPISODE_NAME}.mp3"
echo "   - $TRANSCRIPT_DIR/${EPISODE_NAME}.txt"
echo "   - $TRANSLATION_DIR/${EPISODE_NAME}_ru.txt"
echo "   - $AUDIO_DIR/${EPISODE_NAME}.ru.mp3"
echo ""
echo "⏱️ Duration check:"
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$AUDIO_DIR/${EPISODE_NAME}.ru.mp3" 2>/dev/null || echo "Duration check skipped"
