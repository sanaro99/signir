"""Independent model requests and strict boundaries for experimental outputs."""
import copy
import json
from pathlib import Path
import re

from ..compare import compare
from ..schema import CHECKS, record, validate

PROMPTS = Path(__file__).with_name('prompts')
STATUSES = ('MATCH', 'MISMATCH', 'UNKNOWN')
SCOPES = {'entities': 'lexical mentions', 'action': 'single lexical predicate',
          'negation': 'one explicitly scoped predicate', 'numbers': 'explicit number attachments',
          'roles': 'explicit active roles'}


def default_config():
    return {'version': 1, 'model': 'nvidia/Qwen3.8-27B-NVFP4', 'seed': 42,
            'temperature': 0.0, 'top_p': 1.0, 'max_tokens': 3072,
            'max_model_len': 8192, 'gpu_memory_utilization': 0.65,
            'batch_size': 4, 'enforce_eager': True, 'enable_prefix_caching': False}


def validate_config(config):
    allowed = set(default_config())
    if not allowed - {'enable_prefix_caching'} <= set(config) <= allowed or config['version'] != 1:
        raise ValueError('Config must contain exactly the version-1 configuration fields')
    if not isinstance(config['model'], str) or not re.fullmatch(r'[\w.-]+/[\w.-]+', config['model']):
        raise ValueError('Expected a Hugging Face owner/model identifier')
    for key in ('seed', 'max_tokens', 'max_model_len', 'batch_size'):
        if type(config[key]) is not int or config[key] < (0 if key == 'seed' else 1):
            raise ValueError(f'Invalid configuration integer: {key}')
    for key in ('temperature', 'top_p', 'gpu_memory_utilization'):
        if type(config[key]) not in (int, float):
            raise ValueError(f'Invalid numeric configuration: {key}')
    if not (0 <= config['temperature'] <= 2 and 0 < config['top_p'] <= 1
            and 0 < config['gpu_memory_utilization'] < 1
            and config['max_tokens'] < config['max_model_len']
            and type(config['enforce_eager']) is bool
            and type(config.get('enable_prefix_caching', False)) is bool):
        raise ValueError('Invalid decoding or engine limits')
    return config


def obj(properties):
    return {'type': 'object', 'properties': properties,
            'required': list(properties), 'additionalProperties': False}


STRING = {'type': 'string', 'minLength': 1}
SPAN = obj({'start': {'type': 'integer', 'minimum': 0},
            'end': {'type': 'integer', 'minimum': 1}, 'text': STRING})
SPANS = {'type': 'array', 'items': SPAN}
VALUES = {'entities': {'type': 'array', 'minItems': 1, 'items': STRING},
          'action': STRING,
          'negation': obj({'action': STRING, 'negative': {'type': 'boolean'}}),
          'numbers': {'type': 'array', 'minItems': 1,
                      'items': obj({'entity': STRING, 'count': {'type': 'integer', 'minimum': 0}})},
          'roles': obj({'action': STRING, 'agent': STRING, 'patient': STRING})}


def response_schema(task):
    if task in ('english', 'gloss'):
        properties = {}
        for name in CHECKS:
            known = obj({'state': {'const': 'KNOWN'}, 'value': VALUES[name],
                         'reason': STRING, 'evidence': {**SPANS, 'minItems': 1}})
            unknown = obj({'state': {'const': 'UNKNOWN'}, 'value': {'type': 'null'},
                           'reason': STRING, 'evidence': SPANS})
            properties[name] = {'anyOf': [known, unknown]}
        return obj({'facts': obj(properties)})
    if task == 'judge':
        return obj({'checks': obj({name: obj({'status': {'enum': list(STATUSES)},
            'reason': STRING, 'english_evidence': SPANS, 'gloss_evidence': SPANS}) for name in CHECKS})})
    raise ValueError('Unknown experiment task')


def make_request(task, pair):
    schema = response_schema(task)
    if task in ('english', 'gloss'):
        payload = {'language': task, 'text': pair[task]}
    else:
        payload = {'english': pair['english'], 'gloss': pair['gloss']}
    system = (PROMPTS / f'{task}.txt').read_text(encoding='utf-8')
    system += '\nReturn only JSON conforming to this schema:\n' + json.dumps(schema)
    return {'task': task, 'messages': [{'role': 'system', 'content': system},
            {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}], 'schema': schema}


def exact_keys(value, keys, label):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ValueError(f'Invalid {label} fields')


def label(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Z][A-Z0-9:_/#.+-]*', value):
        raise ValueError('Canonical labels must be nonempty uppercase labels')


def validate_spans(evidence, text):
    if not isinstance(evidence, list):
        raise ValueError('Evidence must be a list')
    for span in evidence:
        exact_keys(span, ('start', 'end', 'text'), 'evidence')
        if (type(span['start']) is not int or type(span['end']) is not int
                or not 0 <= span['start'] < span['end'] <= len(text)
                or text[span['start']:span['end']] != span['text']):
            raise ValueError('Evidence does not index the unchanged original text')


def parse_extraction(payload, text, language):
    exact_keys(payload, ('facts',), 'extraction')
    exact_keys(payload['facts'], CHECKS, 'facts')
    ir = record(text, language, 'gpu-independent-1')
    for name in CHECKS:
        f = copy.deepcopy(payload['facts'][name])
        exact_keys(f, ('state', 'value', 'evidence', 'reason'), 'fact')
        if not isinstance(f['reason'], str) or not f['reason'].strip():
            raise ValueError('Every fact needs a reason')
        validate_spans(f['evidence'], text)
        if f['state'] not in ('KNOWN', 'UNKNOWN') or (f['state'] == 'UNKNOWN') != (f['value'] is None):
            raise ValueError('Invalid KNOWN/UNKNOWN value')
        if f['state'] == 'KNOWN':
            value = f['value']
            if not f['evidence']:
                raise ValueError('A known fact requires evidence')
            if name == 'entities':
                if not isinstance(value, list) or not value:
                    raise ValueError('Entities must be a nonempty list')
                for item in value:
                    label(item)
            elif name == 'action':
                label(value)
            elif name in ('roles', 'negation'):
                keys = ('action', 'negative') if name == 'negation' else ('action', 'agent', 'patient')
                exact_keys(value, keys, name)
                for key in keys:
                    if key != 'negative':
                        label(value[key])
                if name == 'negation' and type(value['negative']) is not bool:
                    raise ValueError('Polarity must be boolean')
            elif name == 'numbers':
                if not isinstance(value, list) or not value:
                    raise ValueError('Numbers must be a nonempty list')
                for item in value:
                    exact_keys(item, ('entity', 'count'), 'number')
                    label(item['entity'])
                    if type(item['count']) is not int or not 0 <= item['count'] < 10**18:
                        raise ValueError('Counts must be exact supported integers')
            if language == 'gloss':
                if name == 'roles':
                    raise ValueError('This experiment does not assess gloss roles')
                if name == 'negation' and not value['negative'] and 'POS:' + value['action'] not in text.split():
                    raise ValueError('Absent gloss negation is not positive polarity evidence')
        f['scope'] = SCOPES[name]
        ir['facts'][name] = f
    validate(ir)
    return ir


def parse_judge(payload, english, gloss):
    exact_keys(payload, ('checks',), 'judge')
    exact_keys(payload['checks'], CHECKS, 'judge checks')
    result = copy.deepcopy(payload['checks'])
    for name, check in result.items():
        exact_keys(check, ('status', 'reason', 'english_evidence', 'gloss_evidence'), 'judgment')
        if check['status'] not in STATUSES or not isinstance(check['reason'], str) or not check['reason'].strip():
            raise ValueError('Invalid judgment status/reason')
        for side, text in (('english', english), ('gloss', gloss)):
            validate_spans(check[side + '_evidence'], text)
            if check['status'] != 'UNKNOWN' and not check[side + '_evidence']:
                raise ValueError('Assessed judgments require evidence from both sides')
        if name == 'roles' and check['status'] != 'UNKNOWN':
            raise ValueError('This experiment does not assess gloss roles')
        check['scope'] = SCOPES[name]
    return result


def compare_records(english, gloss):
    """Use core comparison plus the current documented conservative guards."""
    if english['language'] != 'english' or gloss['language'] != 'gloss':
        raise ValueError('Expected English then gloss')
    result = compare(english, gloss, missing=False)
    for name in CHECKS:
        a, b = english['facts'][name], gloss['facts'][name]
        if a['state'] != 'KNOWN' or b['state'] != 'KNOWN':
            continue
        reason = None
        if name == 'roles':
            reason = 'Gloss roles are outside this experiment scope'
        elif name == 'numbers' and any(len({x['entity'] for x in f['value']}) != len(f['value']) for f in (a, b)):
            reason = 'Repeated count entities need occurrence alignment'
        elif name == 'action' and a['value'] != b['value'] and any(f['value'].startswith('PROPERTY:') for f in (a, b)):
            reason = 'Different property interpretations need sense alignment'
        if reason:
            result[name]['status'], result[name]['reason'] = 'UNKNOWN', reason
    result['roles']['status'] = 'UNKNOWN'
    result['roles']['reason'] = 'Gloss roles are outside this experiment scope'
    return result
