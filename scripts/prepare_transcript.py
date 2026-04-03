#!/usr/bin/env python3
"""
Save transcription as file for AI translation
The actual translation will be done by the AI assistant
"""

import sys

def load_text(file_path):
    """Load text from file"""
    with open(file_path, 'r', encoding='utf-8') as f:
        return f.read()

def save_text(text, file_path):
    """Save text to file"""
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(text)

def remove_timestamps(line):
    """Remove timestamp prefix from a line"""
    import re
    # Match pattern like [00:00 - 00:05] or [MM:SS - MM:SS]
    pattern = r'^\[\d{2}:\d{2}\s*-\s*\d{2}:\d{2}\]\s*'
    return re.sub(pattern, '', line)

def prepare_for_translation(input_file, output_file):
    """
    Prepare transcript for TTS generation by removing timestamps
    """
    print(f"STATUS: Preparing transcript for TTS: {input_file}", flush=True)

    text = load_text(input_file)

    if not text.strip():
        print("ERROR: Empty input file", flush=True)
        sys.exit(1)

    # Remove timestamps from each line
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        cleaned_line = remove_timestamps(line)
        if cleaned_line.strip():  # Only keep non-empty lines
            cleaned_lines.append(cleaned_line.strip())

    cleaned_text = '\n'.join(cleaned_lines)

    save_text(cleaned_text, output_file)
    print(f"SUCCESS: Prepared for TTS: {output_file}", flush=True)
    print(f"STATUS: Original text: {len(text)} characters, Cleaned: {len(cleaned_text)} characters", flush=True)

if __name__ == "__main__":
    import datetime

    if len(sys.argv) < 3:
        print("Usage: python3 prepare_transcript.py <input_file> <output_file>")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2]

    prepare_for_translation(input_file, output_file)
