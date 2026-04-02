#!/usr/bin/env python3
"""
Extract TTS-ready text from timestamped translation
Removes timestamps and creates clean text for Edge TTS
"""

import sys
import re

def extract_tts_text(input_file, output_file):
    """
    Extract clean Russian text without timestamps for TTS

    Input format:
    # Metadata
    [00:00 - 00:05] English text here
    Russian translation here

    Output format:
    Russian translation here (continuous prose)
    """
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Split into lines
        lines = content.split('\n')

        # Extract only Russian text (lines after timestamps)
        russian_lines = []
        skip_next = False

        for i, line in enumerate(lines):
            line = line.strip()

            # Skip empty lines
            if not line:
                continue

            # Skip metadata headers
            if line.startswith('#') or line.startswith('---'):
                continue

            # Skip timestamp lines (and the English text on them)
            if re.match(r'^\[\d{2}:\d{2}', line):
                # Line contains timestamp + English text - skip it
                continue

            # Skip lines that look like English text (before Russian translation)
            # Pattern: timestamp line is followed by English text, then Russian translation
            # We only want the Russian translation lines
            if i > 0 and re.match(r'^\[\d{2}:\d{2}', lines[i-1] if i > 0 else ''):
                # This is the Russian translation line after a timestamp
                russian_lines.append(line)
            elif not re.match(r'^[A-Z]', line) and not re.match(r'^\[\d{2}:\d{2}', line):
                # Keep lines that don't start with capital English letters or timestamps
                # These are likely Russian translations
                russian_lines.append(line)

        # Join into continuous prose with proper spacing
        tts_text = ' '.join(russian_lines)

        # Clean up spacing: add space after punctuation
        tts_text = re.sub(r'(?<=[.!?])\s+', ' ', tts_text)
        tts_text = re.sub(r'\s+', ' ', tts_text)  # Remove extra spaces

        # Write to output file
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(tts_text.strip() + '\n')

        word_count = len(tts_text.split())
        char_count = len(tts_text)

        print(f"✓ TTS text extracted: {word_count} words, {char_count} chars")
        return True

    except FileNotFoundError:
        print(f"❌ Error: File not found: {input_file}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 extract_tts_text.py <input_file> <output_file>")
        print("")
        print("Example:")
        print("  python3 extract_tts_text.py translations/episode_ru.txt translations/episode_ru_tts.txt")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2]

    success = extract_tts_text(input_file, output_file)
    sys.exit(0 if success else 1)
