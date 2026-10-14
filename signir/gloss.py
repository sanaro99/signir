"""Independent conservative gloss extraction. Fixture annotations are not ASL grammar."""
import re
from .schema import record, fact, spans

# Intentionally independent of English analysis and lexical morphology.
ACTIONS = {'BUY', 'SELL', 'HELP', 'SEE', 'VISIT', 'LIKE'}
THINGS = {'APPLE', 'BOOK', 'DOG', 'CAT', 'TEACHER', 'STUDENT'}
COUNTS = {w: n for n, w in enumerate(('ZERO', 'ONE', 'TWO', 'THREE', 'FOUR', 'FIVE', 'SIX', 'SEVEN', 'EIGHT', 'NINE', 'TEN'))}


def is_number(token):
    return bool(re.fullmatch(r'[0-9]{1,18}', token))


def entity_label(token):
    if token in THINGS:
        return token
    if re.fullmatch(r'fs-[A-Z]+(?:-[A-Z]+)*', token):
        # Only one-letter sequences are joined; hyphenated names stay hyphenated.
        name = token[3:]
        parts = name.split('-')
        return 'NAME:' + (''.join(parts) if all(len(p) == 1 for p in parts) else name)
    return None


def extract_fixture_gloss(text):
    ir = record(text, 'gloss', 'gloss-rules-1')
    tokens = ir['tokens']
    ev = spans(text)
    entities, entity_ev, actions, role_values, polarity = [], [], [], {}, []
    unknown = []
    plain_entities = []
    for i, token in enumerate(tokens):
        if token in ACTIONS:
            actions.append((token, i))
        elif token.startswith(('AGENT:', 'PATIENT:')):
            role, label = token.split(':', 1)
            value = entity_label(label)
            if not value or role in role_values:
                unknown.append(i)
            else:
                role_values[role] = (value, i)
                entities.append(value)
                entity_ev.append(ev[i])
        elif token.startswith(('NEG:', 'POS:')):
            polarity.append((token.split(':', 1), i))
        elif token == 'NOT':
            polarity.append((['NEG', None], i))
        elif entity_label(token):
            plain_entities.append((entity_label(token), i))
        elif is_number(token) or token in COUNTS:
            pass
        else:
            unknown.append(i)
    # A repeated plain noun after PATIENT:X is a count attachment, not another
    # participant, only when immediately preceded by an explicit count.
    for value, i in plain_entities:
        attachment = i > 0 and (is_number(tokens[i-1]) or tokens[i-1] in COUNTS)
        if not (attachment and role_values.get('PATIENT', (None,))[0] == value):
            entities.append(value)
            entity_ev.append(ev[i])
    complete = bool(tokens) and not unknown and len(actions) == 1
    if not complete:
        for f in ir['facts'].values():
            f['reason'] = 'Unsupported gloss label, empty input, or ambiguous action count'
            f['evidence'] = ev
        return ir
    action, ai = actions[0]
    ir['facts']['action'] = fact(action, [ev[ai]], 'One supported action in explicit fragment')
    if entities:
        ir['facts']['entities'] = fact(entities, entity_ev, 'Explicit entities in supported fragment; repetition retained')
    if len(polarity) == 1 and polarity[0][0][1] in (None, action):
        (sign, scope), pi = polarity[0]
        ir['facts']['negation'] = fact({'action': action, 'negative': sign == 'NEG'}, [ev[ai], ev[pi]],
                                       'Explicit polarity scoped to the sole supported action')
    else:
        ir['facts']['negation']['reason'] = 'Missing, conflicting, or wrong-action polarity marker'
    numbers, number_ev, unattached = [], [], False
    for i, token in enumerate(tokens):
        if is_number(token) or token in COUNTS:
            entity = entity_label(tokens[i+1]) if i+1 < len(tokens) else None
            if entity is None:
                unattached = True
            else:
                numbers.append({'entity': entity, 'count': int(token) if is_number(token) else COUNTS[token]})
                number_ev.extend([ev[i], ev[i+1]])
    if numbers and not unattached:
        ir['facts']['numbers'] = fact(numbers, number_ev, 'Explicit adjacent count and entity in supported fragment')
    if set(role_values) == {'AGENT', 'PATIENT'}:
        ir['facts']['roles'] = fact({'action': action, 'agent': role_values['AGENT'][0], 'patient': role_values['PATIENT'][0]},
                                    [ev[ai], ev[role_values['AGENT'][1]], ev[role_values['PATIENT'][1]]],
                                    'Explicit fixture role labels; no role inferred from order')
    else:
        ir['facts']['roles']['reason'] = 'No complete explicit role annotation; gloss order is not role evidence'
    return ir


def extract_gloss(text):
    ir = extract_fixture_gloss(text)
    if any(f['state'] == 'KNOWN' for f in ir['facts'].values()):
        return ir
    from .natural import extract_natural_gloss
    return extract_natural_gloss(text)
