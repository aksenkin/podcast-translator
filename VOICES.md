# TTS Voices

**Read in other languages:** [Русский](VOICES.ru.md)

## Available Russian Voices

### Female Voices

| Voice | ID | Description |
|-------|----|-------------|
| Dariya | `ru-RU-DariyaNeural` | Female voice |
| Svetlana | `ru-RU-SvetlanaNeural` | Female voice |

### Male Voices

| Voice | ID | Description |
|-------|----|-------------|
| Dmitry | `ru-RU-DmitryNeural` | Male voice (default) |

## How to Use

### Command Line

**Default voice (Dmitry)**:
```bash
python3 scripts/generate_tts.py \
  translations/podcast_ru.txt \
  audio/podcast_ru.mp3
```

**Female voice (Svetlana)**:
```bash
python3 scripts/generate_tts.py \
  translations/podcast_ru.txt \
  audio/podcast_ru.mp3 \
  ru-RU-SvetlanaNeural
```

**Female voice (Dariya)**:
```bash
python3 scripts/generate_tts.py \
  translations/podcast_ru.txt \
  audio/podcast_ru.mp3 \
  ru-RU-DariyaNeural
```

### With Subagent

When invoking the podcast-translator agent, it will ask which voice to use:

```
Translate this podcast: https://www.youtube.com/watch?v=VIDEO_ID
Use a female voice.
```

Or simply:
```
Translate this podcast with a female voice: [URL]
```

## Voice Comparison

### Dmitry (Male)
- Lower pitch
- Standard for technical podcasts
- Good intelligibility

### Svetlana (Female)
- Higher pitch
- Softer sound
- Good for educational content

### Dariya (Female)
- Higher pitch
- Clear articulation
- Alternative female voice option

## All Available Edge TTS Voices

To get a complete list of all available voices:

```bash
python3 -c "import edge_tts; print('\n'.join([v['Name'] for v in edge_tts.list_voices() if 'ru' in v['Locale']]))"
```

## Recommendations

- **Technical podcasts**: Dmitry (default male voice)
- **Educational content**: Svetlana or Dariya (female voices)
- **News releases**: Dmitry
- **Training materials**: Svetlana or Dariya
