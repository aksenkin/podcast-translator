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

def prepare_for_translation(input_file, output_file):
    """
    Prepare transcript for AI translation
    This just copies the text - translation will be done by AI assistant
    """
    print(f"STATUS: Preparing transcript for translation: {input_file}", flush=True)

    text = load_text(input_file)

    if not text.strip():
        print("ERROR: Empty input file", flush=True)
        sys.exit(1)

    # Add metadata header
    metadata = f"""# Podcast Translation Request
# Source Language: English
# Target Language: Russian
# Generated: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

---
"""
    full_text = metadata + text

    save_text(full_text, output_file)
    print(f"SUCCESS: Prepared for translation: {output_file}", flush=True)
    print(f"STATUS: Text length: {len(text)} characters", flush=True)

if __name__ == "__main__":
    import datetime

    if len(sys.argv) < 3:
        print("Usage: python3 prepare_transcript.py <input_file> <output_file>")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2]

    prepare_for_translation(input_file, output_file)
