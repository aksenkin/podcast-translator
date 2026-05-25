#!/usr/bin/env python3
"""
Extract TTS-ready text from translation file (removes timestamps).
"""

import sys
import re

def extract_tts_text(input_file, output_file):
    """Extract Russian text without timestamps."""
    with open(input_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # Filter out timestamp lines and extract just the Russian text
    tts_lines = []
    for line in lines:
        line = line.strip()
        # Skip empty lines
        if not line:
            continue
        # Skip metadata/manifest lines
        if line.startswith('==='):
            continue
        # Extract text after timestamp
        # Pattern: [00:00 - 00:03] Text here
        match = re.match(r'^\[\d{2}:\d{2}\s*-\s*\d{2}:\d{2}\]\s*(.+)$', line)
        if match:
            text = match.group(1).strip()
            if text:
                tts_lines.append(text)

    # Join with spaces for natural TTS flow
    tts_text = ' '.join(tts_lines)

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(tts_text)

    print(f"Extracted {len(tts_lines)} segments")
    print(f"Output: {output_file}")
    return len(tts_lines)

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Usage: extract_tts_text.py <input_file> <output_file>")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2]

    extract_tts_text(input_file, output_file)
