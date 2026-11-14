"""Optional user-supplied bibliography bound to exact PDF bytes, never identity verification."""
import json
from pathlib import Path


def bibliography(path, digest):
    path = Path(path)
    sidecar = path.with_suffix('.metadata.json')
    # Sidecars may not redirect reading outside the PDF's directory.
    if not sidecar.is_file() or sidecar.is_symlink() or sidecar.stat().st_size > 64000:
        return {}
    try:
        value = json.loads(sidecar.read_text(encoding='utf-8'))
        if not isinstance(value, dict) or value.get('sha256') != digest:
            return {}
        title, authors, year = value.get('title'), value.get('authors'), value.get('year')
        if not isinstance(title,str) or not 1 <= len(title.strip()) <= 500:
            return {}
        if not isinstance(authors,list) or len(authors)>100 or any(not isinstance(a,str) or not 1<=len(a)<=300 for a in authors):
            return {}
        if year is not None and (type(year) is not int or not 1<=year<=9999):
            return {}
        return {'title':title.strip(),'authors':authors,'year':year,
                'metadata_provenance':'user_provided_hash_bound',
                'metadata_source':value.get('source') if isinstance(value.get('source'),str) else None}
    except (OSError,UnicodeError,ValueError):
        return {}


def metadata_fingerprint(path):
    sidecar = Path(path).with_suffix('.metadata.json')
    if sidecar.is_file() and not sidecar.is_symlink() and sidecar.stat().st_size <= 64000:
        import hashlib
        return hashlib.sha256(sidecar.read_bytes()).hexdigest()
    return 'none'
