"""Argument registration stays dependency-free; event dependencies load on dispatch."""
import json
from pathlib import Path


def register(sub):
    one = sub.add_parser("event-check", help="Experimental independent local-model event check")
    one.add_argument("--english", required=True)
    one.add_argument("--gloss", required=True)
    one.add_argument("--config", type=Path, required=True)
    one.add_argument("--out", type=Path, required=True)
    for name in ("event-check-file", "event-compare", "event-audit"):
        parser = sub.add_parser(name)
        parser.add_argument("input", type=Path)
        parser.add_argument("--out", type=Path, required=True)
        if name == "event-check-file":
            parser.add_argument("--config", type=Path, required=True)
        if name == "event-audit":
            parser.add_argument("--baseline", type=Path)
            parser.add_argument("--labels", type=Path)


def dispatch(args):
    try:
        from .client import LocalClient, ModelConfig, strict_json
        from .lexicon import Lexicon
        from .workflow import run_batch, run_saved, preflight
        from .audit import audit
    except ImportError as exc:
        raise ValueError("event engine requires installation with: pip install -e '.[events]'") from exc
    from signir.data import read_jsonl, write_json, file_hash
    from .data import ensure_distinct_paths

    if args.command in ("event-check", "event-check-file"):
        config = ModelConfig.model_validate(strict_json(args.config.read_text(encoding="utf-8")))
        inputs = [args.config]
        lexicon = None
        if config.lexicon:
            path = args.config.parent / config.lexicon
            lexicon = Lexicon.load(path)
            inputs.append(path)
        if args.command == "event-check-file":
            rows = read_jsonl(args.input)
            inputs.append(args.input)
        else:
            rows = [{"id": "single", "english": args.english, "gloss": args.gloss,
                     "source_group": "single", "provenance": {"kind": "cli_input", "version": "1"}}]
        result = run_batch(rows, args.out, LocalClient(config), lexicon, inputs)
    elif args.command == "event-compare":
        result = run_saved(read_jsonl(args.input), args.out, [args.input])
    else:
        inputs = [p for p in (args.input, args.baseline, args.labels) if p]
        ensure_distinct_paths(inputs, [args.out])
        if args.out.exists():
            raise ValueError("audit output must be a new file")
        result = audit(read_jsonl(args.input),
                       read_jsonl(args.baseline) if args.baseline else None,
                       read_jsonl(args.labels) if args.labels else None)
        result["input_hashes"] = {str(p): file_hash(p) for p in inputs}
        write_json(args.out, result)
    print(json.dumps({"output": str(args.out), **result}, indent=2))
    return 2 if result["error_pairs"] else 0
