"""Coverage, optional reviewed-gold evaluation, and blind annotation exports."""
from collections import Counter
import csv
import json
from pathlib import Path

from ..compare import canonical
from ..schema import CHECKS, record
from .protocol import STATUSES, compare_records, parse_extraction
from .storage import digest, load_pairs, protect_output, write_json

ARMS = ('cpu', 'structured', 'judge')


def read_records(path):
    rows = [json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines() if line.strip()]
    if not rows or len({row['id'] for row in rows}) != len(rows):
        raise ValueError('Records must have unique IDs and at least one pair')
    for row in rows:
        if any(arm not in row['arms'] for arm in ARMS):
            raise ValueError('Every record must include all three experiment arms')
        for arm in ARMS:
            if (row['arms'][arm]['status'] not in ('ok', 'error')
                    or set(row['arms'][arm]['checks']) != set(CHECKS)
                    or any(check['status'] not in STATUSES for check in row['arms'][arm]['checks'].values())):
                raise ValueError('Invalid arm/check status')
    return rows


def load_gold(path, records):
    available, result = {row['id']: row for row in records}, {}
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        gold = json.loads(line)
        identifier = gold['id']
        if identifier not in available or identifier in result:
            raise ValueError('Gold IDs must be unique and present in the predictions')
        if gold.get('annotation_kind') not in ('authored', 'human-reviewed'):
            raise ValueError('Gold needs explicit authored or human-reviewed annotation_kind')
        if (not isinstance(gold.get('checks'), dict) or not gold['checks']
                or any(key not in CHECKS or value not in STATUSES for key, value in gold['checks'].items())):
            raise ValueError('Gold checks must explicitly label selected supported fields')
        if gold['checks'].get('roles', 'UNKNOWN') != 'UNKNOWN':
            raise ValueError('Gloss roles are outside this experiment scope')
        if not all(side in gold for side in ('english', 'gloss')):
            pair_hash = digest({side: available[identifier][side] for side in ('english', 'gloss')})
            if gold.get('pair_sha256') != pair_hash:
                raise ValueError('Check-only gold requires pair_sha256 binding the exact English/gloss texts')
        for side in ('english', 'gloss'):
            if side not in gold:
                continue
            ir = gold[side]
            if ir['text'] != available[identifier][side] or ir['language'] != side:
                raise ValueError('Gold record text/language differs from input')
            facts = {name: {key: value for key, value in f.items() if key != 'scope'}
                     for name, f in ir['facts'].items()}
            gold[side] = parse_extraction({'facts': facts}, ir['text'], side)
        result[identifier] = gold
    if not result:
        raise ValueError('Gold file must contain at least one reviewed annotation')
    return result


def ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def detection_metrics(predictions):
    confusion = Counter(predictions)
    known = sum(n for (gold, _), n in confusion.items() if gold != 'UNKNOWN')
    tp = confusion['MISMATCH', 'MISMATCH']
    fp = confusion['MATCH', 'MISMATCH']
    fn = confusion['MISMATCH', 'MATCH'] + confusion['MISMATCH', 'UNKNOWN']
    tn = confusion['MATCH', 'MATCH']
    return {'labeled_known': known, 'true_positive': tp, 'false_positive': fp,
            'false_negative': fn, 'true_negative': tn,
            'precision': ratio(tp, tp + fp), 'recall': ratio(tp, tp + fn),
            'f1': ratio(2*tp, 2*tp + fp + fn),
            'false_alarm_rate_on_gold_match': ratio(fp, sum(n for (gold, _), n in confusion.items() if gold == 'MATCH')),
            'accuracy_including_abstentions': ratio(tp + tn, known),
            'abstentions_on_known': sum(n for (gold, pred), n in confusion.items()
                                       if gold != 'UNKNOWN' and pred == 'UNKNOWN'),
            'asserted_on_gold_unknown': confusion['UNKNOWN', 'MATCH'] + confusion['UNKNOWN', 'MISMATCH'],
            'confusion': {gold: {pred: confusion[gold, pred] for pred in STATUSES} for gold in STATUSES}}


def side_record(row, arm, side):
    value = row['arms'][arm].get(side)
    if arm == 'structured':
        return value.get('record') if isinstance(value, dict) and value.get('status') == 'ok' else None
    return value


def extraction_metrics(records, gold):
    result = {}
    for arm in ('cpu', 'structured'):
        result[arm] = {}
        for side in ('english', 'gloss'):
            result[arm][side] = {}
            for name in CHECKS:
                tp = fp = fn = labeled = unsupported = 0
                for row in records:
                    expected = gold.get(row['id'], {}).get(side)
                    if expected is None:
                        continue
                    labeled += 1
                    expected = expected['facts'][name]
                    actual = side_record(row, arm, side)
                    predicted = actual['facts'][name] if actual else {'state': 'UNKNOWN', 'value': None}
                    gk, pk = expected['state'] == 'KNOWN', predicted['state'] == 'KNOWN'
                    equal = gk and pk and canonical(expected['value']) == canonical(predicted['value'])
                    tp += int(equal)
                    fp += int(pk and not equal)
                    fn += int(gk and not equal)
                    unsupported += int(pk and not gk)
                result[arm][side][name] = {'labeled_records': labeled, 'exact_value_true_positive': tp,
                    'false_positive': fp, 'false_negative': fn, 'precision': ratio(tp, tp+fp),
                    'recall': ratio(tp, tp+fn), 'asserted_on_gold_unknown': unsupported}
    return result


def evaluate(records, gold=None, stratify=True):
    result = {'pairs': len(records), 'gold_pairs': len(gold or {}),
              'annotation_kinds': dict(Counter(row.get('annotation_kind', 'unspecified') for row in (gold or {}).values())),
              'limits': ['Coverage is not accuracy.', 'Missing labels are excluded, never treated as MATCH.',
                         'UNKNOWN predictions are missed errors when gold is MISMATCH.',
                         'UNKNOWN gold cannot establish a false-alarm rate; assertions are counted separately.',
                         'Extraction metrics compare complete field values, not individual entity-token accuracy.',
                         'No ASL grammaticality, naturalness, or whole-translation quality claim.'],
              'arms': {}, 'extraction': None, 'gold_contract_control': None}
    for arm in ARMS:
        counts = {name: dict(Counter(row['arms'][arm]['checks'][name]['status'] for row in records)) for name in CHECKS}
        assessed = sum(values.get('MATCH', 0) + values.get('MISMATCH', 0) for values in counts.values())
        pairs_assessed = sum(any(row['arms'][arm]['checks'][name]['status'] != 'UNKNOWN' for name in CHECKS) for row in records)
        result['arms'][arm] = {'pairs_with_assessed_check': pairs_assessed,
            'assessed_checks': assessed, 'possible_checks': len(records) * len(CHECKS),
            'possible_supported_checks': len(records) * (len(CHECKS)-1),
            'failed_pairs': sum(row['arms'][arm]['status'] == 'error' for row in records),
            'coverage_by_check': counts, 'quality': None}
        if gold is not None:
            quality = {name: detection_metrics([(gold[row['id']]['checks'][name],
                row['arms'][arm]['checks'][name]['status']) for row in records
                if row['id'] in gold and name in gold[row['id']]['checks']]) for name in CHECKS}
            result['arms'][arm]['quality'] = quality
    if gold is not None:
        result['extraction'] = extraction_metrics(records, gold)
        controls = {identifier: compare_records(item['english'], item['gloss'])
                    for identifier, item in gold.items() if 'english' in item and 'gloss' in item}
        result['gold_contract_control'] = {name: detection_metrics([
            (gold[identifier]['checks'][name], checks[name]['status'])
            for identifier, checks in controls.items() if name in gold[identifier]['checks']]) for name in CHECKS}
    if stratify:
        result['strata'] = {}
        for dimension in ('split', 'annotation_kind', 'phenomenon'):
            groups = {}
            for row in records:
                key = ((gold or {}).get(row['id'], {}).get('annotation_kind', 'unlabeled')
                       if dimension == 'annotation_kind' else row.get(dimension, 'unspecified'))
                groups.setdefault(key or 'unspecified', []).append(row)
            result['strata'][dimension] = {key: evaluate(rows,
                {row['id']:gold[row['id']] for row in rows if row['id'] in gold} if gold is not None else None,
                stratify=False) for key, rows in groups.items()}
    return result


def write_reports(output, records, summary, gold=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    # A resumed run may replace only its own report files, never arbitrary inputs.
    from .runner import replace_json
    replace_json(output / 'summary.json', summary)
    from .analysis import analyze, render_report
    analysis = analyze(records, gold)
    queue = analysis.pop('review_queue')
    replace_json(output / 'analysis.json', analysis)
    (output/'report.md').write_text(render_report(summary, {**analysis,'review_queue':queue}), encoding='utf-8')
    with (output/'review_queue.jsonl').open('w',encoding='utf-8') as handle:
        for row in queue:
            handle.write(json.dumps(row,ensure_ascii=False)+'\n')
    with (output / 'checks.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=('id', 'arm', 'check', 'status', 'arm_status',
            'reason', 'english_value', 'gloss_value', 'english_evidence', 'gloss_evidence'))
        writer.writeheader()
        for row in records:
            for arm in ARMS:
                for name, check in row['arms'][arm]['checks'].items():
                    writer.writerow({'id': row['id'], 'arm': arm, 'check': name,
                        'status': check['status'], 'arm_status': row['arms'][arm]['status'],
                        'reason': check['reason'], **{key: json.dumps(check.get(key), ensure_ascii=False)
                        for key in ('english_value', 'gloss_value', 'english_evidence', 'gloss_evidence')}})


def export_annotations(input_path, output):
    pairs = load_pairs(input_path)
    output = protect_output(output, [input_path])
    if output.exists() and any(output.iterdir()):
        raise ValueError('Annotation output must be an empty or new directory')
    output.mkdir(parents=True, exist_ok=True)
    for side in ('english', 'gloss'):
        with (output / (side + '.jsonl')).open('x', encoding='utf-8') as handle:
            for pair in pairs:
                handle.write(json.dumps({'id': pair['id'], 'annotation_kind': 'unreviewed',
                    'record': record(pair[side], side, 'human-annotation')}, ensure_ascii=False) + '\n')
    with (output / 'checks.jsonl').open('x', encoding='utf-8') as handle:
        for pair in pairs:
            handle.write(json.dumps({'id': pair['id'], 'annotation_kind': 'unreviewed',
                'english': pair['english'], 'gloss': pair['gloss'],
                'checks': {name: 'UNKNOWN' for name in CHECKS}}, ensure_ascii=False) + '\n')
    write_json(output / 'instructions.json', {'procedure': [
        'Give english.jsonl and gloss.jsonl to separate blinded reviewers.',
        'Do not show checks.jsonl, other-side text, model outputs, or source gold before side annotations are frozen.',
        'Unknown facts are explicit unassessability judgments, not blank/missing labels.',
        'Adjudicate checks.jsonl after independent annotation; unmodified originals are not assumed faithful.',
        'Set completed annotation_kind to human-reviewed; merge by id with the assemble command.',
        'Keep all text and annotation files within the input data access restrictions.']})


def assemble_annotations(input_path, english_path, gloss_path, checks_path, output):
    pairs = load_pairs(input_path)
    protect_output(output, [input_path, english_path, gloss_path, checks_path])
    sheets = []
    for path in (english_path, gloss_path, checks_path):
        rows = [json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines() if line.strip()]
        mapping = {row['id']: row for row in rows}
        if len(mapping) != len(rows) or set(mapping) != {pair['id'] for pair in pairs}:
            raise ValueError('Annotation IDs must match inputs exactly and without duplicates')
        if any(row.get('annotation_kind') != 'human-reviewed' for row in rows):
            raise ValueError('Every annotation sheet must be explicitly human-reviewed')
        sheets.append(mapping)
    completed = []
    for pair in pairs:
        identifier = pair['id']
        checks = sheets[2][identifier]
        if checks['english'] != pair['english'] or checks['gloss'] != pair['gloss']:
            raise ValueError('Check annotation text differs from input')
        completed.append({'id': identifier, 'annotation_kind': 'human-reviewed',
            'english': sheets[0][identifier]['record'], 'gloss': sheets[1][identifier]['record'],
            'checks': checks['checks']})
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Validate in memory before creating the destination, through the same loader.
    import tempfile
    with tempfile.TemporaryDirectory() as directory:
        temporary = Path(directory) / 'gold.jsonl'
        temporary.write_text(''.join(json.dumps(row) + '\n' for row in completed), encoding='utf-8')
        load_gold(temporary, pairs)
    with output.open('x', encoding='utf-8') as handle:
        for row in completed:
            handle.write(json.dumps(row, ensure_ascii=False) + '\n')
