#!/usr/bin/env python3
"""
Extract clean TTS text from translation file (removes timestamps)
"""

import sys
import re

def extract_tts_text(input_file, output_file):
    """Extract clean Russian text from translation file (remove timestamps)"""
    print(f"STATUS: Extracting TTS text from {input_file}", flush=True)

    with open(input_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    clean_lines = []
    for line in lines:
        # Remove timestamp pattern: [MM:SS - MM:SS]
        clean_line = re.sub(r'^\[\d{2}:\d{2}\s*-\s*\d{2}:\d{2}\]\s*', '', line)
        if clean_line.strip():
            clean_lines.append(clean_line.strip())

    clean_text = '\n'.join(clean_lines)

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(clean_text)

    print(f"SUCCESS: TTS text extracted to {output_file}", flush=True)
    print(f"STATUS: {len(clean_lines)} lines, {len(clean_text)} characters", flush=True)

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 extract_tts_text.py <input_file> <output_file>")
        sys.exit(1)

    extract_tts_text(sys.argv[1], sys.argv[2])
