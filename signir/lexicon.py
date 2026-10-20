"""Optional English-word to gloss-label dictionaries used to recognize synonyms.

A dictionary maps an English word to the gloss labels that can express it, e.g.
{"parents": ["MOTHER+FATHER"], "teacher": ["TEACH+AGENT"]}. The gloss reader
inverts it so each gloss sign lists the English words it may express. It never
sees the English sentence being checked. No restricted dictionary is bundled;
configure one with SIGNIR_GLOSS_LEXICON (paths separated by os.pathsep) or
configure(paths).
"""
import hashlib
import json
import os
from pathlib import Path
import re

_INDEX = None
_SOURCES = []


def label_core(label):
    """Strip hand/handshape wrappers, variant numbers, repetition and loci."""
    t = re.sub(r'^(\([^)]*\))+', '', label.strip())
    t = t.removeprefix('alt.').lstrip('#')
    t = re.sub(r'^[a-z0-9]+:', '', t)
    t = re.sub(r':[a-z0-9/-]+$', '', t)
    t = re.sub(r'_\d+$', '', t)
    return t.rstrip('+').upper()


def _load(path):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if isinstance(data, dict) and isinstance(data.get('entries'), dict):
        data = data['entries']
    if not isinstance(data, dict):
        raise ValueError(f'Unsupported gloss lexicon format: {path}')
    return data


def configure(paths=None):
    """Load dictionaries; None reads SIGNIR_GLOSS_LEXICON; an empty list disables."""
    global _INDEX, _SOURCES
    if paths is None:
        paths = [p for p in os.environ.get('SIGNIR_GLOSS_LEXICON', '').split(os.pathsep) if p]
    index, sources = {}, []
    for path in paths:
        raw = Path(path).read_bytes()
        sources.append({'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest()})
        for word, labels in _load(path).items():
            if not isinstance(word, str) or not isinstance(labels, list):
                continue
            word = word.strip().lower()
            if not word or ' ' in word:
                continue
            for label in labels:
                if isinstance(label, str) and label.strip():
                    index.setdefault(label_core(label), set()).add(word)
    _INDEX, _SOURCES = index, sources
    from . import natural
    natural.clear_caches()
    return len(index)


def words_for(core):
    """English words a normalized gloss label can express, per the dictionaries."""
    if _INDEX is None:
        configure()
    return _INDEX.get(core, set())


def fingerprint():
    if _INDEX is None:
        configure()
    return list(_SOURCES)
