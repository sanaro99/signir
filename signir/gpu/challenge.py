"""Authored diagnostic challenges with literal, partial scope expectations.

No reader or model generates these expected labels. They are engineering probes,
not natural ASL examples or a held-out accuracy benchmark.
"""
import json
from pathlib import Path

from .storage import digest


def build_challenge():
    pairs, gold = [], []
    for index, name in enumerate(('Alice', 'Bob', 'Clara', 'David')):
        other = ('Erin', 'Frank', 'Grace', 'Helen')[index]
        fs, target = 'fs-' + name.upper(), 'fs-' + other.upper()
        examples = [
            ('quantity-change', f'{name} buys 3 apples.', f'{fs} BUY 9 APPLE', {'numbers':'MISMATCH','action':'MATCH'}),
            ('quantity-preserved', 'The teacher buys three books.', 'TEACHER BUY 3 BOOK', {'numbers':'MATCH','action':'MATCH'}),
            ('predicate-change', f'{name} buys apples.', f'{fs} SELL APPLE', {'action':'MISMATCH','entities':'MATCH'}),
            ('absent-negation', f'{name} does not buy apples.', f'{fs} BUY APPLE', {'action':'MATCH','negation':'UNKNOWN'}),
            ('quantity-bound', f'{name} buys at least three books.', f'{fs} BUY 4 BOOK', {'numbers':'UNKNOWN'}),
            ('repeated-counts', f'{name} buys three books, and {other} buys five books.',
                f'{fs} BUY 5 BOOK {target} BUY 3 BOOK', {'numbers':'UNKNOWN','action':'UNKNOWN','negation':'UNKNOWN'}),
            ('modal-homograph', f'{name} can watch the birds.', f'{fs} CAN WATCH BIRD', {'action':'MATCH'}),
            ('negative-property', 'The student is not sleepy.', 'STUDENT NOT SLEEPY', {'action':'MATCH','negation':'MATCH'}),
            ('directional-wrapper', f'{name} gives a book to {other}.', f'{fs} i:GIVE:j BOOK {target}', {'action':'MATCH','roles':'UNKNOWN'}),
            ('role-order', f'{name} helps {other}.', f'{target} HELP {fs}', {'action':'MATCH','entities':'MATCH','roles':'UNKNOWN'}),
            ('ambiguous-property', 'The room is clean.', 'ROOM CLEAN', {'action':'UNKNOWN','negation':'UNKNOWN'}),
            ('chapter-identifier', 'Please read chapter two.', 'PLEASE READ CHAPTER 9', {'numbers':'MISMATCH'}),
            ('unicode-evidence', f'{name} didn’t buy 3 apples.', f'{fs} NOT BUY 9 APPLE', {'numbers':'MISMATCH','negation':'MATCH'}),
            ('currency-unit', f'{name} receives a $100 card.', f'{fs} RECEIVE 100 DOLLAR CARD', {'numbers':'MATCH'}),
            ('counterfactual-preserved', f'{name} buys 3 apples.', f'{fs} BUY 3 APPLE', {'numbers':'MATCH'}),
            ('counterfactual-changed', f'{name} buys 9 apples.', f'{fs} BUY 3 APPLE', {'numbers':'MISMATCH'}),
        ]
        for phenomenon, english, gloss, expected in examples:
            identifier = f'{phenomenon}-{index+1:02d}'
            pair = {'id':identifier,'english':english,'gloss':gloss,
                    'source_group':'authored-challenge','family_id':f'{phenomenon}-{index+1}',
                    'split':'diagnostic','phenomenon':phenomenon,
                    'provenance':{'kind':'authored','version':'gpu-diagnostic-1'}}
            pairs.append(pair)
            gold.append({'id':identifier,'annotation_kind':'authored',
                'pair_sha256':digest({'english':english,'gloss':gloss}),
                'checks':{'roles':'UNKNOWN',**expected}})
    # Several phenomena do not use the name template; retain each literal pair
    # once so repeated authored stems do not inflate the reported case count.
    unique, selected_pairs, selected_gold = set(), [], []
    for pair, expected in zip(pairs, gold):
        key = (pair['english'], pair['gloss'])
        if key not in unique:
            unique.add(key)
            selected_pairs.append(pair)
            selected_gold.append(expected)
    return selected_pairs, selected_gold


def write_challenge(output):
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError('Challenge output must be a new or empty directory')
    pairs, gold = build_challenge()
    output.mkdir(parents=True, exist_ok=True)
    for filename, rows in (('pairs.jsonl',pairs),('gold.jsonl',gold)):
        with (output/filename).open('x',encoding='utf-8') as handle:
            for row in rows:
                handle.write(json.dumps(row,ensure_ascii=False)+'\n')
    return pairs
