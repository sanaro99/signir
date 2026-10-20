"""Frozen evaluation protocol, development-only calibration and abstention reports."""
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import platform

from . import __version__
from .baselines import sign_f1, word_f1
from .compare import check_pair, canonical
from .data import digest, file_hash, read_jsonl, write_json, write_jsonl, prepare, validate_pair
from .schema import CHECKS
from .natural import extraction_configuration

BASELINES = {'sign_f1': sign_f1, 'word_f1': word_f1}


def rule_hashes():
    return {p.name: file_hash(p) for p in sorted(Path(__file__).parent.glob('*.py'))}


def baseline_label(row):
    if any(v == 'MISMATCH' for v in row.get('expected', {}).values()):
        return True
    if row.get('cohort') in ('synthetic_reference', 'reviewed_reference') and row.get('expected'):
        return False
    return None


def calibrate(rows):
    if any(row.get('split') != 'dev' for row in rows):
        raise ValueError('Calibration accepts development rows only')
    labelled = [r for r in rows if baseline_label(r) is not None and r.get('reference_gloss') is not None]
    if set(baseline_label(r) for r in labelled) != {False, True}:
        raise ValueError('Development calibration needs labelled errors and reviewed/synthetic unchanged references')
    out = {}
    for name, metric in BASELINES.items():
        scores = [(metric(r['gloss'], r['reference_gloss']), baseline_label(r)) for r in labelled]
        candidates = sorted({0.0, 1.0} | {s for s, _ in scores} |
                            {(a+b)/2 for a, b in zip(sorted({s for s, _ in scores}), sorted({s for s, _ in scores})[1:])})
        best = None
        for threshold in candidates:
            pos = [s < threshold for s, y in scores if y]
            neg = [s >= threshold for s, y in scores if not y]
            score = (sum(pos)/len(pos) + sum(neg)/len(neg))/2
            if best is None or score > best['balanced_accuracy']:
                best = {'threshold': threshold, 'balanced_accuracy': score, 'n': len(scores)}
        out[name] = best
    return out


def freeze(data_path, lock_path):
    if Path(lock_path).exists():
        raise ValueError('Freeze already exists; use a new versioned freeze path')
    rows = read_jsonl(data_path)
    prepare(rows)  # validates IDs and catches connected dev/test leakage
    if {r.get('split') for r in rows} != {'dev', 'test'}:
        raise ValueError('Freeze requires prepared development and test splits')
    frozen = {'protocol': 'signir-evaluation-1', 'created_utc': datetime.now(timezone.utc).isoformat(),
              'package_version': __version__, 'python_version': platform.python_version(),
              'data_sha256': file_hash(data_path), 'data_version': sorted({r['provenance']['version'] for r in rows}),
              'development_sha256': digest([r for r in rows if r['split'] == 'dev']),
              'test_sha256': digest([r for r in rows if r['split'] == 'test']),
              'rules': rule_hashes(), 'calibration_split': 'dev',
              'threshold_rule': 'error iff overlap < threshold; maximize dev balanced accuracy; ties use smallest threshold',
              'baselines': calibrate([r for r in rows if r['split'] == 'dev']),
              'extractors': extraction_configuration(),
              'configuration': {'signir_version': '1.0', 'checks': CHECKS},
              'generation_sources': sorted({r['provenance']['version'] for r in rows if r['provenance']['kind'] == 'saved_generated'})}
    write_json(lock_path, frozen)
    return frozen


def write_csv(path, rows, fields):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def analyze(rows, thresholds=None):
    counts = defaultdict(Counter)
    errors = defaultdict(Counter)
    extraction = defaultdict(Counter)
    recoverability = defaultdict(Counter)
    causes = Counter()
    records = []
    additions = []
    for row in rows:
        validate_pair(row)
        result = check_pair(row['english'], row['gloss'], row.get('gloss_nmm'), row.get('gloss_notation'))
        cohort = row.get('cohort', 'unreviewed_reference')
        baseline = {}
        for name, metric in BASELINES.items():
            score = metric(row['gloss'], row['reference_gloss']) if 'reference_gloss' in row else None
            baseline[name] = {'score': score, 'flagged': score < thresholds[name]['threshold'] if thresholds and score is not None else None}
        any_wrong = False
        for name, check in result['checks'].items():
            c = counts[(cohort, name)]
            c['total'] += 1
            c[check['status']] += 1
            expected = row.get('expected', {}).get(name)
            if expected:
                c['labelled'] += 1
                c['correct_status'] += check['status'] == expected
                any_wrong |= check['status'] != expected
            if cohort == 'reviewed_reference' and expected == 'MATCH':
                c['reviewed_unchanged'] += 1
                c['false_alarm'] += check['status'] in ('MISMATCH', 'MISSING')
            for side in ('english', 'gloss'):
                rc = recoverability[(cohort, side, name)]
                rc['n'] += 1
                rc['known'] += result[side]['facts'][name]['state'] == 'KNOWN'
                if name in row.get('gold', {}).get(side, {}):
                    g = row['gold'][side][name]
                    predicted = result[side]['facts'][name]['value']
                    ec = extraction[(cohort, side, name)]
                    ec['n_gold'] += 1
                    ec['gold_unknown'] += g is None
                    ec['predicted_unknown'] += predicted is None
                    ec['correct'] += canonical(g) == canonical(predicted)
                    ec['wrong_known'] += predicted is not None and canonical(g) != canonical(predicted)
                    ec['missed_recoverable'] += g is not None and predicted is None
        if any_wrong:
            cause = row.get('audit', {}).get('cause', 'unresolved')
            causes[cause] += 1
        error_type = row.get('error_type')
        if error_type:
            actual = result['checks'][error_type]['status']
            e = errors[(cohort, error_type)]
            e['total'] += 1
            e['detected'] += actual in ('MISMATCH', 'MISSING')
            e['detected_as_missing'] += actual == 'MISSING'
            e['missed_match'] += actual == 'MATCH'
            e['missed_unknown'] += actual == 'UNKNOWN'
            for name in BASELINES:
                e[name + '_assessed'] += baseline[name]['flagged'] is not None
                e[name + '_detected'] += baseline[name]['flagged'] is True
            if actual in ('MISMATCH', 'MISSING') and baseline['sign_f1']['flagged'] is False:
                additions.append({'id': row['id'], 'cohort': cohort, 'error_type': error_type,
                                  'sign_f1': baseline['sign_f1']['score'], 'diagnostic': result['checks'][error_type]})
        records.append({'id': row['id'], 'cohort': cohort, 'expected': row.get('expected'),
                        'provenance': row['provenance'], 'baseline': baseline, **result})
    summary = []
    for (cohort, name), c in sorted(counts.items()):
        summary.append({'cohort': cohort, 'check': name, 'n': c['total'], 'match': c['MATCH'],
                        'mismatch': c['MISMATCH'], 'missing': c['MISSING'], 'unknown': c['UNKNOWN'],
                        'coverage': (c['total']-c['UNKNOWN'])/c['total'],
                        'labelled': c['labelled'], 'correct_status': c['correct_status'],
                        'reviewed_unchanged': c['reviewed_unchanged'], 'false_alarms': c['false_alarm']})
    controlled = [{'cohort': cohort, 'error_type': name, **{k: c[k] for k in ('total', 'detected', 'detected_as_missing', 'missed_match', 'missed_unknown', 'sign_f1_assessed', 'sign_f1_detected', 'word_f1_assessed', 'word_f1_detected')}}
                  for (cohort, name), c in sorted(errors.items())]
    extract = [{'cohort': cohort, 'side': side, 'check': name, **{k: c[k] for k in ('n_gold', 'gold_unknown', 'predicted_unknown', 'correct', 'wrong_known', 'missed_recoverable')}}
               for (cohort, side, name), c in sorted(extraction.items())]
    baseline_summary = []
    for cohort in sorted({r['cohort'] for r in records}):
        selected = [r for r in records if r['cohort'] == cohort]
        for name in BASELINES:
            scored = [r['baseline'][name]['score'] for r in selected if r['baseline'][name]['score'] is not None]
            baseline_summary.append({'cohort': cohort, 'baseline': name, 'n_scored': len(scored),
                                     'mean': sum(scored)/len(scored) if scored else None,
                                     'flagged': sum(r['baseline'][name]['flagged'] is True for r in selected),
                                     'n_threshold_assessed': sum(r['baseline'][name]['flagged'] is not None for r in selected)})
    recovery = [{'cohort': cohort, 'side': side, 'check': name, 'n': c['n'], 'known': c['known'],
                 'unknown': c['n']-c['known'], 'coverage': c['known']/c['n']}
                for (cohort, side, name), c in sorted(recoverability.items())]
    return {'n_pairs': len(rows), 'summary': summary, 'controlled_errors': controlled, 'recoverability': recovery,
            'extraction': extract, 'error_attribution': dict(causes), 'baselines': baseline_summary,
            'beyond_overlap_examples': additions,
            'limits': ['Coverage is not accuracy.', 'Synthetic fixture labels are not natural-ASL judgments.',
                       'Unchanged unreviewed corpus pairs have no equivalence label.',
                       'Error causes require audit; unresolved is not silently attributed.',
                       'No natural extraction accuracy is available without independent gold records.']}, records


def save_report(out_dir, report, records):
    out_dir = Path(out_dir)
    write_json(out_dir / 'report.json', report)
    write_jsonl(out_dir / 'records.jsonl', records)
    for key, fields in [
        ('summary', ['cohort', 'check', 'n', 'match', 'mismatch', 'missing', 'unknown', 'coverage', 'labelled', 'correct_status', 'reviewed_unchanged', 'false_alarms']),
        ('controlled_errors', ['cohort', 'error_type', 'total', 'detected', 'detected_as_missing', 'missed_match', 'missed_unknown', 'sign_f1_assessed', 'sign_f1_detected', 'word_f1_assessed', 'word_f1_detected']),
        ('extraction', ['cohort', 'side', 'check', 'n_gold', 'gold_unknown', 'predicted_unknown', 'correct', 'wrong_known', 'missed_recoverable']),
        ('recoverability', ['cohort', 'side', 'check', 'n', 'known', 'unknown', 'coverage']),
        ('baselines', ['cohort', 'baseline', 'n_scored', 'mean', 'flagged', 'n_threshold_assessed'])]:
        write_csv(out_dir / (key + '.csv'), report[key], fields)


def evaluate(data_path, lock_path, out_dir):
    lock = json.loads(Path(lock_path).read_text(encoding='utf-8'))
    if lock.get('protocol') != 'signir-evaluation-1' or file_hash(data_path) != lock['data_sha256'] or rule_hashes() != lock['rules']:
        raise ValueError('Frozen data or implementation changed; create a new explicitly versioned study freeze')
    if lock.get('extractors') != extraction_configuration():
        raise ValueError('Frozen extraction dependency or model resources changed')
    rows = read_jsonl(data_path)
    if calibrate([r for r in rows if r['split'] == 'dev']) != lock['baselines']:
        raise ValueError('Frozen baseline thresholds were modified')
    report, records = analyze([r for r in rows if r['split'] == 'test'], lock['baselines'])
    report['reproducibility'] = lock
    save_report(out_dir, report, records)
    return report


def feasibility(data_path, out_dir):
    rows = read_jsonl(data_path)
    report, records = analyze(rows)
    report['reproducibility'] = {'data_sha256': file_hash(data_path), 'rules': rule_hashes(),
                                 'extractors': extraction_configuration(),
                                 'python_version': platform.python_version(), 'package_version': __version__,
                                 'mode': 'descriptive feasibility; no fitted thresholds or held-out accuracy claim'}
    save_report(out_dir, report, records)
    return report
