"""Architecture experiment: rule readers vs model readers vs hybrid vs direct judge.

Development data only (ASLLRP dev files via the scenario harness; held-out groups refused).
Outputs go to private/ because they contain corpus text.

  python experiments/architecture/run.py sample --data ../sign_language_gen/data --out private/architecture/sample.jsonl
  python experiments/architecture/run.py models --sample ... --cache private/architecture/cache.jsonl --model qwen3:4b
  python experiments/architecture/run.py score --sample ... --cache ... --out private/architecture/results-01
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import random
import re
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path[:0] = [str(HERE), str(HERE.parent / 'scenario-testing'), str(ROOT)]

import prompts as P  # noqa: E402

CHECKS = P.CHECKS
FLAGS = ('MISMATCH', 'MISSING')
OPS = ['control_unchanged', 'control_negation_by_headshake_only', 'negation_dropped', 'negation_added_sign',
       'negation_added_nonmanual', 'entity_swapped', 'action_swapped', 'number_changed', 'number_dropped']
QUOTA = {'number_changed': 8, 'number_dropped': 6, 'negation_dropped': 12, 'control_negation_by_headshake_only': 6,
         'entity_swapped': 15, 'action_swapped': 15, 'negation_added_sign': 12}
PROMPT_VERSION = hashlib.sha256((P.ENGLISH + P.GLOSS + P.JUDGE).encode()).hexdigest()[:10]


def configure_lexicons(data):
    from signir.lexicon import configure, BUILTIN
    d = Path(data)
    configure([BUILTIN, str(d / 'processed/asllrp/gloss_dictionary_merged_translations.json'),
               str(d / 'export/signbank_translations_2026_08_02.lexical.json')])


# --- sample --------------------------------------------------------------------

def cmd_sample(args):
    import run_scenarios as rs
    configure_lexicons(args.data)
    rows, _ = rs.load(args.data)
    rows = [r for r in rows if r['cohort'] == 'asllrp_human' and r['gloss_nmm'] is not None]
    ops = {**rs.ERRORS, **rs.CONTROLS}
    applicable = []
    for r in rows:
        made = {}
        for name in OPS:
            out = ops[name](r, r['gloss'].split())
            if out:
                made[name] = {'gloss': out[0], 'target': out[1], 'nmm': out[2]}
        applicable.append((r, made))
    random.Random(args.seed).shuffle(applicable)
    chosen, counts = [], Counter()
    for op, quota in QUOTA.items():  # rare operations first
        for r, made in applicable:
            if counts[op] >= quota or len(chosen) >= args.refs:
                break
            if op in made and all(r['id'] != c[0]['id'] for c in chosen):
                chosen.append((r, made))
                counts.update(k for k in made if k in QUOTA)
    for r, made in applicable:  # fill with plain references (false-alarm denominator)
        if len(chosen) >= args.refs:
            break
        if all(r['id'] != c[0]['id'] for c in chosen):
            chosen.append((r, made))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    if args.out.exists():
        raise SystemExit('Sample file must be new')
    n = 0
    with open(args.out, 'w', encoding='utf-8') as f:
        for r, made in chosen:
            for op, v in made.items():
                f.write(json.dumps({'ref': r['id'], 'doc_id': r['doc_id'], 'op': op, 'target': v['target'],
                                    'english': r['english'], 'reference': r['gloss'], 'gloss': v['gloss'],
                                    'nmm': v['nmm']}, ensure_ascii=False) + '\n')
                n += 1
    print(json.dumps({'references': len(chosen), 'pairs': n,
                      'ops': Counter(json.loads(l)['op'] for l in open(args.out, encoding='utf-8'))}, indent=1))


def load_sample(path):
    return [json.loads(l) for l in open(path, encoding='utf-8')]


# --- model calls -----------------------------------------------------------------

def key(model, task, payload):
    return hashlib.sha256(json.dumps([PROMPT_VERSION, model, task, payload], sort_keys=True).encode()).hexdigest()


def requests_for(sample, tasks):
    seen = set()
    for s in sample:
        items = []
        if 'english' in tasks:
            items.append(('english', {'text': s['english']}))
        if 'gloss' in tasks:
            items.append(('gloss', {'text': s['gloss']}))
        if 'judge' in tasks:
            items.append(('judge', {'english': s['english'], 'gloss': s['gloss'],
                                    'head_shake': (s['nmm'] or {}).get('negation')}))
        for task, payload in items:
            k = (task, json.dumps(payload, sort_keys=True))
            if k not in seen:
                seen.add(k)
                yield task, payload


def messages(task, payload):
    system = {'english': P.ENGLISH, 'gloss': P.GLOSS, 'judge': P.JUDGE}[task]
    user = payload['text'] if task != 'judge' else json.dumps(payload, ensure_ascii=False)
    return [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}]


def cmd_models(args):
    from ollama import chat
    sample = load_sample(args.sample)
    if args.refs:
        keep = list(dict.fromkeys(s['ref'] for s in sample))[:args.refs]
        sample = [s for s in sample if s['ref'] in keep]
    done = set()
    if args.cache.exists():
        done = {json.loads(l)['key'] for l in open(args.cache, encoding='utf-8')}
    schema = {'english': P.ENGLISH_SCHEMA, 'gloss': P.GLOSS_SCHEMA, 'judge': P.JUDGE_SCHEMA}
    todo = [(t, p) for t, p in requests_for(sample, args.tasks.split(',')) if key(args.model, t, p) not in done]
    print(f'{len(todo)} calls to make', flush=True)
    args.cache.parent.mkdir(parents=True, exist_ok=True)
    for i, (task, payload) in enumerate(todo, 1):
        try:
            r = chat(args.model, messages(task, payload), schema[task])
        except Exception as e:  # recorded as a failure, never retried
            r = {'text': None, 'error': f'{type(e).__name__}: {e}'}
        with open(args.cache, 'a', encoding='utf-8') as f:
            f.write(json.dumps({'key': key(args.model, task, payload), 'model': args.model, 'task': task,
                                'payload': payload, **r}, ensure_ascii=False) + '\n')
        print(i, task, r.get('seconds'), r.get('error', ''), flush=True)


def load_cache(paths):
    out = {}
    for path in paths:
        for l in open(path, encoding='utf-8'):
            c = json.loads(l)
            out[c['key']] = c
    return out


# --- model-reader parsing and comparison ------------------------------------------

def forms(word):
    w = word.lower().strip()
    out = {w}
    if w.endswith('ies') and len(w) > 4:
        out.add(w[:-3] + 'y')
    if w.endswith('es') and len(w) > 3:
        out.add(w[:-2])
    if w.endswith('s') and len(w) > 3:
        out.add(w[:-1])
    return out


def family(words):
    from signir.natural import word_family
    out = set()
    for w in words:
        for f in forms(w):
            out |= word_family([f])
    return out


def grounded(quote, text, fold):
    return bool(quote) and ((quote.lower() in text.lower()) if fold else (quote in text))


def parse_reader(cell, text, task, strict):
    """Returns (parsed, problem). strict: any ungrounded quote fails the record; else drop the item."""
    if cell is None or cell.get('text') is None:
        return None, 'call_failed'
    if cell.get('truncated'):
        return None, 'truncated'
    try:
        d = json.loads(cell['text'])
    except json.JSONDecodeError:
        return None, 'bad_json'
    fold = task == 'english'
    lists = ('entities', 'predicates', 'numbers') if task == 'english' else ('signs', 'numbers')
    bad = 0
    for name in lists:
        kept = [x for x in d.get(name, []) if grounded(x.get('quote'), text, fold)]
        bad += len(d.get(name, [])) - len(kept)
        d[name] = kept
    if bad and strict:
        return None, 'ungrounded'
    d['_ungrounded'] = bad
    return d, None


def compare_readers(e, g, nmm):
    """Same policy as the rule checker, on model-read facts. Roles are out of scope (UNKNOWN)."""
    meanings = set()
    for s in g['signs']:
        meanings |= family(s.get('meanings', []) + [re.sub(r'^(fs-|ns-|#)', '', s['quote']).lower()])
    out = {'roles': 'UNKNOWN'}
    ents = [x['lemma'] for x in e['entities'] if x.get('lemma')]
    if not ents:
        out['entities'] = 'UNKNOWN'
    else:
        out['entities'] = 'MISSING' if any(not (family([w]) & meanings) for w in ents) else 'MATCH'
    preds = [x['lemma'] for x in e['predicates'] if x.get('main') and x.get('lemma')]
    preds = [w for w in preds if w not in ('be', 'have', 'do')]
    if not preds:
        out['action'] = 'UNKNOWN'
    else:
        out['action'] = 'MISSING' if any(not (family([w]) & meanings) for w in preds) else 'MATCH'
    gneg = g.get('negation') or any(s['kind'] == 'negation' for s in g['signs'])
    shake = (nmm or {}).get('negation')
    if e.get('negated'):
        out['negation'] = 'MATCH' if gneg or shake else ('MISSING' if shake is False else 'UNKNOWN')
    else:
        out['negation'] = 'MISMATCH' if gneg or shake else 'MATCH'
    evals = {x['value'] for x in e['numbers']}
    gvals = {x['value'] for x in g['numbers']}
    if not evals:
        out['numbers'] = 'UNKNOWN'
    elif evals <= gvals:
        out['numbers'] = 'MATCH'
    else:
        out['numbers'] = 'MISMATCH' if gvals - evals else 'MISSING'
    return out


def parse_judge(cell):
    if cell is None or cell.get('text') is None:
        return None, 'call_failed'
    if cell.get('truncated'):
        return None, 'truncated'
    try:
        d = json.loads(cell['text'])
        return {k: d[k]['status'] for k in CHECKS}, None
    except (json.JSONDecodeError, KeyError, TypeError):
        return None, 'bad_json'


# --- embedding matcher -------------------------------------------------------------

_EMB = {}


def embed_all(words):
    from ollama import embed
    import urllib.error
    new = sorted({w for w in words if w not in _EMB})
    for i in range(0, len(new), 256):
        batch = new[i:i + 256]
        try:
            vectors = embed(batch)
        except urllib.error.HTTPError:
            vectors = []
            for w in batch:  # find the rejected word(s); they get no vector (never matched)
                try:
                    vectors.append(embed([w])[0])
                except urllib.error.HTTPError as e:
                    print('embedding rejected:', repr(w), e.read()[:120], file=sys.stderr)
                    vectors.append(None)
        for w, v in zip(batch, vectors):
            if v is not None:
                n = math.sqrt(sum(x * x for x in v)) or 1.0
                _EMB[w] = [x / n for x in v]


def cos(a, b):
    if a not in _EMB or b not in _EMB:
        return -1.0
    return sum(x * y for x, y in zip(_EMB[a], _EMB[b]))


def embedding_status(check, result, tau):
    """Downgrade an entity/action MISSING to MATCH when every missing item is close to some gloss sign."""
    c = result['checks'][check]
    if c['status'] != 'MISSING' or not c.get('missing'):
        return c['status'], c.get('confidence')
    items = result['english']['content'][('entities' if check == 'entities' else 'predicates')]
    words = {}
    for it in items:
        if it.get('label') in c['missing']:
            words[it['label']] = [w.lower() for w in it.get('candidates') or [it['label'].lower()]]
    signs = [w.lower() for s in result['gloss'].get('signs') or [] for w in [s['core']] + s.get('concepts', [])]
    signs = [re.sub(r'^(fs-|ns-|#)', '', w) for w in signs]
    if not signs or set(words) != set(c['missing']):
        return c['status'], c.get('confidence')
    for label, ws in words.items():
        if max(cos(w, s) for w in ws for s in signs) < tau:
            return c['status'], c.get('confidence')
    return 'MATCH', None


# --- scoring --------------------------------------------------------------------

def rate(k, n):
    return {'k': k, 'n': n, 'rate': round(k / n, 3) if n else None}


def cmd_score(args):
    from signir.compare import check_pair
    configure_lexicons(args.data)
    sample = load_sample(args.sample)
    cache = load_cache(args.cache)
    models = sorted({c['model'] for c in cache.values()})
    systems = defaultdict(dict)   # system -> (ref, op) -> {check: (status, confidence)}
    failures = Counter()
    routed = Counter()
    cost = defaultdict(lambda: defaultdict(list))
    for c in cache.values():
        if c.get('seconds'):
            cost[c['model']][c['task']].append((c['seconds'], c.get('prompt_tokens') or 0, c.get('output_tokens') or 0))
    rule_results = {}
    for s in sample:
        r = check_pair(s['english'], s['gloss'], s['nmm'])
        rule_results[s['ref'], s['op']] = r
        systems['rules'][s['ref'], s['op']] = {k: (r['checks'][k]['status'], r['checks'][k].get('confidence'))
                                                for k in CHECKS}
    words = set()
    for r in rule_results.values():
        for it in (r['english'].get('content') or {}).get('entities', []) + (r['english'].get('content') or {}).get('predicates', []):
            words |= {w.lower() for w in it.get('candidates') or [it.get('label', '').lower()]}
        for sg in r['gloss'].get('signs') or []:
            words |= {re.sub(r'^(fs-|ns-|#)', '', w.lower()) for w in [sg['core']] + sg.get('concepts', [])}
    embed_all({w for w in words if w})
    for tau in args.taus:
        name = f'rules+embed@{tau}'
        for (ref, op), r in rule_results.items():
            st = dict(systems['rules'][ref, op])
            for check in ('entities', 'action'):
                st[check] = embedding_status(check, r, tau)
            systems[name][ref, op] = st
    for model in models:
        for strict in (True, False):
            name = f'readers:{model}' + ('' if strict else ':lenient')
            for s in sample:
                ec = cache.get(key(model, 'english', {'text': s['english']}))
                gc = cache.get(key(model, 'gloss', {'text': s['gloss']}))
                if ec is None or gc is None:
                    continue
                e, pe = parse_reader(ec, s['english'], 'english', strict)
                g, pg = parse_reader(gc, s['gloss'], 'gloss', strict)
                if e is None or g is None:
                    failures[name, pe or pg] += 1
                    systems[name][s['ref'], s['op']] = {k: ('FAILED', None) for k in CHECKS}
                    continue
                systems[name][s['ref'], s['op']] = {k: (v, None) for k, v in compare_readers(e, g, s['nmm']).items()}
            # verify: the model re-reads only checks where the rules raised a low-confidence alarm.
            # fill: also checks the rules left UNKNOWN. High-confidence rule results are kept. Roles stay rules-only.
            for mode in ('verify', 'fill'):
                hyb = f'hybrid-{mode}:{model}' + ('' if strict else ':lenient')
                for (ref, op), st in systems[name].items():
                    rules = systems['rules'][ref, op]
                    out, sent = {}, False
                    for k in CHECKS:
                        status, conf = rules[k]
                        low = status in FLAGS and conf == 'low'
                        if k != 'roles' and (low or (mode == 'fill' and status == 'UNKNOWN')):
                            sent = True
                            m = st[k][0]
                            out[k] = (m, None) if m not in ('FAILED', 'UNKNOWN') else (status, conf)
                        else:
                            out[k] = (status, conf)
                    systems[hyb][ref, op] = out
                    routed[hyb, 'pairs'] += 1
                    routed[hyb, 'routed'] += sent
        name = f'judge:{model}'
        for s in sample:
            jc = cache.get(key(model, 'judge', {'english': s['english'], 'gloss': s['gloss'],
                                                 'head_shake': (s['nmm'] or {}).get('negation')}))
            if jc is None:
                continue
            j, pj = parse_judge(jc)
            if j is None:
                failures[name, pj] += 1
                systems[name][s['ref'], s['op']] = {k: ('FAILED', None) for k in CHECKS}
            else:
                systems[name][s['ref'], s['op']] = {k: (v, None) for k, v in j.items()}
    report = {'prompt_version': PROMPT_VERSION, 'sample_pairs': len(sample),
              'sample_refs': len({s['ref'] for s in sample}), 'systems': {}}
    targets = {s['op']: s['target'] for s in sample}
    for name, table in systems.items():
        refs = {ref for ref, op in table if op == 'control_unchanged'}
        entry = {'pairs_scored': len(table), 'references_scored': len(refs)}
        base = {ref: table[ref, 'control_unchanged'] for ref in refs}
        fa = {}
        for k in CHECKS:
            fa[k] = rate(sum(base[r][k][0] in FLAGS for r in refs), len(refs))
            fa[k + ':high'] = rate(sum(base[r][k][0] in FLAGS and base[r][k][1] != 'low' for r in refs), len(refs))
        fa['any'] = rate(sum(any(base[r][k][0] in FLAGS for k in CHECKS) for r in refs), len(refs))
        fa['any:high'] = rate(sum(any(base[r][k][0] in FLAGS and base[r][k][1] != 'low' for k in CHECKS) for r in refs), len(refs))
        entry['false_alarms_on_references'] = fa
        det, ctrl = {}, {}
        for op in OPS:
            pairs = [(ref, o) for ref, o in table if o == op and ref in base]
            if op.startswith('control'):
                if op != 'control_unchanged':
                    new = sum(any(table[p][k][0] in FLAGS and base[p[0]][k][0] not in FLAGS for k in CHECKS) for p in pairs)
                    ctrl[op] = rate(new, len(pairs))
                continue
            t = targets[op]
            eligible = [p for p in pairs if base[p[0]][t][0] not in FLAGS]
            det[op] = rate(sum(table[p][t][0] in FLAGS for p in eligible), len(eligible))
            det[op + ':high'] = rate(sum(table[p][t][0] in FLAGS and table[p][t][1] != 'low' for p in eligible), len(eligible))
            det[op + ':failed'] = sum(table[p][t][0] == 'FAILED' for p in eligible)
        entry['detection_new_alarm_on_target'] = det
        entry['controls_new_alarms'] = ctrl
        report['systems'][name] = entry
    report['failures'] = {f'{a}:{b}': n for (a, b), n in failures.items()}
    report['hybrid_routed_share'] = {h: rate(routed[h, 'routed'], routed[h, 'pairs'])
                                     for h in {h for h, _ in routed}}
    report['cost_per_call'] = {m: {t: {'calls': len(v), 'mean_seconds': round(sum(x[0] for x in v) / len(v), 1),
                                       'mean_prompt_tokens': round(sum(x[1] for x in v) / len(v)),
                                       'mean_output_tokens': round(sum(x[2] for x in v) / len(v))}
                                   for t, v in tasks.items()} for m, tasks in cost.items()}
    args.out.mkdir(parents=True)
    (args.out / 'report.json').write_text(json.dumps(report, indent=1) + '\n', encoding='utf-8')
    with open(args.out / 'pairs.jsonl', 'w', encoding='utf-8') as f:
        for s in sample:
            f.write(json.dumps({**s, 'systems': {n: {k: v[k][0] for k in CHECKS}
                                                 for n, t in systems.items() if (v := t.get((s['ref'], s['op'])))}},
                               ensure_ascii=False) + '\n')
    print(json.dumps(report, indent=1))


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest='cmd', required=True)
    a = sub.add_parser('sample')
    a.add_argument('--data', type=Path, required=True)
    a.add_argument('--out', type=Path, required=True)
    a.add_argument('--refs', type=int, default=45)
    a.add_argument('--seed', type=int, default=7)
    b = sub.add_parser('models')
    b.add_argument('--sample', type=Path, required=True)
    b.add_argument('--cache', type=Path, required=True)
    b.add_argument('--model', required=True)
    b.add_argument('--tasks', default='english,gloss,judge')
    b.add_argument('--refs', type=int, default=0, help='Only the first N references (subset runs)')
    c = sub.add_parser('score')
    c.add_argument('--data', type=Path, required=True)
    c.add_argument('--sample', type=Path, required=True)
    c.add_argument('--cache', type=Path, action='append', required=True)
    c.add_argument('--out', type=Path, required=True)
    c.add_argument('--taus', type=float, nargs='+', default=[0.6, 0.7, 0.8])
    args = p.parse_args()
    {'sample': cmd_sample, 'models': cmd_models, 'score': cmd_score}[args.cmd](args)


if __name__ == '__main__':
    main()
