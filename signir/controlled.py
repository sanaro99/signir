"""Authored artificial fixtures, not sampled or transformed private corpus data."""
from copy import deepcopy

from .schema import CHECKS


def build_fixtures():
    rows = []
    # Distinct documents and wording, with preassigned development/test families.
    families = [('Alice', 'Bob', 'dev'), ('Carol', 'David', 'dev'),
                ('Emma', 'Frank', 'dev'), ('Grace', 'Henry', 'dev'),
                ('Iris', 'James', 'test'), ('Kate', 'Liam', 'test'),
                ('Maya', 'Noah', 'test'), ('Olivia', 'Peter', 'test')]
    for i, (agent, patient, split) in enumerate(families):
        stem = f'fixture-{i:02}'
        n = i + 2
        original = f'AGENT:fs-{agent.upper()} BUY PATIENT:APPLE {n} APPLE NEG:BUY'
        base = {'id': stem, 'source_group': stem, 'document_id': stem, 'split': split,
                'english': f'{agent} does not buy {n} apples.', 'gloss': original,
                'reference_gloss': original, 'cohort': 'synthetic_reference',
                'provenance': {'kind': 'synthetic', 'version': 'authored-fixtures-1',
                               'annotation_convention': 'explicit-fixture-v1'},
                'review': {'status': 'authored_specification', 'qualified_asl_review': False},
                'expected': dict.fromkeys(CHECKS, 'MATCH')}
        # Gold values are authored from the fixture specification, never extracted.
        def gold_values(who, count, action='BUY', negative=True):
            return {'entities': ['NAME:' + who.upper(), 'APPLE'], 'action': action,
                    'negation': {'action': action, 'negative': negative},
                    'numbers': [{'entity': 'APPLE', 'count': count}],
                    'roles': {'action': action, 'agent': 'NAME:' + who.upper(), 'patient': 'APPLE'}}
        base['gold'] = {'english': gold_values(agent, n), 'gloss': gold_values(agent, n)}
        rows.append(base)
        changes = [
            ('entities', original.replace(f'fs-{agent.upper()}', 'fs-ZOE'),
             {'entities': 'MISMATCH', 'roles': 'MISMATCH'}, 'Replace one explicit named agent; role value necessarily also changes.', gold_values('Zoe', n)),
            ('action', original.replace('BUY', 'SELL'),
             {'action': 'MISMATCH', 'negation': 'UNKNOWN', 'roles': 'UNKNOWN'}, 'Replace one event action and its annotation references consistently; event alignment is lost.', gold_values(agent, n, 'SELL')),
            ('negation', original.replace('NEG:BUY', 'POS:BUY'),
             {'negation': 'MISMATCH'}, 'Explicit opposite polarity for the same event.', gold_values(agent, n, negative=False)),
            ('numbers', original.replace(f'{n} APPLE', f'{n+1} APPLE'),
             {'numbers': 'MISMATCH'}, 'Change only the count attached to APPLE.', gold_values(agent, n+1)),
        ]
        for field, gloss, overrides, reason, gold in changes:
            row = deepcopy(base)
            row.update(id=stem + '-' + field, variant_of=stem, gloss=gloss,
                       cohort='controlled', error_type=field,
                       change={'original_pair_id': stem, 'original_gloss': original,
                               'modified_gloss': gloss, 'affected_check': field, 'reason': reason})
            row['expected'].update(overrides)
            row['gold']['gloss'] = gold
            rows.append(row)
        missing = deepcopy(base)
        missing.update(id=stem + '-missing-negation', variant_of=stem,
                       gloss=original.replace(' NEG:BUY', ''), cohort='controlled',
                       change={'original_pair_id': stem, 'original_gloss': original,
                               'affected_check': 'negation', 'reason': 'Removed marker means insufficient polarity evidence, not proven positive meaning.'})
        missing['expected']['negation'] = 'UNKNOWN'
        missing['gold']['gloss']['negation'] = None
        rows.append(missing)
        role_original = f'AGENT:fs-{agent.upper()} HELP PATIENT:fs-{patient.upper()} POS:HELP'
        role = deepcopy(base)
        role.update(id=stem+'-role-base', variant_of=stem, english=f'{agent} helps {patient}.',
                    gloss=role_original, reference_gloss=role_original)
        role['expected']['numbers'] = 'UNKNOWN'
        values = {'entities': ['NAME:'+agent.upper(), 'NAME:'+patient.upper()], 'action': 'HELP',
                  'negation': {'action': 'HELP', 'negative': False}, 'numbers': None,
                  'roles': {'action': 'HELP', 'agent': 'NAME:'+agent.upper(), 'patient': 'NAME:'+patient.upper()}}
        role['gold'] = {'english': deepcopy(values), 'gloss': deepcopy(values)}
        rows.append(role)
        reversal = deepcopy(role)
        reversal.update(id=stem+'-roles', variant_of=role['id'],
                        gloss=f'PATIENT:fs-{agent.upper()} HELP AGENT:fs-{patient.upper()} POS:HELP',
                        cohort='controlled', error_type='roles',
                        change={'original_pair_id': role['id'], 'original_gloss': role_original,
                                'affected_check': 'roles', 'reason': 'Swap explicit role labels, retaining the same two people and action; not an arbitrary gloss shuffle.'})
        reversal['expected']['roles'] = 'MISMATCH'
        reversal['gold']['gloss']['roles'] = {'action': 'HELP', 'agent': 'NAME:'+patient.upper(), 'patient': 'NAME:'+agent.upper()}
        rows.append(reversal)
    return rows
