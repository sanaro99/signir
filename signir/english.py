"""Conservative English grammar. No gloss input and no statistical parser."""
import re
from .schema import record, fact, evidence

VERBS = {'buy': 'BUY', 'buys': 'BUY', 'bought': 'BUY', 'sell': 'SELL', 'sells': 'SELL',
         'sold': 'SELL', 'help': 'HELP', 'helps': 'HELP', 'helped': 'HELP',
         'see': 'SEE', 'sees': 'SEE', 'saw': 'SEE', 'visit': 'VISIT', 'visits': 'VISIT',
         'visited': 'VISIT', 'like': 'LIKE', 'likes': 'LIKE', 'liked': 'LIKE'}
NOUNS = {'apple': 'APPLE', 'apples': 'APPLE', 'book': 'BOOK', 'books': 'BOOK',
         'dog': 'DOG', 'dogs': 'DOG', 'cat': 'CAT', 'cats': 'CAT',
         'teacher': 'TEACHER', 'teachers': 'TEACHER', 'student': 'STUDENT', 'students': 'STUDENT'}
NUMBERS = {w: n for n, w in enumerate(('zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten'))}
NAME = r'[A-Z][a-z]+(?:-[A-Z][a-z]+)*'
NON_NAMES = {'He', 'She', 'It', 'They', 'We', 'You', 'This', 'That', 'These', 'Those', 'Who', 'Someone', 'Everyone', 'Nobody', 'Somebody', 'Anyone', 'Everybody'}
GRAMMAR = re.compile(rf'(?P<agent>{NAME}) (?:(?P<aux>does|did) (?P<neg>not) )?(?P<verb>[a-z]+) (?P<object>.+?)[.]?')
OBJECT = re.compile(rf'(?:(?P<number>[0-9]{{1,18}}|{"|".join(NUMBERS)}) )?(?P<entity>{NAME}|{"|".join(NOUNS)})')


def extract_fixture_english(text):
    ir = record(text, 'english', 'english-rules-1')
    m = GRAMMAR.fullmatch(text)
    if not m or m['verb'] not in VERBS or m['agent'] in NON_NAMES:
        for f in ir['facts'].values():
            f['reason'] = 'Outside supported English single-clause grammar'
        return ir
    # Do not accept inflected verbs after do-support (e.g. does not bought).
    if m['aux'] and m['verb'] not in ('buy', 'sell', 'help', 'see', 'visit', 'like'):
        return ir
    objects = []
    offset = m.start('object')
    for chunk in m['object'].split(' and '):
        obj = OBJECT.fullmatch(chunk)
        if not obj or obj['entity'] in NON_NAMES:
            return ir
        objects.append((obj, offset))
        offset += len(chunk) + len(' and ')
    action = VERBS[m['verb']]
    agent = 'NAME:' + m['agent'].upper()
    agent_ev = evidence(text, m.start('agent'), m.end('agent'))
    verb_ev = evidence(text, m.start('verb'), m.end('verb'))
    entities, entity_ev, counts, count_ev = [agent], [agent_ev], [], []
    for obj, offset in objects:
        entity = NOUNS.get(obj['entity'], 'NAME:' + obj['entity'].upper())
        ev = evidence(text, offset + obj.start('entity'), offset + obj.end('entity'))
        entities.append(entity)
        entity_ev.append(ev)
        if obj['number'] is not None:
            n = obj['number']
            counts.append({'entity': entity, 'count': int(n) if n.isdigit() else NUMBERS[n]})
            count_ev.extend([evidence(text, offset + obj.start('number'), offset + obj.end('number')), ev])
    ir['facts']['entities'] = fact(entities, entity_ev, 'Complete supported English clause')
    ir['facts']['action'] = fact(action, [verb_ev], 'Supported lexical verb')
    ir['facts']['negation'] = fact({'action': action, 'negative': bool(m['neg'])},
                                    [verb_ev] + ([evidence(text, m.start('neg'), m.end('neg'))] if m['neg'] else []),
                                    'Polarity of the complete supported English clause')
    if counts:
        ir['facts']['numbers'] = fact(counts, count_ev, 'Explicit count attached within noun phrase')
    if len(objects) == 1:
        ir['facts']['roles'] = fact({'action': action, 'agent': agent, 'patient': entities[1]},
                                   [agent_ev, verb_ev, entity_ev[1]], 'Supported English active transitive clause')
    return ir


def _candidates(label):
    if label.startswith('NAME:'):
        return [label[5:].lower()]
    from .natural import lemmas
    return sorted(lemmas(label))


def fixture_content(ir):
    """Content inventory for a sentence parsed by the fixture grammar."""
    facts = ir['facts']
    entities = []
    if facts['entities']['state'] == 'KNOWN':
        for label, ev in zip(facts['entities']['value'], facts['entities']['evidence']):
            entities.append({'label': label, 'candidates': _candidates(label), 'dep': None,
                             'name': label.startswith('NAME:'), 'evidence': [ev]})
    action = facts['action']
    content = {'entities': entities,
               'predicates': [{'label': action['value'], 'candidates': _candidates(action['value']), 'light': False,
                               'dictionary': True, 'evidence': action['evidence']}] if action['state'] == 'KNOWN' else [],
               'negative_sentence': facts['negation']['value']['negative'] if facts['negation']['state'] == 'KNOWN' else None,
               'negation_evidence': facts['negation']['evidence'][1:]}
    if facts['roles']['state'] == 'KNOWN':
        v = facts['roles']['value']
        content['roles'] = {k: _candidates(v[k]) for k in ('action', 'agent', 'patient')}
    return content


def extract_english_for_check(text):
    """Fixture grammar when it parses the sentence (it is exact there), else spaCy; both with content."""
    ir = extract_fixture_english(text)
    if any(f['state'] == 'KNOWN' for f in ir['facts'].values()):
        ir['content'] = fixture_content(ir)
        return ir
    from .natural import extract_natural_english
    return extract_natural_english(text)


def extract_english(text):
    ir = extract_fixture_english(text)
    if any(f['state'] == 'KNOWN' for f in ir['facts'].values()):
        return ir
    from .natural import extract_natural_english
    return extract_natural_english(text)
