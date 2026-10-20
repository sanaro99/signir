"""Deterministic comparison, independent of how SignIR records were obtained.

Statuses: MATCH, MISMATCH (conflicting evidence), MISSING (the English states the
fact and the translation, including its non-manual markers when supplied, shows
no trace of it) and UNKNOWN (not enough evidence either way).
"""
import json
from .schema import CHECKS, validate
from .english import extract_english
from .gloss import extract_gloss, is_annotated

STATUSES = ('MATCH', 'MISMATCH', 'MISSING', 'UNKNOWN')


def canonical(value):
    if isinstance(value, list):
        return sorted(json.dumps(x, sort_keys=True) for x in value)
    return value


def _result(status, reason, scope, a, b, english_evidence=None, gloss_evidence=None, **extra):
    return {'status': status, 'reason': reason, 'scope': scope,
            'english_value': a['value'], 'gloss_value': b['value'],
            'english_evidence': a['evidence'] if english_evidence is None else english_evidence,
            'gloss_evidence': b['evidence'] if gloss_evidence is None else gloss_evidence, **extra}


def _legacy(english, gloss):
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
        result[name] = _result(status, reason, a.get('scope') or b.get('scope') or 'supported fixture facts', a, b)
        if (a.get('scope') or b.get('scope')) and status != 'UNKNOWN':
            result[name]['reason'] += '; assessed scope: ' + result[name]['scope']
    return result


def _nmm_evidence(gloss):
    nmm = gloss.get('nmm') or {}
    return [{'channel': 'nmm', 'label': 'negation', 'value': nmm['negation']}] if 'negation' in nmm else []


def _negation_from_channels(english, gloss, current):
    """Sentence-level negation using manual signs and supplied NMM labels."""
    a, b = english['facts']['negation'], gloss['facts']['negation']
    content = english.get('content') or {}
    english_negative = content.get('negative_sentence') if content else (
        a['value']['negative'] if a['state'] == 'KNOWN' else None)
    if current['status'] in ('MATCH', 'MISMATCH') or english_negative is None:
        return current
    nmm = (gloss.get('nmm') or {}).get('negation')
    manual = gloss.get('manual_negation')
    if manual is None:  # fixture gloss: explicit polarity annotations only
        manual = [{'strength': 'predicate'}] if b['state'] == 'KNOWN' and b['value']['negative'] else []
    strong = [m for m in manual if m['strength'] in ('predicate', 'self')]
    english_ev = content.get('negation_evidence') or a['evidence']
    gloss_ev = [e for m in manual for e in m.get('evidence', [])] + _nmm_evidence(gloss)
    manual_only = gloss.get('notation') == 'aslg_pc12'
    scope = 'sentence-level negation (manual signs and non-manual markers)'
    if english_negative:
        if manual or nmm:
            how = ' and '.join(x for x, y in (('manual negation sign', manual), ('non-manual negation', nmm)) if y)
            return _result('MATCH', f'English negation expressed by {how}', scope, a, b, english_ev, gloss_ev)
        if nmm is False or manual_only:
            return _result('MISSING', 'English negation is not expressed by a negation sign'
                           + (' or the non-manual markers' if nmm is False else ''), scope, a, b, english_ev, gloss_ev,
                           missing=['negation'])
        return _result('UNKNOWN', 'No manual negation sign; negation may be non-manual and no NMM labels were supplied',
                       scope, a, b, english_ev, gloss_ev)
    if strong:
        return _result('MISMATCH', 'Positive English sentence but the translation has a negation sign', scope, a, b,
                       english_ev, gloss_ev)
    if nmm:
        if content.get('negative_meaning'):
            return _result('UNKNOWN', 'Head-shake without a negation sign; it may accompany a negative-meaning word',
                           scope, a, b, english_ev, gloss_ev)
        return _result('MISMATCH', 'Positive English sentence but the non-manual markers show negation', scope, a, b,
                       english_ev, gloss_ev)
    if nmm is False or manual_only:
        return _result('MATCH', 'Neither side expresses negation', scope, a, b, english_ev, gloss_ev)
    return current


def _expressed(candidates, gloss):
    words = set(candidates)
    return [s for s in gloss['signs'] if words & set(s['concepts'])]


def _entities(english, gloss):
    a, b = english['facts']['entities'], gloss['facts']['entities']
    items = english['content']['entities']
    scope = 'English nouns and names expressed by some gloss sign (dictionary or lexicon match)'
    if not items:
        return _result('UNKNOWN', 'No English noun or name to check', scope, a, b)
    missing, gloss_ev, used, unflagged = [], [], set(), []
    for item in items:
        found = _expressed(item['candidates'], gloss)
        if found:
            gloss_ev += found[0]['evidence']
            used.update(s['index'] for s in found)
        elif item.get('core', True):
            missing.append(item)
        else:
            unflagged.append(item['label'])
    # An English name may be a personal or abbreviated name sign (ns-#SD for San Diego) we cannot
    # resolve; a fully fingerspelled different name (fs-ZOE for Bob) is still flagged.
    spare_names = [s for s in gloss['signs'] if s.get('name_sign') and s['index'] not in used]
    if spare_names:
        missing = [m for m in missing if not m['name']]
    # A previously introduced referent can be shown by pointing to its locus or by a classifier.
    referable = gloss.get('pointing') or gloss.get('classifier')
    unresolved = [m['label'] for m in missing if m.get('given') and referable]
    missing = [m['label'] for m in missing if not (m.get('given') and referable)]
    eng_ev = [e for item in items for e in item['evidence']]
    if not missing and unresolved:
        return _result('UNKNOWN', 'Not signed by name, but may be referred to by pointing or a classifier: '
                       + ', '.join(unresolved), scope, a, b, eng_ev, gloss_ev)
    if not missing and unflagged and not gloss_ev:
        return _result('UNKNOWN', 'Only generic or peripheral nouns, which translations often absorb', scope, a, b)
    if missing:
        return _result('MISSING', 'Not expressed in the gloss: ' + ', '.join(missing), scope, a, b, eng_ev, gloss_ev,
                       missing=missing)
    return _result('MATCH', 'Every English noun/name has a corresponding gloss sign', scope, a, b, eng_ev, gloss_ev)


def _action(english, gloss):
    a, b = english['facts']['action'], gloss['facts']['action']
    scope = 'English lexical predicates expressed by some gloss sign'
    predicates = [p for p in english['content']['predicates'] if p['dictionary']]
    if not predicates:
        return _result('UNKNOWN', 'No dictionary English predicate to check', scope, a, b)
    missing, gloss_ev, unexpressed_light = [], [], []
    for p in predicates:
        found = _expressed(p['candidates'], gloss)
        if found:
            gloss_ev += found[0]['evidence']
        elif p['light'] or not p.get('main', True):
            unexpressed_light.append(p['label'])
        else:
            missing.append(p['label'])
    eng_ev = [e for p in predicates for e in p['evidence']]
    if missing and gloss.get('classifier'):
        return _result('UNKNOWN', 'Not signed lexically, but the gloss has classifier predicates that may express: '
                       + ', '.join(missing), scope, a, b, eng_ev, gloss_ev)
    if missing:
        sole = b['state'] == 'KNOWN' and len(predicates) == 1
        if sole:
            return _result('MISMATCH', f"English predicate {missing[0]} differs from the gloss's sole predicate {b['value']}",
                           scope, a, b, eng_ev, gloss_ev + b['evidence'])
        return _result('MISSING', 'Not expressed in the gloss: ' + ', '.join(missing), scope, a, b, eng_ev, gloss_ev,
                       missing=missing)
    if unexpressed_light and not gloss_ev:
        return _result('UNKNOWN', 'Only light verbs, which ASL often expresses structurally', scope, a, b)
    return _result('MATCH', 'English predicates have corresponding gloss signs', scope, a, b, eng_ev, gloss_ev)


def _numbers(english, gloss):
    a, b = english['facts']['numbers'], gloss['facts']['numbers']
    scope = 'English counts and their nouns/units, including numerals merged into signs'
    if a['state'] != 'KNOWN':
        return _result('UNKNOWN', 'No explicit English number', scope, a, b)
    entities = {x['label']: x['candidates'] for x in english['content']['entities']}
    special = {'DOLLAR': ['dollar'], 'POUND': ['pound'], 'EURO': ['euro'], 'AGE': ['age', 'old', 'year']}
    present = {n['value'] for n in gloss['numerals']}
    outcomes = []
    for item in a['value']:
        candidates = set(special.get(item['entity']) or entities.get(item['entity'], [item['entity'].lower()]))
        candidates.add(item['entity'].lower())
        same = [x for x in gloss['number_attachments'] if candidates & set(x['concepts'])]
        if same:
            outcomes.append('match' if any(x['value'] == item['count'] for x in same) else 'mismatch')
        elif item['count'] in present:
            outcomes.append('unknown')  # the value is there but its noun could not be aligned
        elif gloss['unresolved_numerals']:
            outcomes.append('unknown')
        elif item['count'] == 1:
            outcomes.append('unknown')  # English "one" often works like the article "a"
        else:
            outcomes.append('missing')
    g_ev = [e for x in gloss['number_attachments'] for e in x['evidence']] + [e for n in gloss['numerals'] for e in n['evidence']]
    if 'mismatch' in outcomes:
        return _result('MISMATCH', 'A count attached to the same noun/unit differs', scope, a, b, None, g_ev)
    if 'missing' in outcomes:
        missing = [f"{x['count']} {x['entity']}" for x, o in zip(a['value'], outcomes) if o == 'missing']
        return _result('MISSING', 'Number not expressed in the gloss: ' + ', '.join(missing), scope, a, b, None, g_ev,
                       missing=missing)
    if all(o == 'match' for o in outcomes):
        return _result('MATCH', 'Equal counts attached to the same nouns/units', scope, a, b, None, g_ev)
    return _result('UNKNOWN', 'Numbers present but their attachment could not be aligned', scope, a, b, None, g_ev)


def _roles(english, gloss):
    a, b = english['facts']['roles'], gloss['facts']['roles']
    scope = 'subject/object of an active English clause vs plain-verb gloss word order'
    roles = english['content'].get('roles')
    if not roles:
        return _result('UNKNOWN', 'No single active English clause with noun subject and object', scope, a, b)
    clauses = [c for c in gloss['clauses'] if set(roles['action']) & set(c['action']['concepts'])]
    if len(clauses) != 1:
        reason = gloss.get('roles_gate') or ('No plain-verb gloss clause for this predicate' if not clauses
                                             else 'Several gloss clauses for this predicate')
        return _result('UNKNOWN', reason, scope, a, b)
    c = clauses[0]
    has = lambda side, who: bool(set(roles[who]) & set(c[side]['concepts']))
    ev = c['action']['evidence'] + c['agent']['evidence'] + c['patient']['evidence']
    if has('agent', 'agent') and has('patient', 'patient'):
        return _result('MATCH', 'Same doer and receiver in gloss word order', scope, a, b, None, ev)
    if has('agent', 'patient') and has('patient', 'agent'):
        return _result('MISMATCH', 'Doer and receiver are reversed in gloss word order', scope, a, b, None, ev)
    return _result('UNKNOWN', 'Gloss clause participants do not both correspond to the English ones', scope, a, b, None, ev)


def compare(english, gloss, missing=True):
    """missing=False keeps the original three-status comparison (used by frozen experiments)."""
    validate(english)
    validate(gloss)
    if not missing:
        return _legacy(english, gloss)
    if english.get('content') is not None and gloss.get('signs') is not None:
        result = {'entities': _entities(english, gloss), 'action': _action(english, gloss),
                  'numbers': _numbers(english, gloss), 'roles': _roles(english, gloss)}
        legacy = _legacy(english, gloss)
        result['negation'] = _negation_from_channels(english, gloss, legacy['negation'])
        return {name: result[name] for name in CHECKS}
    result = _legacy(english, gloss)
    result['negation'] = _negation_from_channels(english, gloss, result['negation'])
    return result


def check_pair(english, gloss, gloss_nmm=None, notation=None):
    """Annotated fixtures use the fixture readers; other glosses use the natural readers."""
    if is_annotated(gloss):
        a = extract_english(english)
        b = extract_gloss(gloss, nmm=gloss_nmm, notation=notation)
    else:
        from .english import extract_english_for_check
        from .natural import extract_natural_gloss
        a = extract_english_for_check(english)
        b = extract_natural_gloss(gloss, nmm=gloss_nmm, notation=notation)
    return {'english': a, 'gloss': b, 'checks': compare(a, b)}
