---
name: podcast-translator
description: Translate podcast transcripts from English to Russian. Use this skill whenever the user needs to translate a podcast transcript, translate audio transcription, or convert English podcast content to Russian. This skill handles the podcast translation workflow: reading prepared transcript files with timestamps, translating while preserving technical terms and names in English, and outputting continuous Russian text without timestamps. Trigger this skill for tasks like "translate this podcast", "convert transcript to Russian", or any podcast/audio translation work.
---

# Podcast Translator Skill

Translate podcast transcripts from English to Russian, outputting continuous Russian text without timestamps.

## When to use this skill

Use this skill when:
- The user needs to translate a podcast transcript from English to Russian
- The user asks to translate prepared transcript files
- The user mentions converting podcast content to Russian
- The user wants to translate audio transcription with timestamps

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

### Step 2: Translate the content

When translating:

1. **Do NOT include metadata header** - The output should contain ONLY the translated text, no headers or separators.

2. **Remove timestamps and translate** - For each line with a timestamp:
   - Remove the timestamp prefix (e.g., `[00:00 - 00:05]`)
   - Translate the English text to Russian
   - Combine translations into continuous Russian text
   - **Do NOT include English text or timestamps in the output**

   The output should be continuous Russian prose - natural paragraphs that flow well.

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
   - Creating natural paragraph breaks where topics change

### Step 3: Verify and clean the translation

After translating, perform a final verification pass to ensure the text is ready for text-to-speech:

1. **Remove all metadata** - Delete any headers, separators, or metadata from the output
2. **Remove non-Russian artifacts** - Delete any characters or text that cannot be pronounced in Russian, EXCEPT for:
   - Technical terms and company names (in English)
   - Product names and model numbers (in English)
   - Person names (in English)
3. **Check for mixed-language artifacts** - Look for and remove:
   - Chinese or other non-Cyrillic/non-Latin characters
   - English words embedded in Russian text (unless they are known technical terms)
   - Partial words or fragments from the original English text
4. **Verify TTS compatibility** - Ensure the text flows naturally and can be read aloud by a Russian TTS system

### Step 4: Save the translation

Save the cleaned translated content to `{episode_name}_ru.txt` in the same translations directory.

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

The output (`translations/podcast_20260327_122421_ru.txt`) should be:

```
Сегодня в AI Daily Brief, большие изменения в OpenAI, так как побочные квесты завершаются, а основной квест Work AGI набирает обороты.

С возвращением в AI Daily Brief. Отличительной чертой 2026 года пока стали крупные изменения в стиле переломных моментов.
```

Note: No metadata header, no timestamps, only clean Russian text ready for TTS.

## Important notes

- Use Claude's built-in translation capabilities (no external APIs)
- Always read the full input file before translating
- Process the translation in a single pass for consistency
- **NO metadata header in output** - only translated Russian text
- **Remove all timestamps from the output** - only Russian text
- Do NOT include English text in the output (except for technical terms/names)
- Do not translate technical terms, company names, or product names
- **Final verification pass is required** - remove artifacts, check for non-Russian characters, ensure TTS compatibility
- Create natural paragraph breaks where topics shift
- The output should read like natural Russian prose ready for text-to-speech
