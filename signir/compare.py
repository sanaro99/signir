"""Deterministic comparison, independent of how SignIR records were obtained."""
import json
from .schema import CHECKS, validate
from .english import extract_english
from .gloss import extract_gloss


def canonical(value):
    if isinstance(value, list):
        return sorted(json.dumps(x, sort_keys=True) for x in value)
    return value


def compare(english, gloss):
    validate(english)
    validate(gloss)
    result = {}
    for name in CHECKS:
        a, b = english['facts'][name], gloss['facts'][name]
        status = 'UNKNOWN'
        reason = f"English: {a['reason']}; gloss: {b['reason']}"
        if a['state'] == b['state'] == 'KNOWN':
            # Comparing polarity/roles of different actions is not an alignment.
            if name in ('negation', 'roles') and a['value']['action'] != b['value']['action']:
                reason = 'Different actions: no supported event alignment'
            elif name in ('entities', 'numbers') and len(a['value']) != len(b['value']):
                reason = 'Unequal observed inventories: omitted or repeated evidence cannot establish a complete alignment'
            elif name == 'numbers' and sorted(x['entity'] for x in a['value']) != sorted(x['entity'] for x in b['value']):
                reason = 'Number attachments refer to different entities; no supported count alignment'
            elif name == 'entities' and (a.get('scope') or b.get('scope')) and canonical(a['value']) != canonical(b['value']):
                reason = 'Different lexical mention inventories; synonymy and omitted/ambiguous labels need review, not an automatic entity error'
            else:
                status = 'MATCH' if canonical(a['value']) == canonical(b['value']) else 'MISMATCH'
                reason = 'Equal supported facts' if status == 'MATCH' else 'Conflicting explicit supported facts'
        result[name] = {'status': status, 'reason': reason,
                        'scope': a.get('scope') or b.get('scope') or 'supported fixture facts',
                        'english_value': a['value'], 'gloss_value': b['value'],
                        'english_evidence': a['evidence'], 'gloss_evidence': b['evidence']}
        if (a.get('scope') or b.get('scope')) and status != 'UNKNOWN':
            result[name]['reason'] += '; assessed scope: ' + result[name]['scope']
    return result


def check_pair(english, gloss):
    a, b = extract_english(english), extract_gloss(gloss)
    return {'english': a, 'gloss': b, 'checks': compare(a, b)}
