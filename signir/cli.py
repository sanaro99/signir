"""Command-line workflows. All file access is local and explicit."""
import argparse
import json
from pathlib import Path

from .compare import check_pair
from .controlled import build_fixtures
from .correction import correct_once, SavedResponses
from .data import read_jsonl, write_jsonl, write_json, prepare, import_prior, validate_pair, file_hash
from .evaluate import freeze, evaluate, feasibility, write_csv, rule_hashes
from .natural import extraction_configuration

FIXTURES = Path(__file__).parent / 'fixtures'


def explain(result):
    lines = [f"English: {result['english']['text']}", f"Gloss:   {result['gloss']['text']}"]
    for name, check in result['checks'].items():
        a = ', '.join(f"{x['text']} [{x['start']}:{x['end']}]" for x in check['english_evidence']) or '(none)'
        b = ', '.join(f"{x['text']} [{x['start']}:{x['end']}]" for x in check['gloss_evidence']) or '(none)'
        lines.extend([f"  {name}: {check['status']} - {check['reason']}", f'    English evidence: {a}; gloss evidence: {b}'])
    for side in ('english', 'gloss'):
        for warning in result[side].get('warnings', []):
            lines.append(f'  {side} limitation: {warning}')
        for key in ('unrecognized', 'ambiguous_labels', 'unattached_numbers', 'unrecognized_predicates'):
            labels = result[side].get(key, [])
            if labels:
                lines.append(f"  {side} {key}: " + ', '.join(x['text'] for x in labels))
    return '\n'.join(lines)


def parser():
    p = argparse.ArgumentParser(description='Selected fact checks; MATCH does not certify natural or grammatical ASL.')
    sub = p.add_subparsers(dest='command', required=True)
    sub.add_parser('demo', help='Run authored MATCH/MISMATCH/UNKNOWN examples')
    check = sub.add_parser('check', help='Check one English/gloss pair')
    check.add_argument('--english', required=True)
    check.add_argument('--gloss', required=True)
    check.add_argument('--json', action='store_true')
    for name in ('check-file', 'prepare', 'freeze', 'evaluate', 'feasibility', 'correct'):
        q = sub.add_parser(name)
        q.add_argument('input', type=Path)
        q.add_argument('--out', type=Path, required=True)
        if name == 'prepare':
            q.add_argument('--seed', default='signir-2026')
            q.add_argument('--test-fraction', type=float, default=0.3)
        if name == 'evaluate':
            q.add_argument('--freeze', type=Path, required=True)
        if name == 'correct':
            q.add_argument('--responses', type=Path, required=True, help='Exact saved fixture responses; no live model')
    controlled = sub.add_parser('build-controlled')
    controlled.add_argument('--out', required=True, type=Path)
    prior = sub.add_parser('import-prior')
    prior.add_argument('--predictions', required=True, type=Path)
    prior.add_argument('--corpus', required=True, type=Path)
    prior.add_argument('--manifest', required=True, type=Path)
    prior.add_argument('--out', required=True, type=Path)
    return p


def main(argv=None):
    p = parser()
    args = p.parse_args(argv)
    try:
        if args.command == 'demo':
            for row in read_jsonl(FIXTURES/'demo.jsonl'):
                print(f"\n{row['id']} (synthetic fixture)")
                print(explain(check_pair(row['english'], row['gloss'])))
            print('\nEvidence checks only; no ASL grammaticality or naturalness claim.')
        elif args.command == 'check':
            result = check_pair(args.english, args.gloss)
            print(json.dumps(result, indent=2) if args.json else explain(result))
        elif args.command == 'build-controlled':
            rows = build_fixtures()
            write_jsonl(args.out, rows)
            print(f'Wrote {len(rows)} synthetic specification fixtures to {args.out}')
        elif args.command == 'prepare':
            if args.input.resolve() == args.out.resolve():
                raise ValueError('Use a distinct output path; source data must not be overwritten')
            rows = prepare(read_jsonl(args.input), args.seed, args.test_fraction)
            write_jsonl(args.out, rows)
            write_json(str(args.out)+'.manifest.json', {'input_sha256': file_hash(args.input), 'output_sha256': file_hash(args.out),
                       'rules': rule_hashes(), 'seed': args.seed, 'test_fraction': args.test_fraction,
                       'n': len(rows), 'groups': len({r['split_group'] for r in rows})})
            print(f'Prepared {len(rows)} pairs in {len({r["split_group"] for r in rows})} connected groups')
        elif args.command == 'import-prior':
            inputs = (args.predictions, args.corpus, args.manifest)
            if args.out.resolve() in {x.resolve() for x in inputs}:
                raise ValueError('Import output must not overwrite original data')
            rows = import_prior(read_jsonl(args.predictions), read_jsonl(args.corpus),
                                json.loads(args.manifest.read_text(encoding='utf-8-sig')))
            hashes = {x.name: file_hash(x) for x in inputs}
            for row in rows:
                row['provenance']['input_hashes'] = hashes
            write_jsonl(args.out, rows)
            print(f'Imported {len(rows)} saved outputs; keep this file and derived records private')
        elif args.command == 'check-file':
            rows = read_jsonl(args.input)
            records, summary = [], []
            for row in rows:
                validate_pair(row)
                result = check_pair(row['english'], row['gloss'])
                records.append({'id': row['id'], 'provenance': row['provenance'], **result})
                summary.append({'id': row['id'], **{k: v['status'] for k, v in result['checks'].items()}})
            write_jsonl(args.out/'records.jsonl', records)
            write_csv(args.out/'checks.csv', summary, ['id', 'entities', 'action', 'negation', 'numbers', 'roles'])
            write_json(args.out/'manifest.json', {'data_sha256': file_hash(args.input), 'rules': rule_hashes(),
                       'extractors': extraction_configuration()})
            print(f'Checked {len(rows)} pairs; evidence JSON and check CSV in {args.out}')
        elif args.command == 'freeze':
            lock = freeze(args.input, args.out)
            print(json.dumps({'freeze': str(args.out), 'baselines': lock['baselines']}, indent=2))
        elif args.command in ('evaluate', 'feasibility'):
            report = evaluate(args.input, args.freeze, args.out) if args.command == 'evaluate' else feasibility(args.input, args.out)
            print(json.dumps({'n_pairs': report['n_pairs'], 'summary': report['summary'], 'output': str(args.out)}, indent=2))
        elif args.command == 'correct':
            adapter = SavedResponses(json.loads(args.responses.read_text(encoding='utf-8-sig')))
            rows = read_jsonl(args.input)
            results = []
            for row in rows:
                validate_pair(row)
                results.append(correct_once(row, adapter, 'saved-fixture-responses-1'))
            write_jsonl(args.out/'records.jsonl', results)
            write_csv(args.out/'summary.csv', [{'id': r['id'], 'attempts': r['attempts'],
                       'improved': '|'.join(r['improved']), 'regressions': '|'.join(r['regressions']),
                       'lost_coverage': '|'.join(r['lost_coverage'])} for r in results],
                      ['id', 'attempts', 'improved', 'regressions', 'lost_coverage'])
            write_json(args.out/'manifest.json', {'input_sha256': file_hash(args.input), 'responses_sha256': file_hash(args.responses),
                       'rules': rule_hashes(), 'method': 'saved-fixture-responses-1', 'model': None,
                       'interpretation': 'Workflow demonstration only; no live generation or translation improvement result.'})
            print(f'Saved {len(results)} single-attempt fixture corrections, including regression diagnostics')
    except (ValueError, OSError, KeyError, TypeError) as error:
        p.exit(2, f'error: {error}\n')


if __name__ == '__main__':
    main()
