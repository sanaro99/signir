"""Independent natural-text readers; lexical evidence is not full ASL semantics.

spaCy sees English only. The gloss reader uses dictionary lookups, an optional
gloss lexicon and explicit local patterns, never the English sentence or an
English dependency parse. A gloss may come with its non-manual marker (NMM)
labels, which belong to the translation, not to the English source.
"""
from functools import lru_cache
import hashlib
from importlib.metadata import distribution, version, PackageNotFoundError
import re

from . import lexicon
from .schema import record, fact, evidence, spans

MODEL = 'en_core_web_sm'
ENGLISH_ID = 'english-spacy-2'
GLOSS_ID = 'gloss-lexical-3'
# Documented action labels: a noun/verb homograph in this list reads as an action.
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
RAISE LOWER OFFER REPLACE REMOVE CREATE DESTROY WIN FAIL SUCCEED CHASE BITE
KISS CRY LAUGH SWIM FLY JUMP CATCH THROW KICK SMELL TASTE CARRY'''.split())
NUMBER_WORDS = {w: n for n, w in enumerate(
    'zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty'.split())}
NUMBER_WORDS.update(dict(zip('thirty forty fifty sixty seventy eighty ninety'.split(), range(30, 100, 10))))
SCALES = {'hundred': 100, 'thousand': 1000, 'million': 1000000, 'billion': 1000000000}
NUMBER_PREFIX_LABELS = {'AGE', 'CHAPTER', 'PART', 'PAGE', 'SECTION', 'VOLUME'}
# Units that a numeral can be merged into, e.g. ONE-WEEK, TWO-YEAR, THREE-OF-US.
INCORPORATED_UNITS = {'WEEK', 'MONTH', 'YEAR', 'DAY', 'HOUR', 'MINUTE', 'SECOND', 'DOLLAR',
                      'CENT', 'TIME', 'TIMES', 'OF-US', 'OF-THEM', 'OF-YOU', 'YEAR-OLD', 'OCLOCK'}
SKIP = set('''THE A AN AND OR BUT IF THEN BECAUSE TO OF IN ON AT FROM FOR WITH
ABOUT BY AS SO NOT NEVER NO NONE CAN COULD MAY MIGHT MUST SHOULD WOULD WILL
DO DOES DID BE IS ARE WAS WERE HAVE HAS HAD POS NEG PLURAL QUOTE/TOPIC
THIS THAT THESE THOSE THEIR YOUR MY OUR HIS HER ITS ALL ANY EVERY SOME
MANY MORE MOST OTHER ANOTHER FIRST LAST SUCH EACH EVERYTHING EVERYONE
SOMETHING ANYTHING NOTHING SOMEONE ANYONE NOBODY YOU I ME HE SHE IT WE THEY
EVEN STILL REALLY ALSO ONLY ONCE YET VERY TOO WHO WHOM WHAT WHEN WHERE
WHY HOW WHETHER WHICH'''.split())
# Manual negation. Predicate negators scope a neighbouring predicate; quantifier
# negators (NONE/NOTHING) negate the clause. Weak forms count as expressing an
# English negation but are never used to claim that a positive sentence was negated.
PREDICATE_NEGATORS = {'NOT', 'NEVER', 'CANNOT', "CAN'T", "DON'T", "WON'T", "DOESN'T", 'NOT-YET'}
QUANTIFIER_NEGATORS = {'NONE/NOTHING', 'NONE', 'NOTHING', 'NOBODY', 'NO-ONE'}
WEAK_NEGATORS = {'REFUSE', 'NO', 'DENY', 'WITHOUT', 'NOT-CARE', 'NOT-MATTER'}
# Words with negative meaning that a head-shake often accompanies in positive sentences.
NEGATIVE_MEANING = {'no', 'nope', 'refuse', 'deny', 'doubt', 'hate', 'without', 'yuck', 'fail',
                    'lack', 'reject', 'lie', 'blame', 'stop', 'avoid', 'lousy', 'wrong', 'bad'}
NEG_SUFFIX = re.compile(r'\+(?:\([^)]*\))?NEG$')
STRUCTURAL = re.compile(r'^(?:IX|POSS|SELF|PRO)(?:[-:]|$)|^X-|^part:|^[A-Z]*CL[:-]|BUOY$|^(?:HOLD|QMWG|QMwg)$')
ENGLISH_NEGATION_WORDS = {'not', "n't", 'never', 'no', 'nobody', 'nothing', 'none', 'nowhere',
                          'neither', 'nor', 'cannot', 'nt', 'without'}
# Verbs whose content is often carried by structure rather than a sign of their own.
LIGHT_VERBS = {'be', 'have', 'get', 'do', 'make', 'take', 'let', 'seem', 'become', 'happen',
               'tend', 'keep', 'put', 'mean', 'go', 'come', 'turn', 'say', 'try', 'start', 'begin', 'use'}
# Directional (agreement) verbs show who-did-what-to-whom by movement between loci.
DIRECTIONAL_VERBS = {'GIVE', 'HELP', 'ASK', 'TELL', 'SHOW', 'PAY', 'INFORM', 'SEND', 'BRING',
                     'TEACH', 'LOOK-AT', 'CALL', 'ANSWER', 'BLAME', 'TEASE', 'HATE', 'FORCE',
                     'INVITE', 'WARN', 'ADVISE', 'BORROW', 'LEND', 'OFFER', 'TAKE', 'BITE'}
NOTATIONS = (None, 'asllrp', 'aslg_pc12')
# Nouns that are often absorbed by structure or paraphrase; their absence is not flagged.
GENERIC_NOUNS = {'thing', 'way', 'lot', 'time', 'kind', 'sort', 'part', 'bit', 'stuff', 'example',
                 'sense', 'fact', 'case', 'point', 'end', 'number', 'one', 'matter', 'side', 'type'}
# Dependency relations of the participants and main predicates whose absence is flagged.
CORE_NOUN_DEPS = {'nsubj', 'nsubjpass', 'dobj', 'iobj', 'attr', 'dative', 'oprd', 'ROOT', 'appos', 'conj', 'poss'}
MAIN_PREDICATE_DEPS = {'ROOT', 'conj', 'xcomp'}


def clear_caches():
    analyze_token.cache_clear()


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
            'packages': packages, 'resource_sha256': resources, 'gloss_lexicons': lexicon.fingerprint(),
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


def lemmas(word):
    """Lowercase word plus every dictionary lemma for it."""
    word = word.lower()
    out = {word}
    for forms in dictionary(word).values():
        out.update(f.lower() for f in forms)
    return out


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


# --- English ---------------------------------------------------------------------

def english_label(token):
    entries = dictionary(token.text)
    if token.pos_ == 'PROPN' and not entries:
        return 'NAME:' + token.text.upper()
    if token.pos_ in ('NOUN', 'PROPN') and 'NOUN' in entries:
        return entries['NOUN'][0].upper()
    if token.pos_ == 'VERB' and 'VERB' in entries and len(entries['VERB']) == 1:
        return entries['VERB'][0].upper()
    return token.lemma_.upper()


def english_candidates(token):
    """Words a gloss sign could use to express this English token."""
    if token.pos_ == 'PROPN' and not dictionary(token.text):
        return sorted({token.text.lower()})
    out = lemmas(token.text) | {token.lemma_.lower()}
    for child in token.children:
        if child.dep_ == 'prt':
            out.add(token.lemma_.lower() + '-' + child.text.lower())
    return sorted(out)


def _negates(t):
    """Negation words, excluding the answer particle "No," and the idiom "no matter"."""
    if not (t.dep_ == 'neg' or t.lower_ in ENGLISH_NEGATION_WORDS):
        return False
    if t.lower_ == 'no':
        following = t.nbor(1) if t.i + 1 < len(t.doc) else None
        if t.dep_ == 'intj' or following is None or following.is_punct or following.lower_ == 'matter':
            return False
    return True


DEFINITE = {'the', 'this', 'that', 'these', 'those'}


def _is_core(t):
    if t.lemma_.lower() in GENERIC_NOUNS:
        return False
    if t.dep_ in CORE_NOUN_DEPS or t.pos_ == 'PROPN' or any(c.dep_ == 'nummod' for c in t.children):
        return True
    # Objects of prepositions attached to a predicate, e.g. "works at a hospital".
    return t.dep_ == 'pobj' and t.head.dep_ in ('prep', 'agent') and t.head.head.pos_ in ('VERB', 'AUX')


def _entity_item(t, ev):
    item = {'label': english_label(t), 'candidates': english_candidates(t), 'dep': t.dep_,
            'name': t.pos_ == 'PROPN', 'core': _is_core(t), 'evidence': [ev(t)],
            # A definite or named referent may have been introduced earlier and be pointed to.
            'given': t.pos_ == 'PROPN' or any(c.dep_ == 'det' and c.lower_ in DEFINITE for c in t.children)}
    if t.pos_ == 'PROPN':
        parts = [c for c in t.children if c.dep_ == 'compound' and c.pos_ == 'PROPN' and c.i < t.i] + [t]
        if len(parts) > 1:
            words = [p.text.lower() for p in parts]
            item['label'] = 'NAME:' + '-'.join(w.upper() for w in words)
            item['candidates'] = sorted(set(words) | {''.join(words), ''.join(w[0] for w in words)})
            item['evidence'] = [ev(p) for p in parts]
    return item


def extract_natural_english(text):
    ir = record(text, 'english', ENGLISH_ID)
    # Backtick apostrophes have the same length, so evidence offsets are unchanged.
    doc = english_pipeline()(text.replace('`', "'"))
    ir['model'] = {'name': MODEL, 'version': english_pipeline().meta['version']}
    ir['warnings'] = ['English dependency analysis is a model prediction. No coreference resolution.']
    nouns = [t for t in doc if t.pos_ in ('NOUN', 'PROPN')
             and not (t.dep_ == 'amod' and 'ADJ' in dictionary(t.text))]
    verbs = [t for t in doc if t.pos_ == 'VERB' and t.lemma_ != 'be']
    unsupported_verbs = [t for t in verbs if 'VERB' not in dictionary(t.text)]
    ir['unrecognized_predicates'] = [evidence(text, t.idx, t.idx+len(t)) for t in unsupported_verbs]
    ev = lambda t: evidence(text, t.idx, t.idx + len(t))
    negators = [t for t in doc if _negates(t)]
    sentence_negative = bool(negators)
    ir['observations'] = {
        'entities': [{'value': english_label(t), 'evidence': [ev(t)]} for t in nouns],
        'actions': [{'value': english_label(t), 'evidence': [ev(t)]} for t in verbs]}
    ir['content'] = {
        'entities': [_entity_item(t, ev) for t in nouns
                     if not (t.pos_ == 'PROPN' and t.dep_ == 'compound' and t.head.pos_ == 'PROPN')],
        'predicates': [{'label': english_label(t), 'candidates': english_candidates(t),
                        'light': t.lemma_.lower() in LIGHT_VERBS, 'dictionary': t not in unsupported_verbs,
                        'main': t.dep_ in MAIN_PREDICATE_DEPS, 'evidence': [ev(t)]} for t in verbs],
        'negative_sentence': sentence_negative,
        'negative_meaning': any(t.lower_ in NEGATIVE_MEANING or t.lemma_.lower() in NEGATIVE_MEANING
                                or t.lower_ == 'no' and not _negates(t) for t in doc),
        'negation_evidence': [ev(t) for t in negators]}
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
    elif len(verbs) == 1 and not negated and not unsupported_verbs and not sentence_negative:
        ir['facts']['negation'] = observed({'action': english_label(verbs[0]), 'negative': False},
            [ev(verbs[0])], 'No negation word anywhere in the sentence; one English predicate', 'one explicitly scoped predicate')
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
                n = numeric(doc[start:end+1].text.replace(',', '')) if start == end else None
            if n is None:
                continue
            symbols = [c for c in t.children if c.text in {'$': 'DOLLAR', '£': 'POUND', '€': 'EURO'}]
            head = t.head
            if symbols:
                unit = {'$': 'DOLLAR', '£': 'POUND', '€': 'EURO'}[symbols[0].text]
                unit_ev = ev(symbols[0])
            elif head.lemma_.lower() == 'year' and any(c.lower_ == 'old' for c in head.children) \
                    or head.lemma_.lower() == 'year' and head.i + 1 < len(doc) and doc[head.i + 1].lower_ == 'old':
                unit, unit_ev = 'AGE', ev(head)
                for item in ir['content']['entities']:
                    if item['evidence'][0]['start'] == head.idx:
                        item['candidates'] = sorted(set(item['candidates']) | {'age'})
            else:
                unit, unit_ev = english_label(head), ev(head)
            counts.append({'entity': unit, 'count': n})
            count_ev += [evidence(text, doc[start].idx, doc[end].idx+len(doc[end])), unit_ev]
    if counts:
        ir['facts']['numbers'] = observed(counts, count_ev,
            'Explicit dependency-linked numeral/unit; integer compounds, currency and ages supported, ordinals excluded',
            'explicit number attachments')
    # Roles: one active predicate with an explicit noun subject and object.
    framed = []
    for v in verbs:
        if v in unsupported_verbs or any(t.dep_ in ('nsubjpass', 'auxpass') for t in v.children):
            continue
        subjects = [t for t in v.children if t.dep_ == 'nsubj' and t.pos_ in ('NOUN', 'PROPN')]
        objects = [t for t in v.children if t.dep_ == 'dobj' and t.pos_ in ('NOUN', 'PROPN')]
        if len(subjects) == len(objects) == 1:
            framed.append((v, subjects[0], objects[0]))
    if len(framed) == 1:
        v, s, o = framed[0]
        ir['facts']['roles'] = observed({'action': english_label(v), 'agent': english_label(s),
            'patient': english_label(o)}, [ev(v), ev(s), ev(o)],
            'One active English predicate with explicit noun subject/object', 'explicit active roles')
        ir['content']['roles'] = {'action': english_candidates(v), 'agent': english_candidates(s),
                                  'patient': english_candidates(o)}
    return ir


# --- gloss -----------------------------------------------------------------------

def _base_decode(word):
    """Dictionary category of one plain uppercase word."""
    if word in SKIP:
        return ('structural', None)
    if numeric(word) is not None:
        return ('number', numeric(word))
    if not re.fullmatch(r'[A-Z]+', word):
        return ('unsupported', None)
    entries = dictionary(word)
    if 'VERB' in entries:
        lemma = entries['VERB'][0].upper()
        if lemma in ACTION_LABELS or word in ACTION_LABELS:
            return ('action', word if word in ACTION_LABELS else lemma)
        if any(p in entries for p in ('NOUN', 'ADJ', 'ADV')):
            return ('ambiguous', {'action': lemma, 'entity': entries.get('NOUN', (None,))[0]})
        return ('action', lemma)
    if 'ADJ' in entries or 'ADV' in entries:
        return ('modifier', None)
    if 'NOUN' in entries:
        return ('entity', entries['NOUN'][0].upper())
    if any(k in entries for k in ('ADP', 'DET', 'PRON', 'CCONJ', 'SCONJ', 'INTJ')):
        return ('modifier', None)
    return ('unsupported', None)


def _strip(token):
    t = token if re.fullmatch(r'[\W_]+', token) else token.rstrip('.,?!;')
    return re.sub(r'^(\([^)]*\))+', '', t).removeprefix('alt.')


@lru_cache(maxsize=65536)
def analyze_token(token, previous=''):
    """Category, normalized core, English concepts and markers of one gloss token."""
    out = {'kind': 'unsupported', 'value': None, 'core': '', 'concepts': (), 'negator': None,
           'directional': False, 'incorporated': None}
    bare = _strip(token)
    if not bare or re.fullmatch(r'[\W_]+', bare):
        return {**out, 'kind': 'structural'}
    if token.startswith(('NEG:', 'POS:', 'AGENT:', 'PATIENT:')):
        return {**out, 'kind': 'annotation'}
    if '"' in bare:  # gestures such as 5"umm" and 5"wave no"
        weak = bare.lower().startswith('no"') and previous.startswith('5"wave')
        return {**out, 'kind': 'structural', 'negator': 'weak' if weak else None}
    if STRUCTURAL.search(bare):
        # HOLD is a sign hold in ASLLRP but the verb "hold" in English-order gloss.
        return {**out, 'kind': 'structural', 'directional': bool(re.search(r':[a-z]', bare)),
                'concepts': ('hold', 'held') if bare == 'HOLD' else ()}
    neg_suffix = bool(NEG_SUFFIX.search(bare))
    bare = NEG_SUFFIX.sub('', bare)
    if bare.startswith('DESC-'):
        bare = bare[5:]
    directional = bool(re.match(r'^[a-z0-9]+:', bare) or re.search(r':[a-z]', bare)
                       or re.search(r'(?:^|-)(?:1|2|3)p(?:-|$)', bare))
    # Names: ns- name signs and fingerspelled candidates.
    if bare.startswith('ns-'):
        name = re.sub(r'^(?:fs-)?#?', '', bare[3:].lstrip('#'))
        name = lexicon.label_core(name).replace('-', '')
        return {**out, 'kind': 'entity', 'value': 'NAME:' + name, 'core': name, 'concepts': (name.lower(),)}
    if bare.startswith('fs-'):
        spelling = lexicon.label_core(bare[3:])
        parts = spelling.split('-')
        word = ''.join(parts) if all(len(p) == 1 for p in parts) else spelling
        words = [w for w in re.split(r'[+]', word.replace('FS-', '')) if w]
        concepts = set(word.lower().replace('-', '').replace('+', '') for _ in [0])
        for w in words:
            concepts |= lemmas(w) if re.fullmatch(r'[A-Z]+', w) else {w.lower()}
        concepts = tuple(sorted(concepts))
        word = words[0] if words else word
        entries = dictionary(word)
        if 'ADJ' in entries or 'ADV' in entries:
            return {**out, 'kind': 'modifier', 'core': word, 'concepts': concepts}
        if 'NOUN' in entries:
            return {**out, 'kind': 'entity', 'value': entries['NOUN'][0].upper(), 'core': word, 'concepts': concepts}
        if 'VERB' in entries:
            return {**out, 'kind': 'action', 'value': entries['VERB'][0].upper(), 'core': word, 'concepts': concepts}
        return {**out, 'kind': 'entity', 'value': 'NAME:' + word.upper(), 'core': word,
                'concepts': (word.lower().replace('-', ''),)}
    core = lexicon.label_core(bare)
    core = re.sub(r'(?<=[+/])\([^)]*\)', '', core).replace('FS-', '')
    core = re.sub(r'-(?:pl-)?arc$|-pl$', '', core)
    core = re.sub(r'^(?:[123]P-)|(?:-[123]P(?:-PL)?)$', '', core)
    out.update(core=core, directional=directional)
    if core in PREDICATE_NEGATORS or core in QUANTIFIER_NEGATORS:
        kind = 'negator'
        return {**out, 'kind': kind, 'negator': 'predicate' if core in PREDICATE_NEGATORS else 'quantifier',
                'concepts': ('not', 'no', 'never', 'none', 'nothing', 'nobody')}
    concepts = set(lexicon.words_for(core))
    pieces = [p for p in re.split(r'[+/]', core) if p]
    for p in pieces:
        concepts |= lexicon.words_for(p)
        for seg in [p] + p.split('-'):
            if re.fullmatch(r'[A-Z]+', seg):
                concepts |= lemmas(seg)
    if pieces and pieces[-1] == 'AGENT' and len(pieces) > 1:
        root = pieces[0].lower()
        concepts |= {root + 'er', root + 'r', root + 'or'}
    concepts.discard('agent')
    out['concepts'] = tuple(sorted(concepts))
    if core in WEAK_NEGATORS:
        out['negator'] = 'weak'
    if neg_suffix:
        out['negator'] = 'self'
    # Numbers, including numerals merged into another sign.
    parts = re.split(r'[+\-]', re.sub(r'_\d+', '', core))
    if numeric(core) is not None or (len(parts) > 1 and numeric_phrase(parts) is not None):
        n = numeric(core) if numeric(core) is not None else numeric_phrase(parts)
        return {**out, 'kind': 'number', 'value': n}
    m = re.fullmatch(r'AGE-(.+)', core)
    if m and numeric_phrase(m.group(1).split('-')) is not None:
        return {**out, 'kind': 'number', 'value': numeric_phrase(m.group(1).split('-')), 'incorporated': 'AGE'}
    for unit in sorted(INCORPORATED_UNITS, key=len, reverse=True):
        if core.endswith('-' + unit):
            n = numeric_phrase(core[:-len(unit) - 1].split('-'))
            if n is not None:
                return {**out, 'kind': 'number', 'value': n, 'incorporated': unit.split('-')[0]}
    if any(ch.isdigit() for ch in core) or any(ch.isnumeric() for ch in core):
        return {**out, 'kind': 'unresolved_number'}
    if pieces and pieces[-1] == 'AGENT' and len(pieces) > 1:
        return {**out, 'kind': 'entity', 'value': core}
    # Category of the sign: slash alternatives may disagree; compounds use their head.
    kinds = []
    for p in pieces or [core]:
        k = _base_decode(p)
        if k[0] == 'unsupported' and '-' in p:
            k = _base_decode(p.split('-')[0])
            if k[0] == 'entity':
                k = ('entity', p)
        kinds.append(k)
    by_kind = {k for k, _ in kinds}
    if len(pieces) > 1 and '/' in core and len(by_kind - {'unsupported'}) > 1:
        # Slash glosses with different categories, e.g. VOMIT/HATE, stay visible.
        actions = [v for k, v in kinds if k == 'action']
        if actions:
            return {**out, 'kind': 'action', 'value': actions[-1]}
    kind, value = kinds[0] if '+' in core else next((k for k in kinds if k[0] != 'unsupported'), kinds[0])
    return {**out, 'kind': kind, 'value': value}


def decode(token):
    """Category and value of one token (kept for the legacy natural facts)."""
    info = analyze_token(token)
    kind = info['kind']
    if kind in ('negator', 'annotation'):
        return ('structural', None)
    if kind == 'unresolved_number':
        return ('unsupported', None)
    return (kind, info['value'])


def extract_natural_gloss(text, nmm=None, notation=None):
    if notation not in NOTATIONS:
        raise ValueError(f'Unsupported gloss notation: {notation}')
    ir = record(text, 'gloss', GLOSS_ID)
    tokens, ev = ir['tokens'], spans(text)
    infos = [analyze_token(t, tokens[i-1] if i else '') for i, t in enumerate(tokens)]
    decoded = [decode(t) if info['kind'] != 'annotation' else ('annotation', None)
               for t, info in zip(tokens, infos)]
    for i, info in enumerate(infos):
        if info['kind'] == 'number' and info['incorporated']:
            decoded[i] = ('number', info['value'])
    predicate_negator = lambda i: i >= 0 and infos[i]['negator'] == 'predicate'
    # Explicit NEG:/POS: or an adjacent predicate negator supports a lexical predicate reading.
    # A numeral plus bounded modifiers supports a noun reading. Unresolved
    # noun/verb homographs veto a sole-action assertion rather than cause flags.
    for i, token in enumerate(tokens):
        # HAVE is normally structural, but NOT HAVE explicitly scopes a
        # predicate. Keep that local reading even when another verb follows.
        scoped_have = infos[i]['core'] == 'HAVE' and predicate_negator(i - 1)
        if _strip(token).startswith(('fs-', 'ns-')) or (
                infos[i]['kind'] in ('structural', 'negator', 'number') and not scoped_have):
            continue  # names and function signs are never re-read as predicates
        core = infos[i]['core'] or token.rstrip('.,?!')
        entries = dictionary(core) if re.fullmatch(r'[A-Z]+', core) else {}
        previous = tokens[i-1] if i > 0 else ''
        scope = previous.split(':', 1)[1] if previous.startswith(('NEG:', 'POS:')) else None
        if 'VERB' in entries and (entries['VERB'][0].upper() == scope or predicate_negator(i - 1)):
            decoded[i] = ('action', entries['VERB'][0].upper())
    for i, (kind, value) in enumerate(decoded):
        if kind != 'ambiguous':
            continue
        previous = tokens[i-1] if i > 0 else ''
        if predicate_negator(i - 1) or infos[i]['negator'] == 'self' \
                or previous in ('NEG:'+value['action'], 'POS:'+value['action']):
            decoded[i] = ('action', value['action'])
        elif value['entity'] and any(decoded[j][0] == 'number' and
                all(decoded[k][0] == 'modifier' for k in range(j+1, i))
                for j in range(max(0, i-3), i)):
            decoded[i] = ('entity', value['entity'].upper())
    # A noun/verb homograph next to a recognized action reads as its noun.
    def neighbour(i, step):
        j = i + step
        while 0 <= j < len(decoded) and decoded[j][0] in ('modifier', 'structural', 'number'):
            j += step
        return decoded[j][0] if 0 <= j < len(decoded) else None
    for i, (kind, value) in enumerate(list(decoded)):
        if kind == 'ambiguous' and value['entity'] and 'action' in (neighbour(i, -1), neighbour(i, 1)):
            decoded[i] = ('entity', value['entity'].upper())
    actions = [(value, i) for i, (kind, value) in enumerate(decoded) if kind == 'action']
    entities = [(value, i) for i, (kind, value) in enumerate(decoded) if kind == 'entity']
    unsupported = [ev[i] for i, (kind, _) in enumerate(decoded) if kind == 'unsupported']
    ambiguous = [ev[i] for i, (kind, _) in enumerate(decoded) if kind == 'ambiguous']
    ir['unrecognized'] = unsupported
    ir['ambiguous_labels'] = ambiguous
    ir['notation'] = notation
    ir['nmm'] = dict(nmm) if nmm else None
    ir['warnings'] = ['Gloss dictionary categories are lexical hypotheses, not an ASL parse.',
                      'Roles come only from plain-verb subject-verb-object order without topic marking.',
                      'Fingerspelled dictionary nouns are treated as nouns; other spellings are candidate names.']
    ir['signs'] = [{'index': i, 'kind': decoded[i][0], 'core': infos[i]['core'],
                    'concepts': list(infos[i]['concepts']), 'evidence': [ev[i]],
                    'name': _strip(tokens[i]).startswith(('fs-', 'ns-')) and decoded[i][0] == 'entity',
                    'name_sign': _strip(tokens[i]).startswith('ns-') and not _strip(tokens[i]).startswith('ns-fs-')}
                   for i in range(len(tokens)) if infos[i]['concepts']]
    ir['pointing'] = any(re.match(r'^(?:IX|POSS|SELF)-(?:3p|loc)', _strip(t)) or re.match(r'^IX:', _strip(t))
                         for t in tokens)
    ir['classifier'] = any(re.match(r'^[A-Z0-9]*CL[:"\-]', _strip(t)) for t in tokens)
    ir['manual_negation'] = [{'strength': infos[i]['negator'], 'evidence': [ev[i]]}
                             for i in range(len(tokens)) if infos[i]['negator']]
    ir['numerals'] = [{'value': infos[i]['value'], 'evidence': [ev[i]]}
                      for i in range(len(tokens)) if infos[i]['kind'] == 'number']
    ir['unresolved_numerals'] = [ev[i] for i in range(len(tokens)) if infos[i]['kind'] == 'unresolved_number']
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
        elif infos[i]['negator'] == 'self' and decoded[i][0] == 'action':
            polarity.append((decoded[i][1], True, i, i))
        elif infos[i]['negator'] == 'predicate':
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
    counts, count_ev, unresolved, attached = [], [], [], []
    for i, (kind, value) in enumerate(decoded):
        if kind != 'number':
            continue
        if infos[i]['incorporated']:
            counts.append({'entity': infos[i]['incorporated'], 'count': value})
            count_ev += [ev[i], ev[i]]
            attached.append({'value': value, 'concepts': sorted(lemmas(infos[i]['incorporated']) | {'age', 'old'}
                             if infos[i]['incorporated'] == 'AGE' else lemmas(infos[i]['incorporated'])), 'evidence': [ev[i]]})
            continue
        if i > 0 and tokens[i-1] in NUMBER_PREFIX_LABELS:
            counts.append({'entity': tokens[i-1], 'count': value})
            count_ev += [ev[i], ev[i-1]]
            attached.append({'value': value, 'concepts': sorted(lemmas(tokens[i-1])), 'evidence': [ev[i], ev[i-1]]})
            continue
        j = i+1
        # Allow ordinary adjectives between a count and its noun, never another
        # noun, event, locus, unknown label or numeral. Bounded local attachment.
        while j < len(decoded) and j <= i+3 and decoded[j][0] == 'modifier':
            j += 1
        if j < len(decoded) and decoded[j][0] == 'entity' and j <= i+3:
            counts.append({'entity': decoded[j][1], 'count': value})
            count_ev += [ev[i], ev[j]]
            attached.append({'value': value, 'concepts': list(infos[j]['concepts']) or [str(decoded[j][1]).lower()],
                             'evidence': [ev[i], ev[j]]})
        else:
            unresolved.append(ev[i])
    ir['unattached_numbers'] = unresolved
    ir['number_attachments'] = attached
    if counts and not unresolved:
        ir['facts']['numbers'] = observed(counts, count_ev,
            'Local numeral/noun attachment, bounded modifiers, merged numerals or documented AGE/CHAPTER/PART/PAGE/SECTION/VOLUME prefix', 'explicit number attachments')
    elif unresolved:
        ir['facts']['numbers']['reason'] = 'At least one numeral has no supported local noun attachment'
    # Roles: subject-verb-object order for plain verbs only.
    ir['clauses'], gate = [], None
    if (nmm or {}).get('topic') and notation != 'aslg_pc12':
        gate = 'Topic marking (non-manual) can front the object; word order is not role evidence'
    clauses = []
    for i, (kind, value) in enumerate(decoded):
        if kind != 'action' or gate:
            continue
        if notation != 'aslg_pc12' and (infos[i]['directional'] or infos[i]['core'] in DIRECTIONAL_VERBS
                                        and infos[i]['directional']):
            continue
        before = [j for j in range(i) if decoded[j][0] == 'entity']
        after = []
        for j in range(i + 1, len(decoded)):
            if decoded[j][0] == 'action':
                break
            if decoded[j][0] == 'entity':
                after.append(j)
                break
        if notation != 'aslg_pc12' and len(before) != 1:
            continue  # two preposed nouns may be a topicalized object
        if before and after:
            a, p = before[-1], after[0]
            clauses.append({'action': i, 'agent': a, 'patient': p})
    ir['clauses'] = [{'action': {'label': decoded[c['action']][1], 'concepts': list(infos[c['action']]['concepts']), 'evidence': [ev[c['action']]]},
                      'agent': {'label': decoded[c['agent']][1], 'concepts': list(infos[c['agent']]['concepts']), 'evidence': [ev[c['agent']]]},
                      'patient': {'label': decoded[c['patient']][1], 'concepts': list(infos[c['patient']]['concepts']), 'evidence': [ev[c['patient']]]}}
                     for c in clauses]
    ir['roles_gate'] = gate
    if len(clauses) == 1:
        c = clauses[0]
        ir['facts']['roles'] = observed({'action': decoded[c['action']][1], 'agent': decoded[c['agent']][1],
                                         'patient': decoded[c['patient']][1]},
                                        [ev[c['action']], ev[c['agent']], ev[c['patient']]],
                                        'Plain-verb subject-verb-object order without topic marking', 'word-order roles')
    else:
        ir['facts']['roles']['reason'] = gate or 'No single plain-verb subject-verb-object clause in gloss order'
    return ir
