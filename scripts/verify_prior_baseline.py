"""Execute recovered old pure functions and compare, without heavy imports."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from signir.baselines import sign_f1


def verify(source, predictions):
    tree = ast.parse(source.read_text(encoding='utf-8'))
    allowed = {'lexical_core', 'cores', 'sentence_sign_prf'}
    nodes = [n for n in tree.body if isinstance(n, (ast.Assign, ast.AnnAssign)) or
             isinstance(n, ast.FunctionDef) and n.name in allowed or
             isinstance(n, ast.Import) or isinstance(n, ast.ImportFrom) and n.module in ('collections', '__future__')]
    namespace = {}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), 'exec'), namespace)
    rows = [json.loads(x) for x in predictions.read_text(encoding='utf-8').splitlines() if x]
    probes = [(r['hypothesis'], r['reference']) for r in rows]
    probes += [('BUY 3 APPLE', 'BUY 9 APPLE'), ('APPLE', 'APPLE APPLE'), ('', ''),
               ('(1h)(25)WHY fs-A-L-I-C-E GIVE:i/j TOTAL_2 MOTHER+FATHER', 'WHY fs-ALICE GIVE TOTAL MOTHER')]
    differences = sum(sign_f1(h, r) != namespace['sentence_sign_prf'](h, r)[2] for h, r in probes)
    if differences:
        raise AssertionError(f'{differences} baseline parity failures')
    return {'comparisons': len(probes), 'differences': differences,
            'prior_source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
            'predictions_sha256': hashlib.sha256(predictions.read_bytes()).hexdigest()}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--source', required=True, type=Path)
    p.add_argument('--predictions', required=True, type=Path)
    p.add_argument('--out', required=True, type=Path)
    a = p.parse_args()
    result = verify(a.source, a.predictions)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result))
