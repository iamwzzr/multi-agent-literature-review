"""Isolated parser process: terminated on timeout/disconnection; never runs PDF actions."""
import json
import sys

from pypdf import PdfReader


def main():
    reader = PdfReader(sys.argv[1])
    if reader.is_encrypted:
        raise ValueError('Encrypted PDF is not supported')
    if not 1 <= len(reader.pages) <= int(sys.argv[2]):
        raise ValueError('Page limit exceeded')
    texts, total = [], 0
    for page in reader.pages:
        text = page.extract_text() or ''
        total += len(text)
        if len(text) > 60000 or total > 2_000_000:
            raise ValueError('Text extraction limit exceeded')
        texts.append(text)
    metadata = reader.metadata or {}
    result = {
        'title': str(metadata.get('/Title', ''))[:500],
        'author': str(metadata.get('/Author', ''))[:500], 'pages': texts,
    }
    sys.stdout.buffer.write(json.dumps(result, ensure_ascii=False).encode('utf-8'))


if __name__ == '__main__':
    main()
