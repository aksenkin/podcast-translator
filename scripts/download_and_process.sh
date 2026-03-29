#!/bin/bash
# Download and process a specific YouTube video
# Usage: ./download_and_process.sh [--destination-dir DIR] URL

set -e

# Parse arguments
DESTINATION_DIR=""
URL=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --destination-dir|-d)
            DESTINATION_DIR="$2"
            shift 2
            ;;
        -*)
            echo "❌ Unknown option: $1"
            echo "Usage: $0 [--destination-dir DIR] URL"
            exit 1
            ;;
        *)
            URL="$1"
            shift
            ;;
    esac
done

# Check if URL is provided
if [ -z "$URL" ]; then
    echo "❌ Error: URL is required"
    echo ""
    echo "Usage: $0 [--destination-dir DIR] URL"
    echo ""
    echo "Examples:"
    echo "  $0 \"https://www.youtube.com/watch?v=VIDEO_ID\""
    echo "  $0 --destination-dir /path/to/project \"https://www.youtube.com/watch?v=VIDEO_ID\""
    echo "  $0 -d ~/projects/podcast-translator \"https://www.youtube.com/watch?v=VIDEO_ID\""
    exit 1
fi

EPISODE_NAME="podcast_$(date +%Y%m%d_%H%M%S)"

# Determine PROJECT_DIR
if [ -n "$DESTINATION_DIR" ]; then
    PROJECT_DIR=$(cd "$DESTINATION_DIR" 2>/dev/null && pwd) || PROJECT_DIR="$DESTINATION_DIR"
elif [ -n "$PODCAST_TRANSLATOR_DIR" ]; then
    # Environment variable for CLI agents
    PROJECT_DIR="$PODCAST_TRANSLATOR_DIR"
elif [ -f "./scripts/transcribe_cached.py" ]; then
    # Current directory
    PROJECT_DIR="$(pwd)"
else
    # Prompt for destination directory
    echo "🎙️  Podcast Translation Pipeline"
    echo "==================================="
    echo ""
    echo "📍 Please specify the project directory:"
    echo "   (or press Enter to use default: ~/podcast-translator)"
    echo ""
    read -r USER_DIR

    if [ -z "$USER_DIR" ]; then
        PROJECT_DIR="$HOME/podcast-translator"
    else
        PROJECT_DIR=$(cd "$USER_DIR" 2>/dev/null && pwd) || PROJECT_DIR="$USER_DIR"
    fi
fi

# Validate project directory
if [ ! -d "$PROJECT_DIR" ]; then
    echo "❌ Error: Project directory does not exist: $PROJECT_DIR"
    echo ""
    echo "📋 Required for CLI agents: Set PODCAST_TRANSLATOR_DIR environment variable"
    echo "   export PODCAST_TRANSLATOR_DIR=/path/to/podcast-translator"
    echo ""
    echo "📋 Or use --destination-dir parameter:"
    echo "   $0 --destination-dir /path/to/podcast-translator URL"
    exit 1
fi

# Validate required scripts
if [ ! -f "$PROJECT_DIR/scripts/transcribe_cached.py" ]; then
    echo "❌ Error: Required scripts not found in: $PROJECT_DIR/scripts/"
    echo "   Please ensure you're pointing to the correct podcast-translator directory"
    exit 1
fi

INPUT_DIR="$PROJECT_DIR/input"
TRANSCRIPT_DIR="$PROJECT_DIR/transcripts"
TRANSLATION_DIR="$PROJECT_DIR/translations"
AUDIO_DIR="$PROJECT_DIR/audio"

# Create directories if they don't exist
mkdir -p "$INPUT_DIR" "$TRANSCRIPT_DIR" "$TRANSLATION_DIR" "$AUDIO_DIR"

echo "🎙️  Podcast Translation Pipeline"
echo "==================================="
echo ""
echo "📋 URL: $URL"
echo "📂 Episode: $EPISODE_NAME"
echo "📁 Project: $PROJECT_DIR"
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
