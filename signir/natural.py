"""Independent natural-text readers; lexical evidence is not full ASL semantics.

spaCy sees English only. The gloss reader uses dictionary lookups and explicit
local patterns, never the English sentence or an English dependency parse.
"""
from functools import lru_cache
import hashlib
from importlib.metadata import distribution, version, PackageNotFoundError
import re

from .schema import record, fact, evidence, spans

MODEL = 'en_core_web_sm'
ENGLISH_ID = 'english-spacy-1'
GLOSS_ID = 'gloss-lexical-2'
# Resolve common noun/verb homographs only for these documented action labels.
# All unambiguous dictionary verbs are also recognized. This is not inferred
# from this run, and unfamiliar action labels remain observable diagnostics.
ACTION_LABELS = set('''BUY SELL HELP SEE VISIT LIKE SHOW GIVE TAKE MAKE GO COME
TALK SPEAK SIGN LEARN TEACH TRAIN ENABLE PERMIT ALLOW NEED WANT KNOW THINK SAY
TELL ASK ANSWER WORK LIVE DIE EAT DRINK SLEEP WALK RUN DRIVE READ WRITE WATCH
LOOK HEAR LISTEN PLAY OPEN CLOSE START STOP FINISH RECEIVE SEND BRING LEAVE
ARRIVE RETURN MOVE GROW DEVELOP IMPROVE INFLUENCE EXPERIENCE DISCUSS MEET
FIND LOSE KEEP PUT GET USE FEEL LOVE HATE BUILD BREAK CHANGE PAY WAIT UNDERSTAND
REMEMBER FORGET TRY CHOOSE DECIDE EXPLAIN FOLLOW SUPPORT STUDY CALL TURN
TRAVEL LEND BORROW COUNT COOK WASH CLEAN DANCE SING SIT STAND HAPPEN BECOME
CONTINUE BELIEVE AGREE DISAGREE REFUSE ACCEPT INCLUDE REQUIRE EXPECT HOPE
NOTICE RECOGNIZE DESCRIBE COMPARE PREVENT PROTECT HOLD TOUCH HIT PUSH PULL
RAISE LOWER OFFER REPLACE REMOVE CREATE DESTROY WIN FAIL SUCCEED'''.split())
NUMBER_WORDS = {w: n for n, w in enumerate(
    'zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty'.split())}
NUMBER_WORDS.update(dict(zip('thirty forty fifty sixty seventy eighty ninety'.split(), range(30, 100, 10))))
SCALES = {'hundred': 100, 'thousand': 1000, 'million': 1000000, 'billion': 1000000000}
NUMBER_PREFIX_LABELS = {'AGE', 'CHAPTER', 'PART', 'PAGE', 'SECTION', 'VOLUME'}
SKIP = set('''THE A AN AND OR BUT IF THEN BECAUSE TO OF IN ON AT FROM FOR WITH
ABOUT BY AS SO NOT NEVER NO NONE CAN COULD MAY MIGHT MUST SHOULD WOULD WILL
DO DOES DID BE IS ARE WAS WERE HAVE HAS HAD POS NEG PLURAL QUOTE/TOPIC
THIS THAT THESE THOSE THEIR YOUR MY OUR HIS HER ITS ALL ANY EVERY SOME
MANY MORE MOST OTHER ANOTHER FIRST LAST SUCH EACH EVERYTHING EVERYONE
SOMETHING ANYTHING NOTHING SOMEONE ANYONE NOBODY YOU I ME HE SHE IT WE THEY
EVEN STILL REALLY ALSO ONLY ONCE YET VERY TOO WHO WHOM WHAT WHEN WHERE
WHY HOW WHETHER WHICH'''.split())


def extraction_configuration():
    """Fingerprint external extraction resources as well as our source rules."""
    packages = {}
    resources = {}
    for package in ('spacy', 'lemminflect', MODEL):
        try:
            packages[package] = version(package)
            dist = distribution(package)
            for item in dist.files or ():
                name = str(item).replace('\\', '/')
                if (package == MODEL and (name.endswith('/model') or name.endswith('/lookups.bin')
                        or name.endswith('/patterns') or name.endswith('/config.cfg') or name.endswith('/meta.json'))
                        or package == 'lemminflect' and '/resources/' in name):
                    path = dist.locate_file(item)
                    resources[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        except PackageNotFoundError:
            packages[package] = None
    return {'english_fixture': 'english-rules-1', 'gloss_fixture': 'gloss-rules-1',
            'english_natural': ENGLISH_ID, 'gloss_natural': GLOSS_ID,
            'packages': packages, 'resource_sha256': resources,
            'gloss_parser': 'independent dictionary/local patterns; no English parser on gloss'}


@lru_cache(maxsize=1)
def english_pipeline():
    try:
        import spacy
        return spacy.load(MODEL, exclude=['ner'])
    except (ImportError, OSError) as exc:
        raise ValueError('Natural English extraction requires spaCy and en_core_web_sm. '
                         'Install the natural extra and run python -m spacy download en_core_web_sm; '
                         'missing tools are configuration errors, not UNKNOWN facts.') from exc


@lru_cache(maxsize=8192)
def dictionary(word):
    try:
        from lemminflect import getAllLemmas
    except ImportError as exc:
        raise ValueError('Natural gloss extraction requires lemminflect; install signir-check[natural].') from exc
    return getAllLemmas(word.lower())


def numeric(word):
    if re.fullmatch(r'[0-9]{1,18}', word):
        return int(word)
    return NUMBER_WORDS.get(word.lower())


def numeric_phrase(words):
    words = ' '.join(words).lower().replace('-', ' ').split()
    if len(words) == 1:
        return numeric(words[0])
    total, chunk, previous = 0, 0, None
    for word in words:
        if word == 'and':
            continue
        n = numeric(word)
        if n is not None:
            if previous is not None and previous < 20:
                return None  # reject separate adjacent numbers such as "two three"
            chunk += n
            previous = n
        elif word in SCALES:
            if not chunk:
                return None
            chunk *= SCALES[word]
            if SCALES[word] >= 1000:
                total += chunk
                chunk = 0
            previous = None
        else:
            return None
    return total + chunk


def observed(value, ev, reason, scope):
    f = fact(value, ev, reason)
    f['scope'] = scope
    return f


def english_label(token):
    entries = dictionary(token.text)
    if token.pos_ == 'PROPN' and not entries:
        return 'NAME:' + token.text.upper()
    if token.pos_ in ('NOUN', 'PROPN') and 'NOUN' in entries:
        return entries['NOUN'][0].upper()
    if token.pos_ == 'VERB' and 'VERB' in entries and len(entries['VERB']) == 1:
        return entries['VERB'][0].upper()
    return token.lemma_.upper()


def extract_natural_english(text):
    ir = record(text, 'english', ENGLISH_ID)
    doc = english_pipeline()(text)
    ir['model'] = {'name': MODEL, 'version': english_pipeline().meta['version']}
    ir['warnings'] = ['English dependency analysis is a model prediction. No coreference resolution.']
    nouns = [t for t in doc if t.pos_ in ('NOUN', 'PROPN')
             and not (t.dep_ == 'amod' and 'ADJ' in dictionary(t.text))]
    verbs = [t for t in doc if t.pos_ == 'VERB' and t.lemma_ != 'be']
    unsupported_verbs = [t for t in verbs if 'VERB' not in dictionary(t.text)]
    ir['unrecognized_predicates'] = [evidence(text, t.idx, t.idx+len(t)) for t in unsupported_verbs]
    ev = lambda t: evidence(text, t.idx, t.idx + len(t))
    ir['observations'] = {
        'entities': [{'value': english_label(t), 'evidence': [ev(t)]} for t in nouns],
        'actions': [{'value': english_label(t), 'evidence': [ev(t)]} for t in verbs]}
    if nouns:
        ir['facts']['entities'] = observed([english_label(t) for t in nouns], [ev(t) for t in nouns],
            'Observed noun/proper-noun mentions; not a complete participant interpretation', 'lexical mentions')
    if len(verbs) == 1 and not unsupported_verbs:
        ir['facts']['action'] = observed(english_label(verbs[0]), [ev(verbs[0])],
            'One lexical verb found by the English dependency parser', 'single lexical predicate')
    else:
        ir['facts']['action']['reason'] = f'{len(verbs)} lexical predicates, {len(unsupported_verbs)} outside dictionary; single-event comparison unavailable'
    negated = []
    for t in verbs:
        markers = [c for c in t.children if c.dep_ == 'neg']
        # Some parses attach negation to an auxiliary rather than the predicate.
        markers += [c for aux in t.children if aux.dep_ in ('aux', 'auxpass')
                    for c in aux.children if c.dep_ == 'neg']
        if markers and t not in unsupported_verbs:
            negated.append((t, markers))
    if len(negated) == 1:
        t, markers = negated[0]
        ir['facts']['negation'] = observed({'action': english_label(t), 'negative': True},
            [ev(t)] + [ev(c) for c in markers], 'One explicit negated predicate, scoped by dependency',
            'one explicitly scoped predicate')
    elif len(verbs) == 1 and not negated and not unsupported_verbs:
        ir['facts']['negation'] = observed({'action': english_label(verbs[0]), 'negative': False},
            [ev(verbs[0])], 'No syntactic negation on the sole English predicate', 'one explicitly scoped predicate')
    else:
        ir['facts']['negation']['reason'] = 'No unique explicit negated predicate or single positive predicate'
    counts, count_ev = [], []
    for t in doc:
        if t.dep_ == 'nummod' and t.head.pos_ in ('NOUN', 'PROPN'):
            components = [c for c in t.subtree if c.pos_ == 'NUM']
            if not components or any(c.pos_ == 'NUM' for c in t.head.children if c != t):
                continue
            start, end = min(c.i for c in components), max(c.i for c in components)
            n = numeric_phrase([c.text for c in doc[start:end+1]])
            if n is None:
                continue
            symbols = [c for c in t.children if c.text in {'$': 'DOLLAR', '£': 'POUND', '€': 'EURO'}]
            if symbols:
                unit = {'$': 'DOLLAR', '£': 'POUND', '€': 'EURO'}[symbols[0].text]
                unit_ev = ev(symbols[0])
            else:
                unit, unit_ev = english_label(t.head), ev(t.head)
            counts.append({'entity': unit, 'count': n})
            count_ev += [evidence(text, doc[start].idx, doc[end].idx+len(doc[end])), unit_ev]
    if counts:
        ir['facts']['numbers'] = observed(counts, count_ev,
            'Explicit dependency-linked numeral/unit; integer compounds and currency symbols supported, ordinals excluded',
            'explicit number attachments')
    if len(verbs) == 1 and not unsupported_verbs:
        v = verbs[0]
        subjects = [t for t in v.children if t.dep_ == 'nsubj' and t.pos_ in ('NOUN', 'PROPN')]
        objects = [t for t in v.children if t.dep_ == 'dobj' and t.pos_ in ('NOUN', 'PROPN')]
        if len(subjects) == len(objects) == 1 and not any(t.dep_ in ('nsubjpass', 'auxpass') for t in v.children):
            ir['facts']['roles'] = observed({'action': english_label(v), 'agent': english_label(subjects[0]),
                'patient': english_label(objects[0])}, [ev(v), ev(subjects[0]), ev(objects[0])],
                'One active English predicate with explicit noun subject/object', 'explicit active roles')
    return ir


def decode(token):
    """Retain original evidence while decoding only documented lexical wrappers."""
    token = token.rstrip('.,?!')
    token = re.sub(r'^\([12]h\)', '', token)
    token = re.sub(r'^alt\.', '', token)
    token = token.lstrip('#')
    if token.startswith('fs-'):
        spelling = token[3:]
        parts = spelling.split('-')
        word = ''.join(parts) if all(len(p) == 1 for p in parts) else spelling
        entries = dictionary(word)
        if 'ADJ' in entries or 'ADV' in entries:
            return ('modifier', None)
        if 'NOUN' in entries:
            return ('entity', entries['NOUN'][0].upper())
        if 'VERB' in entries:
            return ('action', entries['VERB'][0].upper())
        # Unknown spelled items are candidate names, not confirmed NER.
        return ('entity', 'NAME:' + word.upper())
    if token in SKIP or token.startswith(('IX-', 'IX:', 'CL:', 'POSS-', 'SELF-')):
        return ('structural', None)
    if numeric(token) is not None:
        return ('number', numeric(token))
    if not re.fullmatch(r'[A-Z]+(?:-[A-Z]+)*', token):
        return ('unsupported', None)
    entries = dictionary(token)
    if 'VERB' in entries:
        lemma = entries['VERB'][0].upper()
        if any(p in entries for p in ('NOUN', 'ADJ', 'ADV')):
            return ('ambiguous', {'action': lemma,
                                 'entity': entries.get('NOUN', (None,))[0]})
        if lemma in ACTION_LABELS or 'NOUN' not in entries:
            return ('action', lemma)
    if 'ADJ' in entries or 'ADV' in entries:
        return ('modifier', None)
    if 'NOUN' in entries:
        return ('entity', entries['NOUN'][0].upper())
    if any(k in entries for k in ('ADJ', 'ADV', 'ADP', 'DET', 'PRON', 'CCONJ', 'SCONJ', 'INTJ')):
        return ('modifier', None)
    return ('unsupported', None)


def extract_natural_gloss(text):
    ir = record(text, 'gloss', GLOSS_ID)
    tokens, ev = ir['tokens'], spans(text)
    decoded = [decode(t) if not t.startswith(('NEG:', 'POS:', 'AGENT:', 'PATIENT:'))
               else ('annotation', None) for t in tokens]
    # Explicit NEG:/POS: or adjacent NOT supports a lexical predicate reading.
    # A numeral plus bounded modifiers supports a noun reading. Unresolved
    # noun/verb homographs veto a sole-action assertion rather than cause flags.
    for i, token in enumerate(tokens):
        entries = dictionary(token.rstrip('.,?!'))
        previous = tokens[i-1] if i > 0 else ''
        scope = previous.split(':', 1)[1] if previous.startswith(('NEG:', 'POS:')) else None
        if 'VERB' in entries and (entries['VERB'][0].upper() == scope or previous in ('NOT', 'NEVER')):
            decoded[i] = ('action', entries['VERB'][0].upper())
    for i, (kind, value) in enumerate(decoded):
        if kind != 'ambiguous':
            continue
        previous = tokens[i-1] if i > 0 else ''
        if previous in ('NOT', 'NEVER') or previous in ('NEG:'+value['action'], 'POS:'+value['action']):
            decoded[i] = ('action', value['action'])
        elif value['entity'] and any(decoded[j][0] == 'number' and
                all(decoded[k][0] == 'modifier' for k in range(j+1, i))
                for j in range(max(0, i-3), i)):
            decoded[i] = ('entity', value['entity'].upper())
    actions = [(value, i) for i, (kind, value) in enumerate(decoded) if kind == 'action']
    entities = [(value, i) for i, (kind, value) in enumerate(decoded) if kind == 'entity']
    unsupported = [ev[i] for i, (kind, _) in enumerate(decoded) if kind == 'unsupported']
    ambiguous = [ev[i] for i, (kind, _) in enumerate(decoded) if kind == 'ambiguous']
    ir['unrecognized'] = unsupported
    ir['ambiguous_labels'] = ambiguous
    ir['warnings'] = ['Gloss dictionary categories are lexical hypotheses, not an ASL parse.',
                      'No roles inferred from order; no positive polarity inferred from absent NOT.',
                      'Fingerspelled dictionary nouns are treated as nouns; other spellings are candidate names.']
    ir['observations'] = {
        'entities': [{'value': v, 'evidence': [ev[i]]} for v, i in entities],
        'actions': [{'value': v, 'evidence': [ev[i]]} for v, i in actions]}
    if entities:
        ir['facts']['entities'] = observed([v for v, _ in entities], [ev[i] for _, i in entities],
            'Observed dictionary noun/spelling mentions only; unexplained labels retained separately', 'lexical mentions')
    if len(actions) == 1 and not unsupported and not ambiguous:
        v, i = actions[0]
        ir['facts']['action'] = observed(v, [ev[i]], 'One recognized lexical predicate; no unexplained labels',
            'single lexical predicate')
    else:
        ir['facts']['action']['reason'] = f'{len(actions)} recognized predicates, {len(unsupported)} unexplained labels, {len(ambiguous)} ambiguous labels; cannot establish sole event'
    polarity = []
    for i, token in enumerate(tokens):
        if token.startswith(('NEG:', 'POS:')):
            sign, scope = token.split(':', 1)
            candidates = [j for v, j in actions if v == scope]
            if i+1 in candidates:
                polarity.append((scope, sign == 'NEG', i, i+1))
            elif len(candidates) == 1:
                polarity.append((scope, sign == 'NEG', i, candidates[0]))
        elif token in ('NOT', 'NEVER'):
            # A following predicate is local explicit scope, even in a multi-event
            # fragment. Postposed NOT is accepted only for one sole predicate.
            if i+1 < len(decoded) and decoded[i+1][0] == 'action':
                polarity.append((decoded[i+1][1], True, i, i+1))
            elif len(actions) == 1 and i == actions[0][1]+1:
                polarity.append((actions[0][0], True, i, actions[0][1]))
    if len(polarity) == 1:
        v, negative, i, target = polarity[0]
        ir['facts']['negation'] = observed({'action': v, 'negative': negative}, [ev[i], ev[target]],
            'One explicit polarity marker attached to one identified predicate occurrence', 'one explicitly scoped predicate')
    else:
        ir['facts']['negation']['reason'] = 'No unique explicitly scoped polarity marker'
    counts, count_ev, unresolved = [], [], []
    for i, (kind, value) in enumerate(decoded):
        if kind != 'number':
            continue
        if i > 0 and tokens[i-1] in NUMBER_PREFIX_LABELS:
            counts.append({'entity': tokens[i-1], 'count': value})
            count_ev += [ev[i], ev[i-1]]
            continue
        j = i+1
        # Allow ordinary adjectives between a count and its noun, never another
        # noun, event, locus, unknown label or numeral. Bounded local attachment.
        while j < len(decoded) and j <= i+3 and decoded[j][0] == 'modifier':
            j += 1
        if j < len(decoded) and decoded[j][0] == 'entity' and j <= i+3:
            counts.append({'entity': decoded[j][1], 'count': value})
            count_ev += [ev[i], ev[j]]
        else:
            unresolved.append(ev[i])
    ir['unattached_numbers'] = unresolved
    if counts and not unresolved:
        ir['facts']['numbers'] = observed(counts, count_ev,
            'Local numeral/noun attachment, bounded modifiers or documented AGE/CHAPTER/PART/PAGE/SECTION/VOLUME prefix', 'explicit number attachments')
    elif unresolved:
        ir['facts']['numbers']['reason'] = 'At least one numeral has no supported local noun attachment'
    ir['facts']['roles']['reason'] = 'Natural gloss order alone cannot establish semantic roles'
    return ir
