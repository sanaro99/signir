"""Recovered prior-study Sign F1; lossy reduction is ONLY for this baseline.

Adapted from aslgloss/evaluation/sign_selection.py (MIT). See THIRD_PARTY.md.
"""
from collections import Counter
import re

_DECORATION = re.compile(r'^\([^)]*\)')
_NAMING = re.compile(r'^(?:ns-|fs-|#)+')
_LOCUS = re.compile(r':[a-z](?:/[a-z])*$')
_VARIANT = re.compile(r'_\d+$')


def lexical_core(token):
    if '"' in token:
        return None
    t = token
    while _DECORATION.match(t):
        t = _DECORATION.sub('', t)
    t = _NAMING.sub('', t)
    t = _LOCUS.sub('', t)
    t = _VARIANT.sub('', t)
    t = re.split(r'[+/^]', t)[0]
    t = re.sub(r'[^A-Za-z-]', '', t)
    if '-' in t:
        t = t.split('-')[0]
    return t.upper() or None


def multiset_f1(a, b):
    a, b = Counter(a), Counter(b)
    overlap = sum((a & b).values())
    p = overlap / sum(a.values()) if a else 0.0
    r = overlap / sum(b.values()) if b else 0.0
    return 2 * p * r / (p + r) if p + r else 0.0


def sign_f1(hypothesis, reference):
    return multiset_f1([c for t in hypothesis.split() if (c := lexical_core(t))],
                       [c for t in reference.split() if (c := lexical_core(t))])


def word_f1(hypothesis, reference):
    """Case-sensitive whitespace token multiset F1, without label normalization."""
    return multiset_f1(hypothesis.split(), reference.split())
