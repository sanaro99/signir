"""One-attempt experiment; an adapter receives inputs, never a hidden reference."""
from typing import Protocol
from .compare import check_pair


class CorrectionAdapter(Protocol):
    def __call__(self, request: dict) -> str: ...


class SavedResponses:
    def __init__(self, responses):
        self.responses = responses

    def __call__(self, request):
        item = self.responses.get(request['id'])
        if not item or item.get('original_gloss') != request['original_gloss'] or item.get('english') != request['english']:
            raise ValueError('No exact saved correction fixture for this input')
        return item['corrected_gloss']


def correct_once(pair, adapter: CorrectionAdapter, method_id):
    before = check_pair(pair['english'], pair['gloss'])
    request = {'id': pair['id'], 'english': pair['english'], 'original_gloss': pair['gloss'],
               'diagnostic': before['checks'], 'instruction': 'One correction attempt for the explicit diagnostics; retain other facts.'}
    corrected = adapter(request)  # exactly one call; no retry, loop, or iterative repair
    if not isinstance(corrected, str):
        raise ValueError('Correction adapter must return a gloss string')
    after = check_pair(pair['english'], corrected)
    improved, regressions, lost_coverage, gained_coverage = [], [], [], []
    for name in before['checks']:
        a, b = before['checks'][name]['status'], after['checks'][name]['status']
        if a == 'MISMATCH' and b == 'MATCH':
            improved.append(name)
        if (a == 'MATCH' and b != 'MATCH') or (a == 'UNKNOWN' and b == 'MISMATCH'):
            regressions.append(name)
        if a != 'UNKNOWN' and b == 'UNKNOWN':
            lost_coverage.append(name)
        if a == 'UNKNOWN' and b != 'UNKNOWN':
            gained_coverage.append(name)
    return {'id': pair['id'], 'method': method_id, 'attempts': 1, 'request': request,
            'original_gloss': pair['gloss'], 'corrected_gloss': corrected,
            'before': before, 'after': after, 'improved': improved, 'regressions': regressions,
            'lost_coverage': lost_coverage, 'gained_coverage': gained_coverage,
            'interpretation': 'Checker transitions only; not proof of improved ASL.'}
