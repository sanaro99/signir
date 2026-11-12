"""CPU rule readers that emit SignIR 2.0 graphs.

The English reader uses the spaCy dependency parse; the gloss reader uses the same
independent dictionary/local-pattern analysis as the legacy checker and never sees
the English. These graphs let the event comparator run without a model and give a
deterministic baseline for model readers. They are conservative: labels are
lemmas, synonyms go in ``concepts`` (never used for equality), and anything the
rules cannot place is recorded as unresolved.
"""
import re

from .schema import Graph

PERSON_PRONOUNS = {'i', 'me', 'you', 'he', 'him', 'she', 'her', 'we', 'us', 'they', 'them'}
CONDITIONAL_MARKS = {'if', 'unless'}
POSSIBLE = {'can', 'could', 'may', 'might'}
OBLIGATORY = {'must', 'should', 'ought'}
REPORTING = {'say', 'tell', 'think', 'believe', 'claim', 'report', 'hear', 'know'}
NONMANUAL_LABELS = ('negation', 'topic', 'yes_no_question', 'wh_question', 'conditional')
GLOSS_CONDITIONAL = {'IF', '#IF', 'SUPPOSE'}


def _span(text, start, end):
    return {'start': start, 'end': end, 'text': text[start:end]}


def _nonmanual(nmm):
    return [{'label': k, 'value': bool(v)} for k, v in sorted((nmm or {}).items()) if k in NONMANUAL_LABELS]


def english_graph(text):
    from ..natural import (dictionary, english_candidates, english_label, english_pipeline, is_filler,
                           numeric, numeric_phrase)
    doc = english_pipeline()(text.replace('`', "'"))
    ev = lambda t: _span(text, t.idx, t.idx + len(t))
    nouns = [t for t in doc if t.pos_ in ('NOUN', 'PROPN') and not is_filler(t)
             and not (t.dep_ == 'amod' and 'ADJ' in dictionary(t.text))
             and not (t.pos_ == 'PROPN' and t.dep_ == 'compound' and t.head.pos_ == 'PROPN')]
    verbs = [t for t in doc if t.pos_ == 'VERB' and t.lemma_ != 'be']
    verb_ids = {t.i: f'e{n}' for n, t in enumerate(verbs)}
    mentions = []
    for t in nouns:
        label = english_label(t).removeprefix('NAME:').lower()
        mentions.append({'id': f'm{t.i}', 'label': label, 'kind': 'other' if t.pos_ == 'PROPN' else 'thing',
                         'form': 'name' if t.pos_ == 'PROPN' else 'lexical',
                         'concepts': sorted(set(english_candidates(t)) - {label}), 'evidence': [ev(t)]})

    def governor(t):
        """Nearest verb in the head chain: the event this noun participates in."""
        seen = set()
        while t.i not in verb_ids and t.head.i != t.i and t.i not in seen:
            seen.add(t.i)
            t = t.head
        return t.i if t.i in verb_ids else None

    events, unresolved = [], []
    for v in verbs:
        eid = verb_ids[v.i]
        parts = [t for t in nouns if governor(t) == v.i]
        passive = any(c.dep_ in ('nsubjpass', 'auxpass') for c in v.children)
        roles = []
        for t in parts:
            role = {'nsubj': 'agent', 'dobj': 'patient', 'nsubjpass': 'patient', 'iobj': 'recipient',
                    'dative': 'recipient'}.get(t.dep_) if t.head == v else None
            if t.dep_ == 'pobj' and t.head.dep_ == 'agent' and t.head.head == v and passive:
                role = 'agent'
            if role:
                roles.append({'role': role, 'mention_id': f'm{t.i}', 'basis': 'syntactic', 'evidence': [ev(t)]})
        negators = [c for c in v.children if c.dep_ == 'neg']
        negators += [c for a in v.children if a.dep_ in ('aux', 'auxpass') for c in a.children if c.dep_ == 'neg']
        negative_word = any(c.lower_ in ('never', 'no', 'nobody', 'nothing', 'none') for c in v.subtree
                            if governor(c) in (v.i, None) and c.i != v.i)
        if negators:
            polarity = {'value': 'negative', 'basis': 'syntactic', 'evidence': [ev(v)] + [ev(c) for c in negators]}
        elif negative_word:
            polarity = {'value': 'unknown', 'basis': 'unknown', 'evidence': []}
        else:
            polarity = {'value': 'positive', 'basis': 'syntactic', 'evidence': [ev(v)]}
        marks = [c for c in v.children if c.dep_ == 'mark' and c.lower_ in CONDITIONAL_MARKS]
        auxes = [c for c in v.children if c.dep_ == 'aux']
        parent = verb_ids.get(v.head.i) if v.head.i != v.i else None
        if marks:
            scope = {'kind': 'conditional', 'parent_event': parent, 'evidence': [ev(c) for c in marks]}
        elif v.dep_ == 'ccomp' and v.head.lemma_ in REPORTING and parent:
            scope = {'kind': 'reported', 'parent_event': parent, 'evidence': [ev(v.head)]}
        elif v.sent[-1].text == '?' and v.dep_ == 'ROOT':
            scope = {'kind': 'question', 'evidence': [ev(v.sent[-1])]}
        elif any(a.lower_ in POSSIBLE for a in auxes):
            scope = {'kind': 'possible', 'evidence': [ev(a) for a in auxes if a.lower_ in POSSIBLE]}
        elif any(a.lower_ in OBLIGATORY for a in auxes):
            scope = {'kind': 'obligatory', 'evidence': [ev(a) for a in auxes if a.lower_ in OBLIGATORY]}
        else:
            scope = {'kind': 'asserted', 'evidence': [ev(v)]}
        quantities = []
        for t in parts:
            nums = [c for c in t.children if c.dep_ == 'nummod']
            if len(nums) != 1:
                continue
            words = [c for c in nums[0].subtree if c.pos_ == 'NUM']
            if not words:
                continue
            a, b = min(c.i for c in words), max(c.i for c in words)
            value = numeric_phrase([c.text for c in doc[a:b + 1]])
            if value is None and a == b:
                value = numeric(doc[a].text.replace(',', ''))
            if value is None:
                unresolved.append({'reason': 'unresolved_quantity', 'detail': doc[a:b + 1].text,
                                   'evidence': [_span(text, doc[a].idx, doc[b].idx + len(doc[b]))]})
                continue
            money = any(c.text in ('$', '£', '€') for c in nums[0].children) or any(c.text in ('$', '£', '€')
                                                                                for c in t.children)
            quantities.append({'mention_id': f'm{t.i}', 'kind': 'money' if money else 'count',
                               'unit': 'dollar' if money else 'item', 'value': str(value), 'relation': 'eq',
                               'evidence': [_span(text, doc[a].idx, doc[b].idx + len(doc[b]))]})
        complete = bool(roles) and {r['mention_id'] for r in roles} == {f'm{t.i}' for t in parts}
        events.append({'id': eid, 'predicate': english_label(v).lower(), 'roles_complete': complete,
                       'concepts': sorted(set(english_candidates(v)) - {english_label(v).lower()}),
                       'evidence': [ev(v)], 'participants': [f'm{t.i}' for t in parts], 'roles': roles,
                       'polarity': polarity, 'scope': scope, 'quantities': quantities})
        if 'VERB' not in dictionary(v.text):
            unresolved.append({'reason': 'unparsed_content', 'detail': 'predicate outside dictionary',
                               'evidence': [ev(v)]})
    for t in doc:
        if t.lower_ in PERSON_PRONOUNS and t.pos_ == 'PRON':
            unresolved.append({'reason': 'unresolved_reference', 'detail': 'pronoun', 'evidence': [ev(t)]})
    _drop_dangling_parents(events)
    return Graph.model_validate({'version': '2.0', 'language': 'english', 'text': text, 'mentions': mentions,
                                 'events': events, 'unresolved': unresolved})


def _drop_dangling_parents(events):
    ids = {e['id'] for e in events}
    for e in events:
        if e['scope'].get('parent_event') not in ids:
            e['scope'].pop('parent_event', None)


def gloss_graph(text, nmm=None, notation=None):
    from ..natural import _strip, analyze_token, extract_natural_gloss
    ir = extract_natural_gloss(text, nmm=nmm, notation=notation)
    tokens = list(re.finditer(r'\S+', text))
    infos = [analyze_token(t.group(), tokens[i - 1].group() if i else '') for i, t in enumerate(tokens)]
    ev = lambda i: _span(text, tokens[i].start(), tokens[i].end())
    index_of = {t.start(): i for i, t in enumerate(tokens)}
    entity_at = {index_of[o['evidence'][0]['start']]: o['value'] for o in ir['observations']['entities']}
    action_at = {index_of[o['evidence'][0]['start']]: o['value'] for o in ir['observations']['actions']}
    mentions, events, unresolved = [], [], []
    for i, value in sorted(entity_at.items()):
        bare = _strip(tokens[i].group())
        name = value.startswith('NAME:')
        form = 'name' if name or bare.startswith('ns-') else 'fingerspelled' if bare.startswith('fs-') else 'lexical'
        label = value.removeprefix('NAME:').lower()
        mentions.append({'id': f'm{i}', 'label': label, 'kind': 'other' if name else 'thing', 'form': form,
                         'concepts': sorted(set(infos[i]['concepts']) - {label}), 'evidence': [ev(i)]})
    for i, t in enumerate(tokens):
        bare = _strip(t.group())
        if re.match(r'^(?:IX|POSS|SELF)-(?:3p|loc)|^IX:', bare):
            mentions.append({'id': f'm{i}', 'label': bare.lower(), 'kind': 'other', 'form': 'pointing',
                             'evidence': [ev(i)]})
        elif re.match(r'^[A-Z0-9]*CL[:"\-]', bare):
            mentions.append({'id': f'm{i}', 'label': bare.lower(), 'kind': 'other', 'form': 'classifier',
                             'evidence': [ev(i)]})
    actions = sorted(action_at)
    topic = bool((nmm or {}).get('topic')) and notation != 'aslg_pc12'
    negation_nmm = (nmm or {}).get('negation')
    conditional_from = min((i for i, t in enumerate(tokens) if _strip(t.group()).lstrip('(1h)') in GLOSS_CONDITIONAL),
                           default=None)
    lexical_mentions = [m for m in mentions if m['form'] in ('lexical', 'name', 'fingerspelled')]

    def nearest(i):
        return min(actions, key=lambda a: (abs(a - i), a)) if actions else None

    clause_roles = {}
    for c in ir['clauses']:
        a = index_of[c['action']['evidence'][0]['start']]
        clause_roles[a] = [('agent', index_of[c['agent']['evidence'][0]['start']]),
                           ('patient', index_of[c['patient']['evidence'][0]['start']])]
    attachments = {}
    for att in ir['number_attachments']:
        spans = att['evidence']
        noun = index_of[spans[-1]['start']]
        if noun in entity_at:
            attachments[noun] = (att['value'], index_of[spans[0]['start']])
    for n, i in enumerate(actions):
        directional = infos[i]['directional']
        participants = sorted(m for m in (int(x['id'][1:]) for x in lexical_mentions) if nearest(m) == i)
        roles = []
        if not directional and not topic:
            for role, j in clause_roles.get(i, []):
                if j not in participants:
                    participants.append(j)
                roles.append({'role': role, 'mention_id': f'm{j}', 'basis': 'word_order', 'evidence': [ev(j)]})
        before = i - 1 if i else None
        if infos[i]['negator'] == 'self' or (before is not None and infos[before]['negator'] == 'predicate'):
            neg = [ev(before)] if infos[i]['negator'] != 'self' else []
            polarity = {'value': 'negative', 'basis': 'lexical_negator', 'evidence': neg + [ev(i)]}
        elif negation_nmm is True and len(actions) == 1:
            polarity = {'value': 'negative', 'basis': 'nonmanual', 'evidence': [ev(i)]}
        elif negation_nmm is False and not ir['manual_negation']:
            polarity = {'value': 'positive', 'basis': 'nonmanual', 'evidence': [ev(i)]}
        else:
            polarity = {'value': 'unknown', 'basis': 'unknown', 'evidence': []}
        # IF marks the first following clause; the consequent clause stays asserted.
        if conditional_from is not None and i == next((a for a in actions if a > conditional_from), None):
            scope = {'kind': 'conditional', 'evidence': [ev(conditional_from)]}
        else:
            scope = {'kind': 'asserted', 'evidence': [ev(i)]}
        quantities = [{'mention_id': f'm{j}', 'kind': 'count', 'unit': 'item', 'value': str(attachments[j][0]),
                       'relation': 'eq', 'evidence': [ev(attachments[j][1])]}
                      for j in participants if j in attachments]
        label = action_at[i].lower()
        complete = bool(roles) and {r['mention_id'] for r in roles} == {f'm{j}' for j in participants}
        events.append({'id': f'e{n}', 'predicate': label, 'form': 'directional' if directional else 'lexical',
                       'roles_complete': complete,
                       'concepts': sorted(set(infos[i]['concepts']) - {label}), 'evidence': [ev(i)],
                       'participants': [f'm{j}' for j in participants], 'roles': roles, 'polarity': polarity,
                       'scope': scope, 'quantities': quantities})
    for key, reason in (('unrecognized', 'unparsed_content'), ('ambiguous_labels', 'lexical_ambiguity'),
                        ('unattached_numbers', 'unresolved_quantity'), ('unresolved_numerals', 'unresolved_quantity')):
        for span in ir.get(key) or []:
            unresolved.append({'reason': reason, 'detail': key, 'evidence': [span]})
    return Graph.model_validate({'version': '2.0', 'language': 'gloss', 'text': text, 'mentions': mentions,
                                 'events': events, 'unresolved': unresolved, 'nonmanual': _nonmanual(nmm)})
