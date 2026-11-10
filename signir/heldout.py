"""A sealed, document-held-out set for independent human fact labels.

The set is drawn only from documents that no SignIR development step has read.
It is built once, its hash is published, and it is scored once per frozen checker.
Annotation sheets are blind: they show the English, one candidate gloss and its
non-manual labels, never the checker's output or which system wrote the gloss.

    python -m signir heldout build --data ../sign_language_gen/data --out private/heldout-v1 \
        --manifest reports/heldout-v1/manifest.json
    python -m signir heldout add-candidates private/heldout-v1 --predictions run.jsonl --system NAME --out ...
    python -m signir heldout sheets private/heldout-v1 --out private/heldout-v1/sheets
    python -m signir heldout adjudicate --key K --sheet A.csv --sheet B.csv --out DIR [--resolved R.csv]
    python -m signir heldout score private/heldout-v1 --gold DIR/gold.jsonl --manifest M --out DIR
"""
from collections import Counter, defaultdict
import csv
import glob
import hashlib
import json
import math
from pathlib import Path
import random
import re
import subprocess
import xml.etree.ElementTree as ET
import zipfile

from .data import file_hash, read_jsonl, write_json, write_jsonl
from .schema import CHECKS

VERSION = 'heldout-v1'
# Files whose sentences earlier SignIR work read: the 643-pair natural audit (asllrp_strat),
# the scenario reference audit (asllrp, asllrp_paper) and the correction pilot (asllrp_paper).
DEVELOPMENT_FILES = ('processed/asllrp/test.jsonl', 'processed/asllrp_paper/test.jsonl',
                     'processed/asllrp_strat/test.jsonl')
ASLLRP_FILES = tuple(f'processed/{view}/{split}.jsonl' for view in
                     ('asllrp', 'asllrp_paper', 'asllrp_strat', 'asllrp_doc_faithful')
                     for split in ('test', 'example_pool'))
NCSLGR_FILES = ('processed/ncslgr/test.jsonl', 'processed/ncslgr/example_pool.jsonl')
LABELS = ('ok', 'changed', 'omitted', 'added', 'na', 'unclear')
ERROR_LABELS = {'changed', 'omitted', 'added'}
MEANING = ('yes', 'partly', 'no', 'unclear')
ALARMS = ('MISMATCH', 'MISSING')
NEGATION_CUE = re.compile(r"\b(not|never|no|nobody|nothing|none|cannot|neither|nor|nowhere|without)\b|n['`’]t\b", re.I)
NUMBER_CUE = re.compile(r'\b(\d+|zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|'
                        r'thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|'
                        r'fifty|sixty|seventy|eighty|ninety|hundred|thousand|million)\b', re.I)
STRATA = {'negation': 0.3, 'number': 0.2, 'other': 0.5}
# ASLLRP is the development domain; NCSLGR shares its annotation conventions.
CORPUS_SHARES = {'asllrp': 0.3, 'ncslgr': 0.7}


def norm(text):
    return re.sub(r'\W+', ' ', text.lower()).strip()


def group_key(source, doc_id):
    """ASLLRP documents are DAI collections; NCSLGR files of one story or session share a key."""
    if source != 'ncslgr':
        return f'asllrp:{doc_id}'
    key = re.sub(r'(?:_\d+)*_?(?:master|slave\d*)?_small(?:_\d+)?$', '', doc_id)
    key = re.sub(r'_\d+$', '', key)
    return f'ncslgr:{key}'


def stratum(english):
    if NEGATION_CUE.search(english):
        return 'negation'
    if NUMBER_CUE.search(english):
        return 'number'
    return 'other'


class _Groups:
    def __init__(self):
        self.parent = {}

    def find(self, x):
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        self.parent[self.find(a)] = self.find(b)


def load_rows(data):
    data = Path(data)
    rows = []
    for name in ASLLRP_FILES + NCSLGR_FILES:
        path = data / name
        if not path.exists():
            raise ValueError(f'Missing corpus file: {path}')
        for r in read_jsonl(path):
            if r.get('text', '').strip() and r.get('gloss', '').strip():
                rows.append({**r, 'file': name, 'group': group_key(r.get('source'), r['doc_id'])})
    return rows


def _dai_documents(folder):
    paths = sorted(glob.glob(str(Path(folder) / '*.xml')))
    for path in paths:
        yield Path(path).read_text(encoding='utf-8', errors='replace')
    if paths:
        return
    for path in sorted(glob.glob(str(Path(folder) / '*.zip'))):
        with zipfile.ZipFile(path) as z:
            for name in z.namelist():
                if name.endswith('.xml'):
                    yield z.read(name).decode('utf-8', errors='replace')


def asllrp_nmm(folder):
    """Normalized utterance translation -> annotated negation/topic (SignStream XML)."""
    out = {}
    for document in _dai_documents(folder):
        for utt in ET.fromstring(document).iter('UTTERANCE'):
            el = utt.find('TRANSLATION')
            text = '' if el is None or el.text is None else el.text.strip().strip("'").strip()
            labels = {(n.findtext('LABEL') or '').strip() for n in utt.iter('NON_MANUAL')}
            if text:
                out[norm(text)] = {'negation': 'negative' in labels, 'topic': 'topic/focus' in labels}
    return out


def ncslgr_nmm(folder):
    """Normalized English translation -> overlap with the negative and topic/focus tiers (ELAN)."""
    out = {}
    for path in sorted(Path(folder).glob('*.eaf')):
        root = ET.fromstring(path.read_text(encoding='utf-8', errors='replace'))
        slots = {}
        order = root.find('TIME_ORDER')
        for i, ts in enumerate(order.findall('TIME_SLOT') if order is not None else []):
            value = ts.get('TIME_VALUE')
            slots[ts.get('TIME_SLOT_ID')] = int(value) if value is not None else i

        def tier(name):
            spans = []
            for t in root.findall('TIER'):
                if t.get('TIER_ID') == name:
                    for a in t.iter('ALIGNABLE_ANNOTATION'):
                        s, e = a.get('TIME_SLOT_REF1'), a.get('TIME_SLOT_REF2')
                        value = (a.findtext('ANNOTATION_VALUE') or '').strip()
                        if s in slots and e in slots and value:
                            spans.append((slots[s], slots[e], value))
            return spans
        negative, topic = tier('negative'), tier('topic/focus')
        for s, e, text in tier('English translation'):
            out[norm(text)] = {'negation': any(a < e and b > s for a, b, _ in negative),
                               'topic': any(a < e and b > s for a, b, _ in topic)}
    return out


def build(data, out, manifest_path, seed=VERSION, target=150, per_group_cap=12,
          development_files=DEVELOPMENT_FILES):
    data, out = Path(data), Path(out)
    if out.exists():
        raise ValueError(f'Output directory already exists: {out}')
    rows = load_rows(data)
    development = [r for name in development_files for r in read_jsonl(data / name)]
    dev_text = {norm(r['text']) for r in development}
    groups = _Groups()
    by_text = defaultdict(set)
    for r in rows:
        groups.find(r['group'])
        by_text[norm(r['text'])].add(r['group'])
    for members in by_text.values():
        first, *rest = sorted(members)
        for other in rest:
            groups.union(first, other)
    touched = {groups.find(group_key(r.get('source'), r['doc_id'])) for r in development}
    touched |= {groups.find(g) for t, members in by_text.items() if t in dev_text for g in members}
    reserved = sorted({r['group'] for r in rows if groups.find(r['group']) not in touched})
    reserved_set = set(reserved)
    candidates, seen = [], set()
    for r in sorted(rows, key=lambda r: (r['group'], r['doc_id'], r.get('sent_idx', 0), r['file'])):
        t = norm(r['text'])
        if r['group'] not in reserved_set or t in seen or t in dev_text:
            continue
        seen.add(t)
        if 3 <= len(r['text'].split()) <= 40:
            candidates.append(r)
    rng = random.Random(seed)
    chosen = _sample(candidates, rng, target, per_group_cap)
    nmm = {'asllrp': asllrp_nmm(data / 'dai'), 'ncslgr': ncslgr_nmm(data / 'raw' / 'ncslgr' / 'elanBUcorpus')}
    chosen.sort(key=lambda r: (r['group'], r['doc_id'], r.get('sent_idx', 0)))
    pairs, refs = [], []
    for i, r in enumerate(chosen, 1):
        corpus = 'ncslgr' if r.get('source') == 'ncslgr' else 'asllrp'
        pid = f'{VERSION}-{i:04d}'
        pairs.append({'id': pid, 'english': r['text'], 'reference_gloss': r['gloss'],
                      'gloss_nmm': nmm[corpus].get(norm(r['text'])), 'corpus': corpus,
                      'doc_id': r['doc_id'], 'source_group': r['group'], 'stratum': stratum(r['text']),
                      'provenance': {'kind': 'heldout_reference', 'version': VERSION, 'file': r['file']}})
        refs.append({'pair_id': pid, 'system': 'reference', 'gloss': r['gloss'],
                     'gloss_nmm': pairs[-1]['gloss_nmm']})
    out.mkdir(parents=True)
    write_jsonl(out / 'pairs.jsonl', pairs)
    candidates_out = _with_item_ids(refs, seed)
    write_jsonl(out / 'candidates.jsonl', candidates_out)
    manifest = {
        'version': VERSION, 'seed': seed, 'target': target, 'per_group_cap': per_group_cap,
        'strata_shares': STRATA, 'corpus_shares': CORPUS_SHARES, 'n_pairs': len(pairs),
        'by_corpus': dict(Counter(p['corpus'] for p in pairs)),
        'by_stratum': dict(Counter(p['stratum'] for p in pairs)),
        'with_nmm': sum(p['gloss_nmm'] is not None for p in pairs),
        'n_sampled_groups': len({p['source_group'] for p in pairs}),
        'reserved_groups': reserved,
        'n_reserved_sentences': sum(r['group'] in reserved_set for r in {norm(x['text']): x for x in rows}.values()),
        'development_files': list(development_files),
        'pairs_sha256': file_hash(out / 'pairs.jsonl'),
        'candidates_sha256': file_hash(out / 'candidates.jsonl'),
        'input_sha256': {name: file_hash(data / name) for name in ASLLRP_FILES + NCSLGR_FILES},
        'code_sha256': file_hash(Path(__file__)),
        'rule': ('Reserved groups share no document, story or English sentence with any development file. '
                 'Never use reserved groups for rule, lexicon or prompt development. Score each frozen '
                 'checker version once; changes after scoring need a new held-out version.'),
    }
    write_json(out / 'manifest.json', manifest)
    if manifest_path:
        write_json(manifest_path, manifest)
    return manifest


def _sample(candidates, rng, target, per_group_cap):
    """Stratify by corpus, then by surface cue; spread over groups with a per-group cap.

    Corpora with few reserved groups get a larger cap so they can still meet their quota.
    Strata come from simple English cues, never from checker output.
    """
    corpus_of = lambda r: 'ncslgr' if r.get('source') == 'ncslgr' else 'asllrp'
    chosen, per_group = [], Counter()
    picked = set()
    for corpus, share in CORPUS_SHARES.items():
        rows = [r for r in candidates if corpus_of(r) == corpus]
        n_groups = len({r['group'] for r in rows}) or 1
        quota = round(target * share)
        cap = max(per_group_cap, math.ceil(quota / n_groups))
        pools = {s: [r for r in rows if stratum(r['text']) == s] for s in STRATA}
        for pool in pools.values():
            rng.shuffle(pool)
        got = 0
        for s in sorted(STRATA, key=lambda s: len(pools[s])):  # rare strata first
            want = round(quota * STRATA[s])
            for r in pools[s]:
                if want <= 0 or got >= quota:
                    break
                if per_group[r['group']] < cap:
                    chosen.append(r)
                    picked.add(id(r))
                    per_group[r['group']] += 1
                    want -= 1
                    got += 1
        rest = [r for r in rows if id(r) not in picked]
        rng.shuffle(rest)
        for r in rest:  # fill this corpus's unused stratum quota
            if got >= quota:
                break
            if per_group[r['group']] < cap:
                chosen.append(r)
                picked.add(id(r))
                per_group[r['group']] += 1
                got += 1
    rest = [r for r in candidates if id(r) not in picked]
    rng.shuffle(rest)
    for r in rest:  # a corpus short of material leaves room for the other
        if len(chosen) >= target:
            break
        if per_group[r['group']] < per_group_cap:
            chosen.append(r)
            picked.add(id(r))
            per_group[r['group']] += 1
    return chosen


def _item_id(seed, pair_id, system):
    return hashlib.sha256(f'{seed}|{pair_id}|{system}'.encode()).hexdigest()[:10]


def _with_item_ids(candidates, seed):
    return [{**c, 'item_id': c.get('item_id') or _item_id(seed, c['pair_id'], c['system'])} for c in candidates]


def reserved_groups(manifest_path):
    path = Path(manifest_path)
    return set(json.loads(path.read_text(encoding='utf-8'))['reserved_groups']) if path.exists() else set()


def assert_not_reserved(rows, manifest_path):
    """Raise if development rows come from a reserved held-out document or story."""
    reserved = reserved_groups(manifest_path)
    hits = sorted({group_key(r.get('source'), r['doc_id']) for r in rows if r.get('doc_id')} & reserved)
    if hits:
        raise ValueError(f'{len(hits)} reserved held-out groups in development data, e.g. {hits[0]}')


def add_candidates(heldout, predictions, system, out, seed=VERSION, candidates=None):
    """Attach one saved translation per English sentence; unmatched sentences stay listed."""
    heldout, out = Path(heldout), Path(out)
    if out.exists():
        raise ValueError(f'Output file already exists: {out}')
    if system == 'reference':
        raise ValueError('The system name "reference" is reserved')
    pairs = {norm(p['english']): p for p in read_jsonl(heldout / 'pairs.jsonl')}
    existing = read_jsonl(heldout / 'candidates.jsonl') if candidates is None else read_jsonl(candidates)
    added, unmatched = [], set(pairs)
    for r in read_jsonl(predictions):
        english = r.get('source') or r.get('english')
        gloss = r.get('hypothesis') if 'hypothesis' in r else r.get('gloss')
        p = pairs.get(norm(english or ''))
        if p is None or not isinstance(gloss, str):
            continue
        unmatched.discard(norm(english))
        nmm = r.get('nmm') if isinstance(r.get('nmm'), dict) else r.get('gloss_nmm')
        added.append({'pair_id': p['id'], 'system': system, 'gloss': gloss,
                      'gloss_nmm': nmm if isinstance(nmm, dict) else None,
                      'source_file_sha256': file_hash(predictions)})
    if not added:
        raise ValueError('No prediction matched a held-out English sentence')
    write_jsonl(out, existing + _with_item_ids(added, seed))
    return {'added': len(added), 'pairs_without_candidate': len(unmatched)}


def _nmm_text(nmm):
    if not nmm:
        return '(not supplied)'
    return ', '.join(f'{k}={"yes" if v else "no"}' for k, v in sorted(nmm.items()))


def sheets(heldout, out, annotators=('A', 'B'), seed=VERSION, candidates=None):
    """Blind sheets, one per annotator, each in its own order; key.csv stays with the coordinator."""
    heldout, out = Path(heldout), Path(out)
    if out.exists():
        raise ValueError(f'Output directory already exists: {out}')
    pairs = {p['id']: p for p in read_jsonl(heldout / 'pairs.jsonl')}
    items = read_jsonl(candidates or heldout / 'candidates.jsonl')
    out.mkdir(parents=True)
    fields = ['item_id', 'english', 'gloss', 'nonmanual_markers'] + list(CHECKS) + ['meaning_preserved', 'notes']
    for name in annotators:
        order = list(items)
        random.Random(f'{seed}|{name}').shuffle(order)
        with (out / f'sheet-{name}.csv').open('w', encoding='utf-8-sig', newline='') as f:
            w = csv.DictWriter(f, fields)
            w.writeheader()
            for c in order:
                w.writerow({'item_id': c['item_id'], 'english': pairs[c['pair_id']]['english'],
                            'gloss': c['gloss'], 'nonmanual_markers': _nmm_text(c['gloss_nmm'])})
    with (out / 'key.csv').open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, ['item_id', 'pair_id', 'system'])
        w.writeheader()
        for c in items:
            w.writerow({k: c[k] for k in ('item_id', 'pair_id', 'system')})
    return {'items': len(items), 'annotators': list(annotators)}


def _read_sheet(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
    out = {}
    for r in rows:
        labels = {k: (r.get(k) or '').strip().lower() for k in CHECKS}
        bad = {k: v for k, v in labels.items() if v not in LABELS}
        meaning = (r.get('meaning_preserved') or '').strip().lower()
        if bad or meaning not in MEANING:
            raise ValueError(f'{path}: item {r.get("item_id")} has missing or invalid labels {bad or meaning!r}')
        out[r['item_id']] = {'labels': labels, 'meaning_preserved': meaning, 'notes': r.get('notes', '')}
    return out


def collapse(label):
    return 'unclear' if label == 'unclear' else 'error' if label in ERROR_LABELS else 'no_error'


def kappa(a, b):
    n = len(a)
    if not n:
        return None
    observed = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    expected = sum(ca[k] * cb[k] for k in ca) / (n * n)
    return None if expected == 1 else round((observed - expected) / (1 - expected), 4)


def adjudicate(key, sheet_paths, out, resolved=None):
    """Agreement statistics, a disagreement sheet and, once resolved, gold.jsonl."""
    out = Path(out)
    if out.exists():
        raise ValueError(f'Output directory already exists: {out}')
    if len(sheet_paths) != 2:
        raise ValueError('Adjudication needs exactly two completed sheets')
    with Path(key).open(encoding='utf-8-sig', newline='') as f:
        keys = {r['item_id']: r for r in csv.DictReader(f)}
    a, b = (_read_sheet(p) for p in sheet_paths)
    if set(a) != set(keys) or set(b) != set(keys):
        raise ValueError('Both sheets must label exactly the items in key.csv')
    fixes = {}
    if resolved:
        with Path(resolved).open(encoding='utf-8-sig', newline='') as f:
            for r in csv.DictReader(f):
                final = (r.get('final') or '').strip().lower()
                if final:
                    if final not in LABELS:
                        raise ValueError(f'Invalid adjudicated label {final!r} for {r["item_id"]}')
                    fixes[r['item_id'], r['field']] = final
    stats, disagreements, gold, unresolved = {}, [], [], 0
    for field in CHECKS:
        la = [a[i]['labels'][field] for i in sorted(keys)]
        lb = [b[i]['labels'][field] for i in sorted(keys)]
        stats[field] = {'n': len(la), 'exact_agreement': round(sum(x == y for x, y in zip(la, lb)) / len(la), 4),
                        'kappa_error_vs_no_error': kappa([collapse(x) for x in la], [collapse(x) for x in lb])}
    for i in sorted(keys):
        labels = {}
        for field in CHECKS:
            x, y = a[i]['labels'][field], b[i]['labels'][field]
            if x == y:
                labels[field] = x
            elif (i, field) in fixes:
                labels[field] = fixes[i, field]
            else:
                labels[field] = None
                unresolved += 1
                disagreements.append({'item_id': i, 'field': field, 'annotator_1': x, 'annotator_2': y,
                                      'notes_1': a[i]['notes'], 'notes_2': b[i]['notes'], 'final': ''})
        gold.append({'item_id': i, 'pair_id': keys[i]['pair_id'], 'system': keys[i]['system'], 'labels': labels,
                     'meaning_preserved': [a[i]['meaning_preserved'], b[i]['meaning_preserved']]})
    out.mkdir(parents=True)
    write_json(out / 'agreement.json', {'fields': stats, 'items': len(keys), 'unresolved': unresolved,
                                        'sheets_sha256': [file_hash(p) for p in sheet_paths]})
    with (out / 'disagreements.csv').open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, ['item_id', 'field', 'annotator_1', 'annotator_2', 'notes_1', 'notes_2', 'final'])
        w.writeheader()
        w.writerows(disagreements)
    if not unresolved:
        write_jsonl(out / 'gold.jsonl', gold)
    return {'unresolved': unresolved, 'fields': stats}


def wilson(k, n, z=1.96):
    if not n:
        return None
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [round(centre - half, 4), round(centre + half, 4)]


def _git_head():
    try:
        return subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True, text=True,
                              cwd=Path(__file__).parent, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _rates(rows, alarm):
    """rows: (gold_label, status, confidence). Gold unclear is excluded and counted."""
    usable = [(g, s, c) for g, s, c in rows if g != 'unclear']
    errors = [(g, s, c) for g, s, c in usable if g in ERROR_LABELS]
    clean = [(g, s, c) for g, s, c in usable if g not in ERROR_LABELS]
    flagged = [x for x in usable if alarm(x)]
    tp = sum(alarm(x) for x in errors)
    fp = sum(alarm(x) for x in clean)
    return {'n': len(usable), 'gold_unclear_excluded': len(rows) - len(usable), 'gold_errors': len(errors),
            'alarms': len(flagged), 'true_alarms': tp, 'false_alarms': fp,
            'missed_as_UNKNOWN': sum(s == 'UNKNOWN' for _, s, _ in errors),
            'missed_as_MATCH': sum(s == 'MATCH' for _, s, _ in errors),
            'precision': round(tp / len(flagged), 4) if flagged else None,
            'precision_95ci': wilson(tp, len(flagged)),
            'recall': round(tp / len(errors), 4) if errors else None, 'recall_95ci': wilson(tp, len(errors)),
            'false_alarm_rate': round(fp / len(clean), 4) if clean else None,
            'false_alarm_rate_95ci': wilson(fp, len(clean)),
            'coverage': round(sum(s != 'UNKNOWN' for _, s, _ in usable) / len(usable), 4) if usable else None}


def score(heldout, gold_path, manifest_path, out, candidates_path=None):
    """Score the current checker once against adjudicated labels; verifies the sealed set."""
    from .compare import check_pair
    from .baselines import sign_f1
    from .natural import extraction_configuration
    heldout, out = Path(heldout), Path(out)
    if out.exists():
        raise ValueError(f'Output directory already exists: {out}')
    manifest = json.loads(Path(manifest_path).read_text(encoding='utf-8'))
    if file_hash(heldout / 'pairs.jsonl') != manifest['pairs_sha256']:
        raise ValueError('pairs.jsonl differs from the sealed manifest; refusing to score')
    pairs = {p['id']: p for p in read_jsonl(heldout / 'pairs.jsonl')}
    candidates = {c['item_id']: c for c in read_jsonl(candidates_path or heldout / 'candidates.jsonl')}
    gold = read_jsonl(gold_path)
    records, table = [], defaultdict(lambda: defaultdict(list))
    for g in gold:
        c, p = candidates[g['item_id']], pairs[g['pair_id']]
        result = check_pair(p['english'], c['gloss'], c.get('gloss_nmm'))
        record = {'item_id': g['item_id'], 'pair_id': p['id'], 'system': c['system'],
                  'gold': g['labels'], 'checks': {k: {x: v.get(x) for x in ('status', 'confidence', 'reason')}
                                                  for k, v in result['checks'].items()},
                  'sign_f1_vs_reference': None if c['system'] == 'reference'
                  else sign_f1(c['gloss'], p['reference_gloss'])}
        records.append(record)
        for field in CHECKS:
            check = result['checks'][field]
            for system in (c['system'], 'all'):
                table[system][field].append((g['labels'][field], check['status'], check.get('confidence')))
    any_alarm = lambda x: x[1] in ALARMS
    high_alarm = lambda x: x[1] in ALARMS and x[2] != 'low'
    report = {'systems': {}, 'checker': {'git_head': _git_head(), 'extraction': extraction_configuration()},
              'pairs_sha256': manifest['pairs_sha256'], 'gold_sha256': file_hash(gold_path),
              'interpretation': ('Alarm = MISMATCH or MISSING. Recall counts UNKNOWN and MATCH as misses. '
                                 'False-alarm rate uses items whose adjudicated label is ok or na.')}
    for system, fields in table.items():
        report['systems'][system] = {field: {'all_alarms': _rates(rows, any_alarm),
                                             'high_confidence_alarms': _rates(rows, high_alarm)}
                                     for field, rows in fields.items()}
    out.mkdir(parents=True)
    write_jsonl(out / 'records.jsonl', records)
    write_json(out / 'report.json', report)
    return report


def register(sub):
    p = sub.add_parser('heldout', help='Sealed document-held-out set for human fact labels')
    h = p.add_subparsers(dest='heldout_command', required=True)
    b = h.add_parser('build')
    b.add_argument('--data', type=Path, required=True, help='Folder with processed/, dai/ and raw/ncslgr/')
    b.add_argument('--out', type=Path, required=True, help='New private output folder')
    b.add_argument('--manifest', type=Path, default=None, help='Also write the public manifest here')
    b.add_argument('--seed', default=VERSION)
    b.add_argument('--target', type=int, default=150)
    b.add_argument('--per-group-cap', type=int, default=12)
    a = h.add_parser('add-candidates')
    a.add_argument('heldout', type=Path)
    a.add_argument('--predictions', type=Path, required=True)
    a.add_argument('--system', required=True)
    a.add_argument('--out', type=Path, required=True, help='New candidates.jsonl path')
    a.add_argument('--candidates', type=Path, default=None, help='Existing candidates file to extend')
    s = h.add_parser('sheets')
    s.add_argument('heldout', type=Path)
    s.add_argument('--out', type=Path, required=True)
    s.add_argument('--annotator', action='append', default=None)
    s.add_argument('--candidates', type=Path, default=None, help='Candidates file from add-candidates')
    j = h.add_parser('adjudicate')
    j.add_argument('--key', type=Path, required=True)
    j.add_argument('--sheet', type=Path, action='append', required=True)
    j.add_argument('--resolved', type=Path, default=None)
    j.add_argument('--out', type=Path, required=True)
    c = h.add_parser('score')
    c.add_argument('heldout', type=Path)
    c.add_argument('--gold', type=Path, required=True)
    c.add_argument('--manifest', type=Path, required=True)
    c.add_argument('--out', type=Path, required=True)
    c.add_argument('--candidates', type=Path, default=None)


def dispatch(args):
    cmd = args.heldout_command
    if cmd == 'build':
        m = build(args.data, args.out, args.manifest, args.seed, args.target, args.per_group_cap)
        print(f"Sealed {m['n_pairs']} pairs from {m['n_sampled_groups']} held-out groups "
              f"({m['by_corpus']}); {len(m['reserved_groups'])} groups reserved. Keep {args.out} private.")
    elif cmd == 'add-candidates':
        r = add_candidates(args.heldout, args.predictions, args.system, args.out, candidates=args.candidates)
        print(f"Added {r['added']} candidates; {r['pairs_without_candidate']} pairs had no matching prediction")
    elif cmd == 'sheets':
        r = sheets(args.heldout, args.out, tuple(args.annotator or ('A', 'B')), candidates=args.candidates)
        print(f"Wrote blind sheets for {r['annotators']} with {r['items']} items each; keep key.csv away from annotators")
    elif cmd == 'adjudicate':
        r = adjudicate(args.key, args.sheet, args.out, args.resolved)
        print(json.dumps(r, indent=2))
    elif cmd == 'score':
        r = score(args.heldout, args.gold, args.manifest, args.out, args.candidates)
        print(json.dumps({s: {f: v['all_alarms'] for f, v in fields.items()} for s, fields in r['systems'].items()},
                         indent=2))
    return 0
