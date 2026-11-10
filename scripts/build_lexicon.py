"""Build a gloss lexicon that cannot leak held-out sentences.

Combines the ASLLRP Sign Bank "related English words" export with corpus-derived
entries from ASLLRP pairs, excluding every reserved held-out group and every
held-out English sentence. Corpus entries keep only high-precision pairs whose
gloss core is literally an English word of the same sentence (the rule of the
earlier project's dictionary builder). Output is restricted data: keep it private.

    python scripts/build_lexicon.py --data ../sign_language_gen/data \
        --signbank ../sign_language_gen/data/export/signbank_translations_2026_08_02.json \
        --manifest reports/heldout-v1/manifest.json --out private/lexicons/heldout-safe-v1.json
"""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from signir.data import file_hash, read_jsonl, write_json  # noqa: E402
from signir.heldout import ASLLRP_FILES, group_key, norm, reserved_groups  # noqa: E402

PREFIXES = ('fs-', 'ns-', '#', '(1h)', '(2h)', '(2h)alt.', 'DCL:', 'BCL:', 'ICL:', 'SCL:')
NONLEX = re.compile(r'^(IX|POSS|SELF|PART|DCL|BCL|ICL|SCL)\b|[:"]|^\d')


def gloss_core(token):
    t = token
    for prefix in PREFIXES:
        if t.startswith(prefix):
            t = t[len(prefix):]
    if not t or NONLEX.search(t):
        return None
    t = re.split(r'[+/]', t)[0]
    t = t.split('-')[0] if '-' in t and not t.startswith('-') else t
    return re.sub(r'[^A-Za-z]', '', t).lower() or None


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--data', type=Path, required=True)
    p.add_argument('--signbank', type=Path, required=True, help='signbank_translations_*.json (word -> labels)')
    p.add_argument('--manifest', type=Path, required=True, help='Held-out manifest listing reserved groups')
    p.add_argument('--heldout-pairs', type=Path, default=None, help='Optional private pairs.jsonl to exclude by text')
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--top-k', type=int, default=8)
    args = p.parse_args(argv)
    if args.out.exists():
        p.exit(2, f'error: output exists: {args.out}\n')
    reserved = reserved_groups(args.manifest)
    if not reserved:
        p.exit(2, 'error: manifest lists no reserved groups\n')
    heldout_text = {norm(r['english']) for r in read_jsonl(args.heldout_pairs)} if args.heldout_pairs else set()
    counts, used, skipped, seen = defaultdict(Counter), 0, 0, set()
    for name in ASLLRP_FILES:
        for r in read_jsonl(args.data / name):
            key = (norm(r['text']), r['gloss'])
            if key in seen:
                continue
            seen.add(key)
            if group_key(r.get('source'), r['doc_id']) in reserved or norm(r['text']) in heldout_text:
                skipped += 1
                continue
            used += 1
            english = {w.lower() for w in re.findall(r'[A-Za-z]+', r['text'])}
            for token in r['gloss'].split():
                core = gloss_core(token)
                if core and core in english:
                    counts[core][token] += 1
    entries = {w: [g for g, _ in c.most_common(args.top_k)] for w, c in counts.items()}
    signbank = json.loads(args.signbank.read_text(encoding='utf-8'))
    for word, labels in signbank.items():
        merged = list(dict.fromkeys(labels[:args.top_k] + entries.get(word, [])))
        entries[word] = merged
    write_json(args.out, {'entries': entries, 'meta': {
        'what': 'Sign Bank related English words plus corpus pairs outside the reserved held-out groups',
        'corpus_pairs_used': used, 'corpus_pairs_excluded': skipped,
        'reserved_groups_excluded': len(reserved), 'manifest_sha256': file_hash(args.manifest),
        'signbank_sha256': file_hash(args.signbank), 'top_k': args.top_k,
        'redistribution': 'PROHIBITED: derived from restricted ASLLRP material; keep private'}})
    print(f'Wrote {len(entries)} entries ({used} corpus pairs used, {skipped} held-out pairs excluded) to {args.out}')


if __name__ == '__main__':
    main()
