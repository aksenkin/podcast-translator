---
name: podcast-translator
description: Translate podcast transcripts from English to Russian. Use this skill whenever the user needs to translate a podcast transcript, create Russian voiceover, or convert podcast content to Russian. This skill reads transcript files, translates English content to Russian while preserving technical terms and names in English, and creates clean text for TTS generation. Trigger this skill for tasks like "translate this podcast", "create Russian translation", or any podcast translation task.
---

# Podcast Translator Skill

Translate podcast transcripts from English to Russian for voiceover generation.

## When to use this skill

Use this skill when:
- The user needs to translate a podcast transcript from English to Russian
- The user asks to translate transcript files for Russian voiceover
- The user mentions converting podcast content to Russian
- The user wants to create TTS audio from translated content

## Translation workflow

### Step 1: Read the source file

Read the transcript file. The file contains English text (may include timestamps):

```
[00:00 - 00:05]  First segment of text here
[00:05 - 00:10]  Second segment continues here
```

### Step 2: Translate the content

When translating:

1. **Translate to natural Russian** - Convert English text to natural-sounding Russian:
   - Focus on meaning, not word-for-word translation
   - Use appropriate Russian technical terminology
   - Maintain the tone of the original content

2. **Remove all timestamps** - The output should contain ONLY translated Russian text, no timestamps or metadata

   Example transformation:
   ```
   [00:00 - 00:05]  Today on the AI Daily Brief, big changes at OpenAI
   ```
   becomes:
   ```
   Сегодня в AI Daily Brief, большие изменения в OpenAI
   ```

3. **Technical terms and names** - Keep technical terms, company names, product names, and proper nouns in English:
   - "OpenAI", "Anthropic", "Claude Code", "OpenClaw"
   - "GPU", "API", "MCP", "SSH"
   - Person names: "Sam Altman", "Peter Steinberger"
   - Product names: "GPT-5", "Opus 4.6", "Codex"

   Rationale: These terms are industry-standard and transliterating them would make the text harder to understand for the technical audience.

### Step 3: Verify and save the translation

After translating, perform a final verification pass to ensure the output is correct:

1. **Remove all timestamps and metadata** - Only Russian text should remain
2. **Check for artifacts** - Remove any English fragments (except known technical terms)
3. **Remove unspeakable characters** - **CRITICAL for TTS generation**:
   - **NO Chinese characters** (汉字, 漢字) - TTS will fail
   - **NO Japanese kanji/kana** - TTS will fail
   - **NO Korean hangul** - TTS will fail
   - **NO Arabic, Thai, or other non-Cyrillic/non-Latin scripts** - TTS will fail
   - Keep ONLY: Cyrillic letters, Latin letters (for technical terms), numbers, and standard punctuation (. , ! ? : ; - —)
   - If TTS encounters unsupported characters, it will fail or produce garbled audio
4. **Verify readability** - Ensure natural flow for Russian-speaking technical audience

Save the translation in the translations directory:
- **`{episode_name}_ru_tts.txt`** - Clean Russian text (for TTS generation)

## File locations

- **Project directory**: `/home/clawd/work/podcast-translator`
- **Source files**: `transcripts/`
- **Output files**: `translations/{episode_name}_ru_tts.txt`

## Example

Given this input:

```
[00:00 - 00:05]  Today on the AI Daily Brief, big changes at OpenAI
[00:05 - 00:08]  as the side quest end and the main quest heats up.
[00:08 - 00:10]  Welcome back to the AI Daily Brief.
[00:10 - 00:15]  The hallmark of 2026 so far has been big inflection point style change.
```

The output should be:

**`translations/podcast_ru_tts.txt`**:
```
Сегодня в AI Daily Brief, большие изменения в OpenAI, так как побочные квесты завершаются, а основной квест набирает обороты.

С возвращением в AI Daily Brief. Отличительной чертой 2026 года пока стали крупные изменения в стиле переломных моментов.
```

Note: Timestamps removed, natural paragraph breaks added for better TTS flow.

## Important notes

- Use Claude's built-in translation capabilities (no external APIs)
- Always read the full input file before translating
- Process the translation in a single pass for consistency
- **NO timestamps in output** - only clean Russian text
- **NO metadata or headers** - just the translated content
- **CRITICAL: Remove all unspeakable characters** - Chinese, Japanese, Korean, Arabic, Thai, etc. will break TTS
- Remove all English text (except for technical terms/names)
- Do not translate technical terms, company names, or product names
- Join segments into natural paragraphs for better TTS flow
- The output must be ready for text-to-speech generation without errors
