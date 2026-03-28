---
name: podcast-translator
description: Translate podcast transcripts from English to Russian with timestamp preservation. Use this skill whenever the user needs to translate a podcast transcript while keeping temporal alignment, create bilingual subtitles, or maintain timestamp references in translated content. This skill reads prepared transcript files with timestamps, translates English content to Russian while preserving technical terms and names in English, and maintains the original timestamp format. Trigger this skill for tasks like "translate this podcast with timestamps", "create aligned transcript", or any podcast translation requiring temporal references.
---

# Podcast Translator Skill

Translate podcast transcripts from English to Russian while preserving timestamps for temporal alignment.

## When to use this skill

Use this skill when:
- The user needs to translate a podcast transcript from English to Russian while keeping timestamps
- The user asks to translate prepared transcript files with temporal alignment
- The user mentions converting podcast content to Russian with timestamps preserved
- The user wants to create bilingual subtitles or aligned transcripts
- The user needs timestamp references in the translated output

## Translation workflow

### Step 1: Read the source file

Read the transcript file from the translations directory. The file will be named `{episode_name}_ready.txt` and contains:

1. **Metadata header** (lines 1-6):
   ```
   # Podcast Translation Request
   # Source Language: English
   # Target Language: Russian
   # Generated: YYYY-MM-DD HH:MM:SS

   ---
   ```

2. **Transcript content** with timestamps:
   ```
   [00:00 - 00:05]  First segment of text here
   [00:05 - 00:10]  Second segment continues here
   ```

### Step 2: Translate the content while preserving timestamps

When translating:

1. **Do NOT include metadata header** - The output should contain ONLY the translated segments with timestamps, no headers or separators.

2. **Preserve timestamps and translate** - For each line with a timestamp:
   - **KEEP the timestamp prefix** (e.g., `[00:00 - 00:05]`)
   - Translate the English text after the timestamp to Russian
   - Output format: `[TIMESTAMP] Russian translation here`
   - **Each timestamped segment should be on its own line**

   Example transformation:
   ```
   [00:00 - 00:05]  Today on the AI Daily Brief, big changes at OpenAI
   ```
   becomes:
   ```
   [00:00 - 00:05] Сегодня в AI Daily Brief, большие изменения в OpenAI
   ```

3. **Technical terms and names** - Keep technical terms, company names, product names, and proper nouns in English:
   - "OpenAI", "Anthropic", "Claude Code", "OpenClaw"
   - "GPU", "API", "MCP", "SSH"
   - Person names: "Sam Altman", "Peter Steinberger"
   - Product names: "GPT-5", "Opus 4.6", "Codex"

   Rationale: These terms are industry-standard and transliterating them would make the text harder to understand for the technical audience.

4. **Translation quality** - Focus on:
   - Natural-sounding Russian (not word-for-word literal translation)
   - Preserving the meaning and tone of the original
   - Using appropriate Russian technical terminology where it exists
   - Maintaining readability for a Russian-speaking technical audience

### Step 3: Verify and clean the translation

After translating, perform a final verification pass to ensure the output is correct:

1. **Remove all metadata** - Delete any headers, separators, or metadata from the output
2. **Verify timestamp format** - Ensure each line has the correct timestamp format: `[MM:SS - MM:SS]`
3. **Check timestamp alignment** - Verify that timestamps match the original file exactly
4. **Remove non-Russian artifacts** - Look for and remove:
   - Chinese or other non-Cyrillic/non-Latin characters
   - English words embedded in Russian text (unless they are known technical terms)
   - Partial words or fragments from the original English text
5. **Verify each segment** - Ensure each timestamped line contains only Russian text (except for technical terms)

### Step 4: Save the translation

Save two versions of the translation in the same translations directory:

1. **`{episode_name}_ru.txt`** - Full translation with timestamps (for aligned transcripts/subtitles)
2. **`{episode_name}_ru_tts.txt`** - Clean text without timestamps (for TTS generation)

When creating the TTS version:
- Remove all timestamp prefixes
- Remove all metadata
- Keep only the Russian text
- Join segments into natural paragraphs

## File locations

- **Project directory**: `/home/clawd/.openclaw/workspace/podcast-translator`
- **Translations directory**: `translations/`
- **Input files**: `translations/{episode_name}_ready.txt`
- **Output files**: `translations/{episode_name}_ru.txt`

## Example

Given this input (`translations/podcast_20260327_122421_ready.txt`):

```
# Podcast Translation Request
# Source Language: English
# Target Language: Russian
# Generated: 2026-03-27 12:48:12

---
[00:00 - 00:05]  Today on the AI Daily Brief, big changes at OpenAI
[00:05 - 00:08]  as the side quest end and the main quest heats up.
[00:08 - 00:10]  Welcome back to the AI Daily Brief.
[00:10 - 00:15]  The hallmark of 2026 so far has been big inflection point style change.
```

The output should create TWO files:

**`translations/podcast_20260327_122421_ru.txt`** (with timestamps):
```
[00:00 - 00:05] Сегодня в AI Daily Brief, большие изменения в OpenAI
[00:05 - 00:08] так как побочные квесты завершаются, а основной квест набирает обороты.
[00:08 - 00:10] С возвращением в AI Daily Brief.
[00:10 - 00:15] Отличительной чертой 2026 года пока стали крупные изменения в стиле переломных моментов.
```

**`translations/podcast_20260327_122421_ru_tts.txt`** (without timestamps, for TTS):
```
Сегодня в AI Daily Brief, большие изменения в OpenAI, так как побочные квесты завершаются, а основной квест набирает обороты.

С возвращением в AI Daily Brief. Отличительной чертой 2026 года пока стали крупные изменения в стиле переломных моментов.
```

Note: Two output files - one with timestamps for reference, one without for TTS generation.

## Important notes

- Use Claude's built-in translation capabilities (no external APIs)
- Always read the full input file before translating
- Process the translation in a single pass for consistency
- **NO metadata header in output** - only translated segments with timestamps
- **PRESERVE all timestamps in the output** - keep exact timestamp format from input
- Each timestamped segment should be on its own line
- Do NOT include English text in the output (except for technical terms/names)
- Do not translate technical terms, company names, or product names
- **Final verification pass is required** - remove artifacts, check for non-Russian characters, verify timestamp format
- The output should be suitable for creating aligned bilingual transcripts or subtitles
