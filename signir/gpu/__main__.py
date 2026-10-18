"""Optional CLI: python -m signir.gpu --help."""
import argparse
import json
from pathlib import Path
import sys

from .protocol import default_config, validate_config
from .storage import (file_hash, freeze_experiment, protect_output, read_json,
                      resolve_revision, verify_freeze, write_json)


def main(argv=None):
    parser = argparse.ArgumentParser(description='CUDA-only SignIR experiment; replay is a separate CPU workflow test')
    commands = parser.add_subparsers(dest='command', required=True)
    freeze = commands.add_parser('freeze', help='Freeze inputs, prompts, model/tokenizer, image and code before inference')
    freeze.add_argument('--input', required=True, type=Path)
    freeze.add_argument('--config', type=Path)
    freeze.add_argument('--revision', help='Immutable HF commit; omitted resolves model main once at freeze time')
    freeze.add_argument('--container-image', required=True, help='image@sha256:digest, or replay for CPU smoke only')
    freeze.add_argument('--out', required=True, type=Path)
    for name in ('run', 'replay'):
        command = commands.add_parser(name)
        command.add_argument('--input', required=True, type=Path)
        command.add_argument('--freeze', required=True, type=Path)
        command.add_argument('--out', required=True, type=Path)
        if name == 'replay':
            command.add_argument('--responses', required=True, type=Path)
    commands.add_parser('preflight', help='Execute an actual CUDA tensor operation; fail without CUDA')
    challenge = commands.add_parser('challenge', help='Build authored diagnostic cases with partial expected checks')
    challenge.add_argument('--out', required=True, type=Path)
    dry = commands.add_parser('dry-run', help='Audit requests, CPU baseline and optional exact tokenizer budget without model weights')
    dry.add_argument('--input',required=True,type=Path)
    dry.add_argument('--out',required=True,type=Path)
    dry.add_argument('--config',type=Path)
    dry.add_argument('--tokenizer',action='store_true',help='Download tokenizer files only and profile exact token budgets')
    dry.add_argument('--revision',help='Optional immutable model/tokenizer commit')
    compare = commands.add_parser('compare',help='Compare semantic facts/statuses across fresh repeats or throughput profiles')
    compare.add_argument('--left',required=True,type=Path)
    compare.add_argument('--right',required=True,type=Path)
    compare.add_argument('--out',required=True,type=Path)
    annotate = commands.add_parser('annotate', help='Export independent blank annotation sheets')
    annotate.add_argument('--input', required=True, type=Path)
    annotate.add_argument('--out', required=True, type=Path)
    score = commands.add_parser('score', help='Report coverage and optional reviewed-gold correctness')
    score.add_argument('--records', required=True, type=Path)
    score.add_argument('--gold', type=Path)
    score.add_argument('--out', required=True, type=Path)
    assemble = commands.add_parser('assemble', help='Merge independently reviewed side/check annotations')
    for name in ('input', 'english', 'gloss', 'checks', 'out'):
        assemble.add_argument('--' + name, required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == 'freeze':
            config = read_json(args.config) if args.config else default_config()
            revision = args.revision or resolve_revision(config['model'])
            protected = [args.input] + ([args.config] if args.config else [])
            protect_output(args.out, protected)
            write_json(args.out, freeze_experiment(args.input, config, revision, args.container_image))
            print('Frozen experiment:', args.out)
        elif args.command == 'preflight':
            from .backend import cuda_preflight
            print(json.dumps(cuda_preflight(), indent=2))
        elif args.command == 'challenge':
            from .challenge import write_challenge
            rows = write_challenge(args.out)
            print(f'Wrote {len(rows)} authored diagnostic pairs to {args.out}')
        elif args.command == 'dry-run':
            from .dry_run import audit, load_tokenizer
            config = validate_config(read_json(args.config) if args.config else default_config())
            tokenizer, revision = load_tokenizer(config,args.revision) if args.tokenizer else (None,None)
            result = audit(args.input,args.out,config,tokenizer,revision,[args.config] if args.config else [])
            budget = result['over_budget_requests'] if args.tokenizer else 'unmeasured (no tokenizer)'
            print(f"CPU dry run: {result['pairs']} pairs, {result['unique_requests']} unique requests, "
                  f"over-budget requests: {budget}; no model/CUDA execution")
        elif args.command == 'compare':
            from .analysis import compare_runs
            from .evaluation import read_records
            protect_output(args.out,[args.left,args.right])
            result = compare_runs(read_records(args.left),read_records(args.right))
            result['provenance'] = {'left_sha256':file_hash(args.left),'right_sha256':file_hash(args.right)}
            write_json(args.out,result)
            print('Repeat comparison:',args.out)
        elif args.command in ('run', 'replay'):
            from .backend import CUDABackend, ReplayBackend
            from .runner import run_experiment
            frozen = read_json(args.freeze)
            verify_freeze(args.input, frozen, dependency_mode='cpu' if args.command == 'replay' else 'all')
            backend = CUDABackend(frozen) if args.command == 'run' else ReplayBackend(args.responses)
            protected = [args.freeze] + ([args.responses] if args.command == 'replay' else [])
            records = run_experiment(args.input, frozen, args.out, backend, protected)
            print('Experiment reports:', args.out)
            return 3 if read_json(args.out / 'manifest.json')['failed_requests'] else 0
        elif args.command == 'annotate':
            from .evaluation import export_annotations
            export_annotations(args.input, args.out)
            print('Blank annotation sheets:', args.out)
        elif args.command == 'assemble':
            from .evaluation import assemble_annotations
            assemble_annotations(args.input, args.english, args.gloss, args.checks, args.out)
            print('Reviewed gold:', args.out)
        elif args.command == 'score':
            from .evaluation import evaluate, load_gold, read_records, write_reports
            protected = [args.records] + ([args.gold] if args.gold else [])
            output = protect_output(args.out, protected)
            if output.exists() and any(output.iterdir()):
                raise ValueError('Score output must be an empty or new directory')
            records = read_records(args.records)
            gold = load_gold(args.gold, records) if args.gold else None
            summary = evaluate(records, gold)
            summary['provenance'] = {'records_sha256': file_hash(args.records),
                'gold_sha256': file_hash(args.gold) if args.gold else None}
            write_reports(output, records, summary, gold)
            print('Evaluation reports:', output)
    except (ValueError, RuntimeError, OSError, KeyError, TypeError) as exc:
        print('Experiment error: ' + str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
