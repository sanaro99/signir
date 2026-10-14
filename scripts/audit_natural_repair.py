"""Reproduce descriptive natural coverage and explicitly labelled local edits.

These edits are chosen from facts the checker already recovers. Their scores
are diagnostic checks, not held-out accuracy or independent ASL judgments.
All outputs contain private corpus text and must stay under private/ locally.
"""
import argparse
import copy
from pathlib import Path

from signir.baselines import sign_f1, word_f1
from signir.compare import check_pair
from signir.data import read_jsonl, write_json, write_jsonl, file_hash
from signir.evaluate import feasibility, write_csv


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('input', type=Path)
    p.add_argument('--out', required=True, type=Path)
    args = p.parse_args()
    rows = read_jsonl(args.input)
    original_hash = file_hash(args.input)
    report = feasibility(args.input, args.out/'natural')
    records = read_jsonl(args.out/'natural/records.jsonl')
    indexed = {r['id']: r for r in rows}
    variants = []
    for record in records:
        row = indexed[record['id']]
        for field in ('numbers', 'negation'):
            c = record['checks'][field]
            if c['status'] != 'MATCH':
                continue
            if field == 'numbers':
                ev = c['gloss_evidence'][0]
                replacement = str(c['gloss_value'][0]['count']+7)
                edits = [('changed-number', replacement, 'MISMATCH')]
            else:
                if not c['gloss_value']['negative']:
                    continue
                ev = next((e for e in c['gloss_evidence'] if e['text'] in ('NOT', 'NEVER')
                           or e['text'].startswith('NEG:')), None)
                if ev is None:
                    continue
                edits = [('explicit-opposite-polarity', 'POS:'+c['gloss_value']['action'], 'MISMATCH'),
                         ('removed-polarity-evidence', '', 'UNKNOWN')]
            for kind, replacement, expected in edits:
                v = copy.deepcopy(row)
                v.update(id=row['id']+':'+kind, cohort='controlled', variant_of=row['id'],
                         gloss=row['gloss'][:ev['start']]+replacement+row['gloss'][ev['end']:],
                         expected={field: expected}, error_type=field if expected == 'MISMATCH' else None,
                         provenance={'kind': 'controlled_natural_mutation', 'version': 'natural-repair-1',
                                     'original_generation': row['provenance']},
                         change={'kind': kind, 'field': field, 'original_evidence': ev,
                                 'replacement': replacement,
                                 'synthetic_annotation': kind == 'explicit-opposite-polarity'})
                variants.append(v)
    write_jsonl(args.out/'variants.jsonl', variants)
    results, summary = [], []
    for v in variants:
        result = check_pair(v['english'], v['gloss'])
        original = indexed[v['variant_of']]
        field = v['change']['field']
        actual = result['checks'][field]['status']
        entry = {'id': v['id'], 'change': v['change'], 'expected': v['expected'],
                 'provenance': v['provenance'], 'cohort': 'controlled',
                 'sign_f1_to_original': sign_f1(original['gloss'], v['gloss']),
                 'word_f1_to_original': word_f1(original['gloss'], v['gloss']), **result}
        results.append(entry)
        summary.append({'id': v['id'], 'change': v['change']['kind'], 'field': field,
                        'expected': v['expected'][field], 'actual': actual,
                        'correct': actual == v['expected'][field]})
    write_jsonl(args.out/'variant-records.jsonl', results)
    write_csv(args.out/'variants.csv', summary, ['id', 'change', 'field', 'expected', 'actual', 'correct'])
    control_summary = []
    for kind in sorted({v['change'] for v in summary}):
        chosen = [v for v in summary if v['change'] == kind]
        control_summary.append({'change': kind, 'n': len(chosen),
                                'expected_obtained': sum(v['correct'] for v in chosen),
                                'failures': sum(not v['correct'] for v in chosen)})
    assert original_hash == file_hash(args.input), 'Input changed during audit'
    outcome = {'natural': report, 'input_unchanged': True,
               'pairs_with_any_assessed_check': sum(any(c['status'] != 'UNKNOWN' for c in r['checks'].values())
                                                   for r in records),
               'derived_controls': control_summary,
               'number_edits_invisible_to_sign_f1': sum(r['change']['kind'] == 'changed-number'
                                                     and r['sign_f1_to_original'] == 1.0 for r in results),
               'limits': ['This corpus was used to diagnose and repair the readers; it is not held-out.',
                          'Variants select already recoverable facts; their success is not general natural accuracy.',
                          'POS:ACTION is artificial explicit positive-polarity metadata, not ordinary ASL gloss.',
                          'Removed markers must abstain; absence of NOT is not evidence of positive polarity.',
                          'No independently reviewed natural ASL gold is supplied.']}
    write_json(args.out/'outcome.json', outcome)
    print({'natural_pairs': len(rows), 'pairs_assessed': outcome['pairs_with_any_assessed_check'],
           'derived_controls': control_summary, 'output': str(args.out)})


if __name__ == '__main__':
    main()
