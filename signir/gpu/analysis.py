"""Offline controls and an actionable review queue; no extra model calls."""
from collections import Counter, defaultdict

from ..schema import CHECKS
from ..compare import canonical
from .evaluation import ARMS, detection_metrics, ratio, side_record
from .protocol import compare_records

SUPPORTED = tuple(name for name in CHECKS if name != 'roles')


def analyze(records, gold=None):
    gold = gold or {}
    controls = {name: [] for name in ('cpu_english_model_gloss', 'model_english_cpu_gloss',
                                     'gold_english_model_gloss', 'model_english_gold_gloss')}
    available = Counter()
    queue, alarms, attrition = [], {}, {}
    for row in records:
        identifier = row['id']
        cpu_a, cpu_b = (side_record(row, 'cpu', side) for side in ('english', 'gloss'))
        model_a, model_b = (side_record(row, 'structured', side) for side in ('english', 'gloss'))
        oracle = gold.get(identifier, {})
        options = {'cpu_english_model_gloss': (cpu_a, model_b),
                   'model_english_cpu_gloss': (model_a, cpu_b),
                   'gold_english_model_gloss': (oracle.get('english'), model_b),
                   'model_english_gold_gloss': (model_a, oracle.get('gloss'))}
        for name, (a, b) in options.items():
            if ((name == 'gold_english_model_gloss' and a is None) or
                    (name == 'model_english_gold_gloss' and b is None)):
                continue  # No oracle annotation: this pair is outside the control cohort.
            if a is not None and b is not None:
                available[name] += 1
                controls[name].append((identifier, compare_records(a, b)))
            else:
                controls[name].append((identifier, {field:{'status':'UNKNOWN'} for field in CHECKS}))
        reasons, priority = [], 0
        for name in SUPPORTED:
            statuses = {arm: row['arms'][arm]['checks'][name]['status'] for arm in ARMS}
            if 'MISMATCH' in statuses.values():
                reasons.append('candidate conflict: ' + name)
                priority += 20 if name in ('numbers', 'negation') else 10
            if len(set(statuses.values())) > 1:
                reasons.append('approach disagreement: ' + name)
                priority += 4
            if statuses['cpu'] == 'UNKNOWN' and statuses['structured'] != 'UNKNOWN':
                reasons.append('newly assessed by model: ' + name)
                priority += 2
        if any(row['arms'][arm]['status'] == 'error' for arm in ARMS):
            reasons.append('protocol/extraction failure')
            priority += 3
        if reasons:
            queue.append({'id': identifier, 'priority': priority, 'reasons': reasons,
                'english': row['english'], 'gloss': row['gloss'], 'arms': row['arms']})
    summaries = {}
    for name, cases in controls.items():
        summaries[name] = {'eligible_pairs': len(cases), 'pairs_ineligible': len(records)-len(cases),
            'pairs_available': available[name], 'pairs_unavailable':len(cases)-available[name],
            'additional_model_calls': 0,
            'quality_scope': ('pairs with the relevant oracle side; failed model sides abstain'
                if name in ('gold_english_model_gloss', 'model_english_gold_gloss') else
                'all labeled pairs; unavailable side records abstain'),
            'counts': {field: dict(Counter(checks[field]['status'] for _, checks in cases)) for field in CHECKS},
            'quality': {field: detection_metrics([(gold[identifier]['checks'][field], checks[field]['status'])
                for identifier, checks in cases if identifier in gold and field in gold[identifier]['checks']])
                for field in CHECKS} if gold and cases else None}
    for arm in ARMS:
        accounting = Counter()
        transitions = Counter()
        for row in records:
            for name in SUPPORTED:
                predicted = row['arms'][arm]['checks'][name]['status']
                baseline = row['arms']['cpu']['checks'][name]['status']
                transitions[baseline + '->' + predicted] += 1
                if predicted != 'MISMATCH':
                    continue
                accounting['total_alarms'] += 1
                expected = gold.get(row['id'], {}).get('checks', {}).get(name)
                category = {'MISMATCH': 'confirmed_error_alarms', 'MATCH': 'known_false_alarms',
                            'UNKNOWN': 'gold_unknown_alarms', None: 'unlabeled_alarms'}[expected]
                accounting[category] += 1
        alarms[arm] = {key: accounting[key] for key in ('total_alarms', 'confirmed_error_alarms',
            'known_false_alarms', 'gold_unknown_alarms', 'unlabeled_alarms')}
        alarms[arm]['confirmed_fraction_of_all_alarms'] = ratio(accounting['confirmed_error_alarms'], accounting['total_alarms']) if gold else None
        attrition[arm] = dict(transitions)
    overlap = defaultdict(set)
    for row in records:
        overlap[' '.join(row['gloss'].split())].add(row.get('split', 'diagnostic'))
    return {'controls': summaries, 'alarm_accountability': alarms,
            'cpu_to_approach_transitions': attrition,
            'cross_split_identical_gloss_groups': sum(len(splits) > 1 for splits in overlap.values()),
            'review_queue': sorted(queue, key=lambda row: (-row['priority'], row['id'])),
            'limits': ['Review queue items are candidates, not verified translation errors.',
                       'Hybrid and gold-side controls require no additional GPU calls.',
                       'Current entity/event alignment can still abstain even with correct extracted facts.',
                       'Confirmed alarm fraction is not a precision estimate for unreviewed/unknown cases.']}


def render_report(summary, analysis):
    lines = ['# SignIR experiment results', '',
        'These are scoped fact checks. Review candidate findings before interpreting translation quality.', '',
        '| Approach | Assessed supported checks | Failed pairs | Candidate alarms |',
        '|---|---:|---:|---:|']
    for arm in ARMS:
        values = summary['arms'][arm]
        lines.append(f"| {arm} | {values['assessed_checks']}/{values['possible_supported_checks']} | {values['failed_pairs']} | {analysis['alarm_accountability'][arm]['total_alarms']} |")
    lines += ['', '## Useful outputs', '',
        '- `review_queue.jsonl`: conflicts, approach disagreements, new assessments and failures with original evidence.',
        '- `analysis.json`: CPU/model hybrids, optional gold-side controls, alarm accountability and coverage transitions.',
        '- `summary.json`: scoped metrics, separated by split, annotation source and phenomenon.',
        '- `manifest.json`: execution, cache and CUDA batch timing (when actual inference ran).', '',
        f"Gold-labeled pairs: {summary['gold_pairs']}. Review candidates: {len(analysis['review_queue'])}.", '',
        '## Interpretation', '',
        'Without reviewed gold, coverage and disagreements are diagnostic outcomes; accuracy is unmeasured.',
        'Authored challenge results and human-reviewed natural results appear in separate strata.',
        'The frozen CPU baseline does not include unrelated uncommitted research repairs.',
        'Mixed-batch amortized timing does not measure individual approach latency.',
        'A negative result is useful when hybrid/oracle controls identify which stage remains limiting.', '']
    return '\n'.join(lines)


def compare_runs(left, right):
    a, b = ({row['id']:row for row in rows} for rows in (left,right))
    if set(a)!=set(b):
        raise ValueError('Repeat comparison requires the same pair IDs')
    changes = []
    for identifier in a:
        if any(a[identifier][side]!=b[identifier][side] for side in ('english','gloss')):
            raise ValueError('Repeat comparison requires identical original texts')
        for arm in ARMS:
            for name in CHECKS:
                before = a[identifier]['arms'][arm]['checks'][name]['status']
                after = b[identifier]['arms'][arm]['checks'][name]['status']
                if before!=after:
                    changes.append({'id':identifier,'arm':arm,'field':name,'kind':'status',
                                    'before':before,'after':after})
            if arm=='structured':
                for side in ('english','gloss'):
                    first, second = (side_record(item[identifier],arm,side) for item in (a,b))
                    for name in CHECKS:
                        values = [(ir['facts'][name]['state'], canonical(ir['facts'][name]['value']))
                                  if ir else None for ir in (first,second)]
                        if values[0]!=values[1]:
                            changes.append({'id':identifier,'arm':arm,'field':name,'side':side,
                                'kind':'fact-value','before':values[0],'after':values[1]})
    return {'paired_pairs':len(a), 'status_changes':sum(row['kind']=='status' for row in changes),
            'fact_value_changes':sum(row['kind']=='fact-value' for row in changes), 'changes':changes,
            'limits':['Stable outputs are not evidence of correctness.',
                      'Use fresh run directories for cold replication; a warm cache is not a repeat.']}
