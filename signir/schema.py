"""Small serializable SignIR records; character offsets index the original text."""
import re

VERSION = '1.0'
CHECKS = ('entities', 'action', 'negation', 'numbers', 'roles')


def spans(text):
    return [{'start': m.start(), 'end': m.end(), 'text': m.group()}
            for m in re.finditer(r'\S+', text)]


def fact(value=None, evidence=(), reason='Insufficient explicit evidence'):
    return {'state': 'UNKNOWN' if value is None else 'KNOWN', 'value': value,
            'evidence': list(evidence), 'reason': reason}


def record(text, language, extractor):
    return {'version': VERSION, 'language': language, 'text': text,
            'tokens': text.split(), 'extractor': extractor,
            'facts': {k: fact() for k in CHECKS}}


def evidence(text, start, end):
    return {'start': start, 'end': end, 'text': text[start:end]}


def validate(ir):
    if ir.get('version') != VERSION or set(ir.get('facts', {})) != set(CHECKS):
        raise ValueError('Unsupported or incomplete SignIR schema')
    if ir.get('language') not in ('english', 'gloss') or not isinstance(ir.get('text'), str):
        raise ValueError('Invalid SignIR language/text')
    for name, f in ir['facts'].items():
        if f.get('state') not in ('KNOWN', 'UNKNOWN'):
            raise ValueError('Invalid fact state')
        v = f.get('value')
        if (f['state'] == 'UNKNOWN') != (v is None):
            raise ValueError('UNKNOWN must have null value; KNOWN must have a value')
        if f['state'] == 'KNOWN':
            if not f.get('evidence'):
                raise ValueError('Known facts require evidence')
            if name == 'entities' and (not isinstance(v, list) or not v or not all(isinstance(x, str) for x in v)):
                raise ValueError('entities must be a nonempty string list')
            if name == 'action' and (not isinstance(v, str) or not v):
                raise ValueError('action must be a string')
            if name == 'negation' and (not isinstance(v, dict) or set(v) != {'action', 'negative'} or type(v['negative']) is not bool):
                raise ValueError('Invalid scoped negation')
            if name == 'roles' and (not isinstance(v, dict) or set(v) != {'action', 'agent', 'patient'}):
                raise ValueError('Invalid roles')
            if name == 'numbers' and (not isinstance(v, list) or not v or any(not isinstance(x, dict) or set(x) != {'entity', 'count'} or type(x['count']) is not int or x['count'] < 0 for x in v)):
                raise ValueError('Invalid number attachments')
        for s in f.get('evidence', []):
            if not (0 <= s['start'] < s['end'] <= len(ir['text'])) or ir['text'][s['start']:s['end']] != s['text']:
                raise ValueError('Evidence does not match original text')
