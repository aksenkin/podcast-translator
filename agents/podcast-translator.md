# Podcast Translation Agent

Autonomous agent that translates YouTube podcasts from English to Russian with text-to-speech generation.

## Task

When invoked with a YouTube URL, perform complete translation pipeline:

1. Download audio from YouTube
2. Transcribe audio to English text (with timestamps)
3. Prepare transcript for translation
4. Translate to Russian (clean text, no timestamps, ready for TTS)
5. Generate Russian text-to-speech audio

## Configuration

**Project directory**: `/home/clawd/work/podcast-translator`

All paths:
- Scripts: `/home/clawd/work/podcast-translator/scripts/`
- Input: `/home/clawd/work/podcast-translator/input/`
- Transcripts: `/home/clawd/work/podcast-translator/transcripts/`
- Translations: `/home/clawd/work/podcast-translator/translations/`
- Audio: `/home/clawd/work/podcast-translator/audio/`

## Pipeline

### Step 1: Download audio
```bash
yt-dlp -x --audio-format mp3 --audio-quality 0 \
  -o "/home/clawd/work/podcast-translator/input/podcast_$(date +%Y%m%d_%H%M%S).mp3" \
  "$URL"
```

### Step 2: Transcribe
```bash
python3 /home/clawd/work/podcast-translator/scripts/transcribe_cached.py \
  "$INPUT_FILE" \
  /home/clawd/work/podcast-translator/transcripts/ \
  small
```

### Step 3: Prepare
```bash
python3 /home/clawd/work/podcast-translator/scripts/prepare_transcript.py \
  "$TRANSCRIPT_FILE" \
  "$READY_FILE"
```

### Step 4: Translate to Russian

**Rules:**
- NO metadata headers in output
- NO timestamps
- ONLY Russian text
- Keep technical terms in English: OpenAI, Anthropic, GPT-5, API, GPU, etc.
- Remove artifacts (Chinese characters, English fragments)
- Natural paragraphs ready for TTS

### Step 5: Generate TTS
```bash
python3 /home/clawd/work/podcast-translator/scripts/generate_tts.py \
  "$TRANSLATION_RU" \
  "$AUDIO_OUTPUT"
```

## Output

When complete, report:
1. Files created (paths)
2. Duration of generated audio
3. Word count of Russian translation

## Error handling

- Report which step failed
- Show error message
- Clean up partial files if needed
