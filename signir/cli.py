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


def _evidence_text(items):
    text = [f"{x['text']} [{x['start']}:{x['end']}]" for x in items if 'text' in x]
    text += [f"NMM {x['label']}={str(x['value']).lower()}" for x in items if 'channel' in x]
    return ', '.join(text) or '(none)'


def explain(result):
    lines = [f"English: {result['english']['text']}", f"Gloss:   {result['gloss']['text']}"]
    if result['gloss'].get('nmm'):
        lines.append('NMM:     ' + ', '.join(f'{k}={str(v).lower()}' for k, v in result['gloss']['nmm'].items()))
    for name, check in result['checks'].items():
        confidence = f" ({check['confidence']} confidence)" if check.get('confidence') else ''
        lines.extend([f"  {name}: {check['status']}{confidence} - {check['reason']}",
                      f"    English evidence: {_evidence_text(check['english_evidence'])}; "
                      f"gloss evidence: {_evidence_text(check['gloss_evidence'])}"])
    for side in ('english', 'gloss'):
        for warning in result[side].get('warnings', []):
            lines.append(f'  {side} limitation: {warning}')
        for key in ('unrecognized', 'ambiguous_labels', 'unattached_numbers', 'unrecognized_predicates'):
            labels = result[side].get(key, [])
            if labels:
                lines.append(f"  {side} {key}: " + ', '.join(x['text'] for x in labels))
    return '\n'.join(lines)


def parse_nmm(text):
    if text is None:
        return None
    out = {}
    for item in filter(None, (x.strip() for x in text.split(','))):
        name, _, value = item.partition('=')
        if value not in ('', 'true', 'false'):
            raise ValueError('--gloss-nmm values must be true or false')
        out[name] = value != 'false'
    return out


def parser():
    p = argparse.ArgumentParser(description='Selected fact checks; MATCH does not certify natural or grammatical ASL.')
    p.add_argument('--gloss-lexicon', action='append', type=Path,
                   help='English-to-gloss dictionary JSON used to recognize synonyms (repeatable)')
    p.add_argument('--no-builtin-lexicon', action='store_true',
                   help='Do not load the bundled common-correspondence dictionary')
    sub = p.add_subparsers(dest='command', required=True)
    sub.add_parser('demo', help='Run authored MATCH/MISMATCH/UNKNOWN examples')
    check = sub.add_parser('check', help='Check one English/gloss pair')
    check.add_argument('--english', required=True)
    check.add_argument('--gloss', required=True)
    check.add_argument('--json', action='store_true')
    check.add_argument('--gloss-nmm', default=None,
                       help='Non-manual markers of the translation, e.g. "negation" or "negation=false,topic"')
    check.add_argument('--notation', choices=['asllrp', 'aslg_pc12'], default=None)
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
    ir = sub.add_parser('ir', help='Print the SignIR 2.0 graph of an English sentence and/or a gloss (CPU rule readers)')
    ir.add_argument('--english')
    ir.add_argument('--gloss')
    ir.add_argument('--gloss-nmm', default=None)
    ir.add_argument('--notation', choices=['asllrp', 'aslg_pc12'], default=None)
    controlled = sub.add_parser('build-controlled')
    controlled.add_argument('--out', required=True, type=Path)
    prior = sub.add_parser('import-prior')
    prior.add_argument('--predictions', required=True, type=Path)
    prior.add_argument('--corpus', required=True, type=Path)
    prior.add_argument('--manifest', required=True, type=Path)
    prior.add_argument('--out', required=True, type=Path)
    from .events.cli import register
    register(sub)
    from .heldout import register as register_heldout
    register_heldout(sub)
    return p


def main(argv=None):
    p = parser()
    args = p.parse_args(argv)
    try:
        if args.gloss_lexicon or args.no_builtin_lexicon:
            from .lexicon import configure, BUILTIN
            configure(([] if args.no_builtin_lexicon else [BUILTIN]) + [str(x) for x in args.gloss_lexicon or []])
        if args.command.startswith('event-'):
            from .events.cli import dispatch
            code = dispatch(args)
            if code:
                p.exit(code)
            return code
        elif args.command == 'heldout':
            from .heldout import dispatch as heldout_dispatch
            return heldout_dispatch(args)
        elif args.command == 'demo':
            for row in read_jsonl(FIXTURES/'demo.jsonl'):
                print(f"\n{row['id']} (synthetic fixture)")
                print(explain(check_pair(row['english'], row['gloss'], row.get('gloss_nmm'), row.get('gloss_notation'))))
            print('\nEvidence checks only; no ASL grammaticality or naturalness claim.')
        elif args.command == 'ir':
            if not args.english and not args.gloss:
                raise ValueError('ir needs --english and/or --gloss')
            try:
                from .events.from_rules import english_graph, gloss_graph
            except ImportError as exc:
                raise ValueError("SignIR 2.0 graphs need: pip install -e '.[events,natural]'") from exc
            out = {}
            if args.english:
                out['english'] = english_graph(args.english).model_dump(exclude_defaults=True)
            if args.gloss:
                out['gloss'] = gloss_graph(args.gloss, parse_nmm(args.gloss_nmm), args.notation).model_dump(
                    exclude_defaults=True)
            print(json.dumps(out, indent=2, ensure_ascii=False))
        elif args.command == 'check':
            result = check_pair(args.english, args.gloss, parse_nmm(args.gloss_nmm), args.notation)
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
                result = check_pair(row['english'], row['gloss'], row.get('gloss_nmm'), row.get('gloss_notation'))
                records.append({'id': row['id'], 'provenance': row['provenance'], **result})
                summary.append({'id': row['id'], **{k: v['status'] for k, v in result['checks'].items()},
                                **{f'{k}_confidence': v.get('confidence') or '' for k, v in result['checks'].items()}})
            write_jsonl(args.out/'records.jsonl', records)
            checks = ['entities', 'action', 'negation', 'numbers', 'roles']
            write_csv(args.out/'checks.csv', summary, ['id', *checks, *(f'{k}_confidence' for k in checks)])
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
