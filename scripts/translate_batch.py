import os, re, json, subprocess, sys

def translate_chunk(chunk, chunk_num, total):
    """Translate a single chunk using ollama API."""
    prompt = f'''Переведи следующий английский текст на русский язык. Сохраняй технические термины на английском (OpenAI, GPU, API, Claude, ChatGPT, DaVinci, YouTube и т.д.). Удали ВСЕ невыговариваемые символы: эмодзи, китайские, японские, корейские символы, специальные символы, и ЛЮБЫЕ скобочные маркеры типа [chunk N/M] или [часть N/M]. Напиши чистый естественный текучий русский текст с правильной пунктуацией для TTS. НЕ включай timestamps или chunk markers.

Text to translate:
{chunk}

Russian translation:'''

    try:
        result = subprocess.run(
            ['curl', '-s', 'http://localhost:11434/api/generate', '-H', 'Content-Type: application/json', '-d',
             json.dumps({'model': 'kimi-k2.6:cloud', 'prompt': prompt, 'stream': False})],
            capture_output=True, text=True, timeout=300
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            ru_text = data.get('response', '').strip()
            # Clean up
            ru_text = re.sub(r'\[.*?\]', '', ru_text)
            ru_text = re.sub(r'[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af\U0001f600-\U0001f64f\U0001f300-\U0001f5ff\U0001f680-\U0001f6ff\U0001f700-\U0001f77f\U0001f780-\U0001f7ff\U0001f800-\U0001f8ff\U0001f900-\U0001f9ff\U0001fa00-\U0001fa6f\U0001fa70-\U0001faff\U00002702-\U000027b0\U000024c2-\U0001f251]', '', ru_text)
            ru_text = re.sub(r'[^\w\s\u0400-\u04ff.,!?;:\-\'\"()«»—–]', ' ', ru_text)
            ru_text = re.sub(r'\s+', ' ', ru_text).strip()
            return ru_text
    except Exception as e:
        print(f'Chunk {chunk_num} error: {e}', file=sys.stderr)
    return None

def main():
    with open('translations/oxerUfMFuCU_ready.txt', 'r') as f:
        text = f.read()

    # Simple chunking by sentences
    sentences = text.replace('\n', ' ').split('. ')
    chunks = []
    current = ''
    for s in sentences:
        if len(current) + len(s) + 2 < 3000:
            current += s + '. '
        else:
            if current:
                chunks.append(current.strip())
            current = s + '. '
    if current:
        chunks.append(current.strip())

    print(f'Text length: {len(text)} chars')
    print(f'Chunks: {len(chunks)}')

    translated = []
    for i, chunk in enumerate(chunks):
        print(f'Translating chunk {i+1}/{len(chunks)} ({len(chunk)} chars)...', flush=True)
        ru_text = translate_chunk(chunk, i+1, len(chunks))
        if ru_text:
            translated.append(ru_text)
            print(f'  -> {len(ru_text)} chars', flush=True)
        else:
            print(f'  -> FAILED', flush=True)

    # Write output
    output = '\n\n'.join(t for t in translated if t)
    with open('translations/oxerUfMFuCU_ru_tts.txt', 'w') as f:
        f.write(output)

    print(f'Done! Output: {len(output)} chars from {len(translated)}/{len(chunks)} chunks')

if __name__ == '__main__':
    main()
