"""Metadata-only audit of an earlier checkout. No corpus text leaves this script."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory(root):
    entries = []
    for path in sorted((root/'data'/'processed').rglob('*.jsonl')):
        rows = [json.loads(line) for line in path.read_text(encoding='utf-8-sig').splitlines() if line.strip()]
        keys = sorted({k for r in rows for k in r})
        texts = Counter(' '.join(r.get('text', r.get('source', '')).casefold().split()) for r in rows)
        docs = {r['doc_id'] for r in rows if r.get('doc_id')}
        entries.append({'path': str(path.relative_to(root)), 'sha256': sha(path), 'n': len(rows),
                        'fields': keys, 'documents': len(docs),
                        'missing_document_id': sum(not r.get('doc_id') for r in rows),
                        'duplicate_english_excess': sum(n-1 for t, n in texts.items() if t),
                        'licence': 'See docs/data-inventory.md; availability is not redistribution permission'})
    selected = root/'results'/'asllrp_strat_gpt54mini_baseline_20260910T173514Z'
    for path in sorted(selected.glob('*.json*')):
        value = json.loads(path.read_text()) if path.suffix == '.json' else [json.loads(x) for x in path.read_text().splitlines() if x]
        entries.append({'path': str(path.relative_to(root)), 'sha256': sha(path),
                        'n': len(value) if isinstance(value, list) else value.get('n'),
                        'fields': sorted(value[0] if isinstance(value, list) and value else value)})
    family_counts = {name: len(list((root/'data'/name).rglob(pattern))) for name, pattern in
                     [('dai', '*.xml'), ('raw/ncslgr', '*.eaf'), ('signbank', '*.csv'), ('asl_lex', '*.csv'), ('asl_citizen', '*.csv')]}
    return {'audit_date': '2026-10-10', 'root': str(root), 'files': entries, 'family_file_counts': family_counts,
            'privacy': 'Metadata and counts only; original and derived corpus text must remain private.'}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    result = inventory(a.root)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(f'Inventoried {len(result["files"])} files without exporting corpus text')
