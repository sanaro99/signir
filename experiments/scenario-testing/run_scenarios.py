"""Scenario tests for the rule checker on real reference glosses, real translator outputs and authored cases.

Parts:
  1. Reference audit: human ASLLRP and rule-generated ASLG-PC12 reference glosses are
     correct, so every MISMATCH or MISSING is a false alarm. ASLLRP references carry their
     annotated non-manual markers (negation, topic) from the SignStream files in data/dai.
  2. English negation against the adjudicated ASLLRP sentence-type labels.
  3. Corrupted references: one realistic error per copy, plus meaning-preserving controls.
  4. Authored English/gloss cases with known errors (authored_cases.jsonl), with and
     without an NMM channel that shows no negation.
  5. Optional saved translator outputs (--generated predictions.jsonl with source,
     hypothesis, reference and nmm fields): flag counts for review; no gold labels.

Corpus text stays in the output directory, which should be under ignored private/.
Usage:
  python experiments/scenario-testing/run_scenarios.py --data data --out private/scenario-testing/run-02 \
      [--gloss-lexicon data/processed/asllrp/gloss_dictionary_merged_translations.json] [--generated path ...]
"""
import argparse
from collections import Counter, defaultdict
import glob
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from signir.baselines import sign_f1, word_f1
from signir.compare import check_pair
from signir.schema import CHECKS

HERE = Path(__file__).parent
FLAGS = ('MISMATCH', 'MISSING')

# --- gloss token helpers -------------------------------------------------------

def split_token(token):
    """(prefix wrappers such as (1h), core label, trailing reduplication +)."""
    m = re.match(r'^((?:\([^)]*\))*)(.*?)(\+*)$', token)
    return m.group(1), m.group(2), m.group(3)


NUMBER_WORDS = {w: n for n, w in enumerate(
    'ZERO ONE TWO THREE FOUR FIVE SIX SEVEN EIGHT NINE TEN ELEVEN TWELVE THIRTEEN FOURTEEN '
    'FIFTEEN SIXTEEN SEVENTEEN EIGHTEEN NINETEEN TWENTY'.split())}
NUMBER_WORDS.update(dict(zip('THIRTY FORTY FIFTY SIXTY SEVENTY EIGHTY NINETY'.split(), range(30, 100, 10))))
WORD_FOR = {n: w for w, n in NUMBER_WORDS.items()}
ENGLISH_NUMBER = re.compile(r'\b(\d+|' + '|'.join(w.lower() for w in NUMBER_WORDS) + r')\b', re.I)

NEGATOR_CORES = {'NOT', 'NEVER', 'NONE/NOTHING', 'NONE', '#NO', 'NO', 'NOT-YET', 'DESC-NOT',
                 "CAN'T", "DON'T", "WON'T", 'NOTHING', 'NOBODY'}
NEG_SUFFIX = re.compile(r'\+(?:\([^)]*\))?NEG$')
ENGLISH_NEGATION = re.compile(r"\b(not|never|no|nobody|nothing|none|cannot|neither|nor|nowhere)\b|n['`]t\b", re.I)

VERBS = set('''WANT LIKE KNOW HAVE GO GO-OUT EAT ARRIVE MAKE LOOK START FEEL WORK SEE GIVE TAKE
BUY SELL HELP LOVE HATE NEED UNDERSTAND THINK TELL SAY ASK LEARN TEACH READ WRITE PLAY DRIVE
COME LEAVE MEET VISIT CALL SLEEP DRINK SIT STAND WALK RUN OPEN CLOSE WIN LOSE REMEMBER FORGET
AGREE ACCEPT CHANGE STOP CONTINUE BECOME LIVE DIE GROW DEVELOP TRAIN STUDY USE PAY WAIT
BELIEVE DECIDE TRY FIND GET BRING SEND RECEIVE ENJOY PREFER COMPARE SUCCEED FAIL PASS
INFORM URGE OFFER SUPPORT PROTECT INCLUDE REQUIRE EXPECT HOPE DISCUSS EXPLAIN FOLLOW'''.split())
ACTION_SWAPS = {'GO': 'COME', 'COME': 'GO', 'ARRIVE': 'LEAVE', 'LEAVE': 'ARRIVE', 'BUY': 'SELL',
                'SELL': 'BUY', 'GIVE': 'TAKE', 'TAKE': 'GIVE', 'START': 'STOP', 'STOP': 'START',
                'OPEN': 'CLOSE', 'CLOSE': 'OPEN', 'WIN': 'LOSE', 'LOSE': 'WIN', 'LIKE': 'HATE',
                'LOVE': 'HATE', 'HATE': 'LIKE', 'REMEMBER': 'FORGET', 'FORGET': 'REMEMBER',
                'EAT': 'DRINK', 'DRINK': 'EAT', 'WORK': 'PLAY', 'PLAY': 'WORK', 'SEE': 'HEAR',
                'TEACH': 'LEARN', 'LEARN': 'TEACH', 'AGREE': 'DISAGREE', 'SIT': 'STAND',
                'STAND': 'SIT', 'READ': 'WRITE', 'WRITE': 'READ', 'WANT': 'REFUSE', 'HELP': 'HIT',
                'MEET': 'AVOID', 'ACCEPT': 'REJECT', 'SUCCEED': 'FAIL', 'FAIL': 'SUCCEED',
                'PASS': 'REJECT', 'SUPPORT': 'OPPOSE', 'KNOW': 'FORGET', 'NEED': 'HAVE',
                'HAVE': 'NEED', 'MAKE': 'BREAK', 'LIVE': 'DIE'}
ENTITY_SWAPS = {'MOTHER': 'FATHER', 'FATHER': 'MOTHER', 'SISTER': 'BROTHER', 'BROTHER': 'SISTER',
                'BOY': 'GIRL', 'GIRL': 'BOY', 'MAN': 'WOMAN', 'WOMAN': 'MAN', 'DOG': 'CAT',
                'CAT': 'DOG', 'SON': 'DAUGHTER', 'DAUGHTER': 'SON', 'CAR': 'BUS', 'BUS': 'CAR',
                'SCHOOL': 'HOSPITAL', 'HOME': 'SCHOOL', 'HOUSE': 'SCHOOL', 'MOVIE': 'BOOK',
                'BOOK': 'MOVIE', 'PIZZA': 'SALAD', 'COLLEGE': 'HOSPITAL', 'FRIEND': 'ENEMY',
                'GRANDMOTHER': 'GRANDFATHER', 'GRANDFATHER': 'GRANDMOTHER', 'TEACHER': 'STUDENT',
                'STUDENT': 'TEACHER', 'DOCTOR': 'LAWYER', 'PARLIAMENT': 'COMMISSION',
                'COMMISSION': 'PARLIAMENT', 'COUNCIL': 'COMMISSION', 'COUNTRY': 'CITY',
                'MONEY': 'TIME', 'PEOPLE': 'ANIMAL', 'CHILDREN': 'ADULT', 'BABY': 'DOG',
                'TEACH+AGENT': 'STUDENT', 'WATER': 'MILK', 'COFFEE': 'TEA', 'FOOD': 'MONEY'}
NAME = re.compile(r'^((?:ns-)?)(fs-[A-Z]+(?:-[A-Z])*)$')
DISCOURSE = re.compile(r'^(IX-.*|part:.*|BUOY|HOLD|QMwg|5".*|.*"(?:pause|umm|well|you know)"|QUOTE/TOPIC)$')


def core(token):
    return split_token(token)[1]


def is_negator(token):
    c = core(token)
    return c in NEGATOR_CORES or bool(NEG_SUFFIX.search(c)) or c == 'CANNOT'


def is_entity(token):
    c = core(token)
    return c in ENTITY_SWAPS or bool(NAME.match(c))


def english_negated(row):
    if row.get('gold_negation') is not None:
        return row['gold_negation']
    return bool(ENGLISH_NEGATION.search(row['english']))


def english_numbers(text):
    values = set()
    for m in ENGLISH_NUMBER.finditer(text):
        word = m.group(1)
        values.add(int(word) if word.isdigit() else NUMBER_WORDS[word.upper()])
    return values


def number_value(token):
    c = core(token)
    if re.fullmatch(r'[0-9]{1,6}', c):
        return int(c)
    return NUMBER_WORDS.get(c)


def with_nmm(row, **changes):
    if row.get('gloss_nmm') is None:
        return None
    return {**row['gloss_nmm'], **changes}

# --- mutation operators: each returns (gloss, error_check, nmm) or None ----------

def m_number_change(row, tokens):
    targets = english_numbers(row['english'])
    for i, t in enumerate(tokens):
        n = number_value(t)
        if n is not None and n in targets:
            p, c, s = split_token(t)
            new = n + 1 if n < 20 else n + 10
            label = str(new) if c.isdigit() else WORD_FOR.get(new, str(new))
            return ' '.join(tokens[:i] + [p + label + s] + tokens[i+1:]), 'numbers', row.get('gloss_nmm')


def m_number_drop(row, tokens):
    targets = english_numbers(row['english'])
    for i, t in enumerate(tokens):
        n = number_value(t)
        if n is not None and n in targets and n != 1:
            return ' '.join(tokens[:i] + tokens[i+1:]), 'numbers', row.get('gloss_nmm')


def _drop_manual_negation(tokens):
    out, changed = [], False
    for t in tokens:
        p, c, s = split_token(t)
        if c in NEGATOR_CORES:
            changed = True
            continue
        if NEG_SUFFIX.search(c):
            out.append(p + NEG_SUFFIX.sub('', c) + s)
            changed = True
        elif c == 'CANNOT':
            out.append(p + 'CAN' + s)
            changed = True
        else:
            out.append(t)
    return out if changed and out else None


def m_negation_drop(row, tokens):
    """Negation removed from both channels: no negation sign and no head-shake."""
    if not english_negated(row):
        return None
    out = _drop_manual_negation(tokens)
    if out is None:
        return None
    return ' '.join(out), 'negation', with_nmm(row, negation=False)


def c_manual_negation_removed_headshake_kept(row, tokens):
    """Valid ASL: negation shown by head-shake alone."""
    if not english_negated(row) or not (row.get('gloss_nmm') or {}).get('negation'):
        return None
    out = _drop_manual_negation(tokens)
    return (' '.join(out), None, row['gloss_nmm']) if out else None


def m_negation_add(row, tokens):
    if english_negated(row) or any(is_negator(t) for t in tokens) or (row.get('gloss_nmm') or {}).get('negation'):
        return None
    marker = 'DESC-NOT' if row.get('notation') == 'aslg_pc12' else 'NOT'
    for i, t in enumerate(tokens):
        if core(t) in VERBS:
            return ' '.join(tokens[:i] + [marker] + tokens[i:]), 'negation', row.get('gloss_nmm')


def m_negation_add_nonmanual(row, tokens):
    """A head-shake added to a positive sentence (NMM classifier error)."""
    if english_negated(row) or row.get('gloss_nmm') is None or row['gloss_nmm'].get('negation') \
            or any(is_negator(t) for t in tokens):
        return None
    return ' '.join(tokens), 'negation', with_nmm(row, negation=True)


def m_action_swap(row, tokens):
    for i, t in enumerate(tokens):
        p, c, s = split_token(t)
        if c in ACTION_SWAPS:
            return ' '.join(tokens[:i] + [p + ACTION_SWAPS[c] + s] + tokens[i+1:]), 'action', row.get('gloss_nmm')


def m_entity_swap(row, tokens):
    for i, t in enumerate(tokens):
        p, c, s = split_token(t)
        if c in ENTITY_SWAPS:
            return ' '.join(tokens[:i] + [p + ENTITY_SWAPS[c] + s] + tokens[i+1:]), 'entities', row.get('gloss_nmm')
        m = NAME.match(c)
        if m and c[-3:] != 'ZOE':
            return ' '.join(tokens[:i] + [p + m.group(1) + 'fs-ZOE' + s] + tokens[i+1:]), 'entities', row.get('gloss_nmm')


def m_entity_drop(row, tokens):
    for i, t in enumerate(tokens):
        if is_entity(t):
            out = tokens[:i] + tokens[i+1:]
            return (' '.join(out), 'entities', row.get('gloss_nmm')) if out else None


def m_role_swap(row, tokens):
    """Swap the gloss signs for the English subject and object of an active clause (subject-verb-object)."""
    result = run_check(row['english'], row['gloss'], row.get('gloss_nmm'), row.get('notation'))
    roles = (result['english'].get('content') or {}).get('roles')
    signs = result['gloss'].get('signs') or []
    if not roles:
        return None
    find = lambda words: [s['index'] for s in signs if set(words) & set(s['concepts'])]
    agents, verbs, patients = find(roles['agent']), find(roles['action']), find(roles['patient'])
    if len(agents) != 1 or len(patients) != 1 or not verbs or agents == patients:
        return None
    a, p = agents[0], patients[0]
    if not a < verbs[0] < p:
        return None
    out = list(tokens)
    out[a], out[p] = out[p], out[a]
    return ' '.join(out), 'roles', row.get('gloss_nmm')


def c_unchanged(row, tokens):
    return ' '.join(tokens), None, row.get('gloss_nmm')


def c_drop_discourse(row, tokens):
    if row.get('notation') == 'aslg_pc12':
        return None  # HOLD is a verb in English-order gloss
    out = [t for t in tokens if not DISCOURSE.match(core(t))]
    return (' '.join(out), None, row.get('gloss_nmm')) if out and len(out) != len(tokens) else None


def c_strip_wrappers(row, tokens):
    out = [split_token(t)[1] + split_token(t)[2] for t in tokens]
    return (' '.join(out), None, row.get('gloss_nmm')) if out != tokens else None


ERRORS = {'number_changed': m_number_change, 'number_dropped': m_number_drop,
          'negation_dropped': m_negation_drop, 'negation_added_sign': m_negation_add,
          'negation_added_nonmanual': m_negation_add_nonmanual,
          'action_swapped': m_action_swap, 'entity_swapped': m_entity_swap,
          'entity_dropped': m_entity_drop, 'roles_reversed': m_role_swap}
CONTROLS = {'control_unchanged': c_unchanged, 'control_drop_pointing_and_fillers': c_drop_discourse,
            'control_strip_hand_wrappers': c_strip_wrappers,
            'control_negation_by_headshake_only': c_manual_negation_removed_headshake_kept}

# --- data -----------------------------------------------------------------------

def norm(text):
    return ' '.join(text.split())


def _dai_text(el):
    return '' if el is None or el.text is None else el.text.strip().strip("'").strip()


def load_dai_nmm(folder):
    """Utterance translation -> annotated negation/topic markers (ASLLRP SignStream XML)."""
    out = {}
    for path in sorted(glob.glob(str(Path(folder) / '*.xml'))):
        root = ET.fromstring(Path(path).read_text(encoding='utf-8', errors='replace'))
        for utt in root.iter('UTTERANCE'):
            text = _dai_text(utt.find('TRANSLATION'))
            labels = {_dai_text(n.find('LABEL')) for n in utt.iter('NON_MANUAL')}
            if text:
                out[norm(text)] = {'negation': 'negative' in labels, 'topic': 'topic/focus' in labels}
    return out


def load(data):
    data = Path(data)
    processed = data / 'processed'
    gold = {}
    for line in open(processed / 'asllrp_paper' / 'nmm_gold.jsonl', encoding='utf-8'):
        g = json.loads(line)
        gold[g['source']] = g['negation']
    nmm = {'asllrp_human': load_dai_nmm(data / 'dai')}
    cohorts = {'asllrp_human': ['asllrp/test.jsonl', 'asllrp_paper/test.jsonl'],
               'aslg_pc12_rule_generated': ['test.jsonl']}
    rows, seen, matched = [], set(), Counter()
    for cohort, files in cohorts.items():
        for name in files:
            for i, line in enumerate(open(processed / name, encoding='utf-8')):
                r = json.loads(line)
                key = (r['text'], r['gloss'])
                if not r['gloss'].strip() or key in seen:
                    continue
                seen.add(key)
                markers = nmm.get(cohort, {}).get(norm(r['text']))
                matched[cohort, markers is not None] += 1
                rows.append({'id': f'{cohort}:{name}:{i}', 'cohort': cohort, 'english': r['text'],
                             'gloss': r['gloss'], 'doc_id': r.get('doc_id'), 'gloss_nmm': markers,
                             'notation': 'aslg_pc12' if cohort.startswith('aslg') else None,
                             'gold_negation': gold.get(r['text']) if cohort == 'asllrp_human' else None})
    return rows, {f'{c}:{"with" if ok else "without"}_nmm': n for (c, ok), n in matched.items()}


_CACHE = {}


def run_check(english, gloss, nmm=None, notation=None):
    key = (english, gloss, tuple(sorted((nmm or {}).items())) if nmm is not None else None, notation)
    if key not in _CACHE:
        _CACHE[key] = check_pair(english, gloss, nmm, notation)
    return _CACHE[key]


def statuses(checks):
    return {k: checks[k]['status'] for k in CHECKS}

# --- parts ----------------------------------------------------------------------

def reference_audit(rows, records):
    out = defaultdict(Counter)
    alarms = []
    for r in rows:
        checks = run_check(r['english'], r['gloss'], r['gloss_nmm'], r['notation'])['checks']
        s = statuses(checks)
        c = out[r['cohort']]
        c['pairs'] += 1
        c['any_assessed'] += any(v != 'UNKNOWN' for v in s.values())
        c['any_flag'] += any(v in FLAGS for v in s.values())
        for k, v in s.items():
            c[f'{k}:{v}'] += 1
            if v in FLAGS:
                alarms.append({'id': r['id'], 'cohort': r['cohort'], 'check': k, 'status': v,
                               'reason': checks[k]['reason'], 'english': r['english'], 'gloss': r['gloss'],
                               'nmm': r['gloss_nmm']})
        records.append({'part': 'reference', **r, 'statuses': s})
    return {k: dict(v) for k, v in out.items()}, alarms


def negation_accuracy(rows):
    confusion, errors = Counter(), []
    for r in rows:
        if r['gold_negation'] is None:
            continue
        content = run_check(r['english'], r['gloss'], r['gloss_nmm'])['english'].get('content') or {}
        predicted = 'neg' if content.get('negative_sentence') else 'pos'
        gold = 'neg' if r['gold_negation'] else 'pos'
        confusion[f'gold_{gold}->pred_{predicted}'] += 1
        if predicted != gold:
            errors.append({'english': r['english'], 'gold': gold, 'predicted': predicted})
    return dict(confusion), errors


def corrupted(rows, records):
    results = defaultdict(lambda: defaultdict(Counter))
    flagged_examples = defaultdict(list)
    for r in rows:
        tokens = r['gloss'].split()
        base = statuses(run_check(r['english'], r['gloss'], r['gloss_nmm'], r['notation'])['checks'])
        for name, op in {**ERRORS, **CONTROLS}.items():
            made = op(r, tokens)
            if not made:
                continue
            gloss, target, nmm = made
            s = statuses(run_check(r['english'], gloss, nmm, r['notation'])['checks'])
            c = results[r['cohort']][name]
            c['n'] += 1
            sf, wf = sign_f1(gloss, r['gloss']), word_f1(gloss, r['gloss'])
            c['sign_f1_sum'] += sf
            c['sign_f1_is_1'] += sf == 1.0
            c['word_f1_sum'] += wf
            new_flags = [k for k in CHECKS if s[k] in FLAGS and base[k] not in FLAGS]
            c['any_new_flag'] += bool(new_flags)
            if target:
                c[f'target:{s[target]}'] += 1
                c['flag_on_other_check'] += any(k != target for k in new_flags)
            elif new_flags and len(flagged_examples[name]) < 15:
                flagged_examples[name].append({'english': r['english'], 'reference': r['gloss'], 'gloss': gloss,
                                               'nmm': nmm, 'flags': {k: s[k] for k in new_flags}})
            records.append({'part': 'corrupted', 'id': r['id'], 'cohort': r['cohort'], 'operation': name,
                            'english': r['english'], 'reference': r['gloss'], 'gloss': gloss, 'nmm': nmm,
                            'target': target, 'statuses': s, 'base_statuses': base,
                            'sign_f1': sf, 'word_f1': wf})
    summary = {}
    for cohort, ops in results.items():
        summary[cohort] = {}
        for name, c in ops.items():
            n = c['n']
            entry = {'n': n, 'any_new_flag': c['any_new_flag'],
                     'mean_sign_f1_vs_reference': round(c['sign_f1_sum'] / n, 3),
                     'sign_f1_unchanged_1.0': c['sign_f1_is_1'],
                     'mean_word_f1_vs_reference': round(c['word_f1_sum'] / n, 3)}
            if name in ERRORS:
                entry.update({'flagged_MISMATCH': c['target:MISMATCH'], 'flagged_MISSING': c['target:MISSING'],
                              'missed_UNKNOWN': c['target:UNKNOWN'], 'missed_MATCH': c['target:MATCH'],
                              'flag_on_other_check': c['flag_on_other_check']})
            summary[cohort][name] = entry
    return summary, flagged_examples


def authored(path, records):
    out = []
    for mode, nmm in (('no_nmm', None), ('nmm_without_negation', {'negation': False})):
        for line in open(path, encoding='utf-8'):
            case = json.loads(line)
            case_nmm = case.get('gloss_nmm', nmm)
            if mode == 'nmm_without_negation' and 'negation' not in case['errors'] and ENGLISH_NEGATION.search(case['english']):
                case_nmm = {'negation': not any(is_negator(t) for t in case['gloss'].split())}
            s = statuses(run_check(case['english'], case['gloss'], case_nmm)['checks'])
            flags = [k for k in CHECKS if s[k] in FLAGS]
            if case['errors']:
                outcome = 'DETECTED' if set(flags) & set(case['errors']) else 'MISSED'
            else:
                outcome = 'FALSE_ALARM' if flags else 'OK'
            out.append({**case, 'mode': mode, 'nmm': case_nmm, 'statuses': s, 'outcome': outcome,
                        'flag_on_other_check': [k for k in flags if k not in case['errors']]})
            records.append({'part': 'authored', **out[-1]})
    return out


def generated(paths, records):
    summary, flagged = {}, defaultdict(list)
    for path in paths:
        run = Path(path).parent.name
        c = Counter()
        for line in open(path, encoding='utf-8'):
            p = json.loads(line)
            if not p.get('hypothesis', '').strip():
                c['empty_output'] += 1
                continue
            nmm = {k: v for k, v in (p.get('nmm') or {}).items() if isinstance(v, bool)} or None
            checks = run_check(p['source'], p['hypothesis'], nmm)['checks']
            s = statuses(checks)
            c['pairs'] += 1
            c['any_flag'] += any(v in FLAGS for v in s.values())
            c['any_assessed'] += any(v != 'UNKNOWN' for v in s.values())
            for k, v in s.items():
                c[f'{k}:{v}'] += 1
                if v in FLAGS:
                    flagged[run].append({'check': k, 'status': v, 'reason': checks[k]['reason'],
                                         'english': p['source'], 'hypothesis': p['hypothesis'],
                                         'reference': p.get('reference'), 'nmm': nmm})
            records.append({'part': 'generated', 'run': run, 'english': p['source'],
                            'hypothesis': p['hypothesis'], 'nmm': nmm, 'statuses': s})
        summary[run] = dict(c)
    return summary, flagged


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--data', type=Path, default=Path('data'))
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--gloss-lexicon', action='append', default=[])
    p.add_argument('--generated', action='append', default=[], help='Saved predictions.jsonl from a translator run')
    args = p.parse_args()
    if args.out.exists():
        raise SystemExit('Output directory must be new')
    from signir.lexicon import configure
    configure(args.gloss_lexicon)
    rows, nmm_coverage = load(args.data)
    records = []
    ref, alarms = reference_audit(rows, records)
    neg, neg_errors = negation_accuracy(rows)
    corr, control_flags = corrupted(rows, records)
    cases = authored(HERE / 'authored_cases.jsonl', records)
    gen, gen_flags = generated(args.generated, records)
    by_category = defaultdict(Counter)
    for c in cases:
        by_category[f"{c['mode']}:{c['category']}"][c['outcome']] += 1
    summary = {'pairs': Counter(r['cohort'] for r in rows), 'nmm_coverage': nmm_coverage,
               'lexicons': args.gloss_lexicon, 'reference_audit': ref,
               'english_negation_vs_human_gold': neg, 'corrupted_references': corr,
               'authored': {k: dict(v) for k, v in sorted(by_category.items())}, 'generated': gen}
    args.out.mkdir(parents=True)
    write = lambda name, value: (args.out / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    write('summary.json', summary)
    write('reference_flags.json', alarms)
    write('control_flags.json', control_flags)
    write('english_negation_errors.json', neg_errors)
    write('authored_results.json', cases)
    write('generated_flags.json', gen_flags)
    with open(args.out / 'records.jsonl', 'w', encoding='utf-8') as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    print(json.dumps(summary, indent=1))


if __name__ == '__main__':
    main()
