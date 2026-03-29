# Subagents and Skills

**Read in other languages:** [Русский](AGENTS.ru.md)

## Claude Code Agent

Autonomous agent for translating podcasts from YouTube.

### Location

- **Project**: `agents/podcast-translator.md`
- **System**: `~/.claude/agents/podcast-translator.md`

### Agent Configuration

```yaml
name: podcast-translator
description: Translates YouTube podcasts from English to Russian. Downloads audio, transcribes, translates, and generates TTS.
tools: Bash, Read, Write, Edit
model: sonnet
```

### How to Use

**Simple request:**
```
Translate this podcast: https://www.youtube.com/watch?v=VIDEO_ID
```

**Explicit invocation:**
```
Use the podcast-translator agent for this URL
```

**With voice selection:**
```
Translate this podcast with a female voice
```

### What the Agent Does

1. 📹 Downloads audio from YouTube
2. 🎤 Transcribes to English text
3. 🌍 Prepares for translation
4. 🇷🇺 Translates to Russian
5. 🔊 Generates Russian voiceover

### Result

The agent will return:
- Paths to all created files
- Audio duration
- Word count in translation
- File sizes

### Available Voices

- `ru-RU-DmitryNeural` - Male voice (default)
- `ru-RU-SvetlanaNeural` - Female voice
- `ru-RU-DariyaNeural` - Female voice

## OpenClaw Skill 🎙️

Automatic skill for OpenClaw with full pipeline.

### Location

- **Project**: `skills/podcast-translator/SKILL.md`

### Skill Configuration

```yaml
name: podcast-translator
description: "Translate YouTube podcasts from English to Russian with TTS generation..."
emoji: "🎙️"
requires: { "bins": ["yt-dlp", "python3"] }
```

### How to Use

Just send a YouTube URL:

```
Translate this podcast: https://www.youtube.com/watch?v=VIDEO_ID
```

**With voice selection:**
```
Translate this podcast with a female voice: [URL]
```

### Features

- Automatically recognizes YouTube URLs
- Spawns subagent to execute pipeline
- Returns results when ready
- Works asynchronously (doesn't block conversation)

## Agent Format

Agents use YAML frontmatter:

```yaml
---
name: podcast-translator
description: Translates YouTube podcasts from English to Russian
tools: Bash, Read, Write, Edit
model: sonnet
---
```

Followed by system prompt in Markdown format.

## Documentation

- [Subagents documentation](https://code.claude.com/docs/en/sub-agents)
- [OpenClaw Skills documentation](https://openclaw.dev/docs/skills)
