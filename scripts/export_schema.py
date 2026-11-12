"""Write the SignIR 2.0 JSON Schema from the Pydantic models: python scripts/export_schema.py"""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from signir.events.schema import Graph  # noqa: E402

PATH = Path(__file__).resolve().parents[1] / 'schemas' / 'signir-2.0.schema.json'


def schema_text():
    schema = Graph.model_json_schema()
    schema = {'$schema': 'https://json-schema.org/draft/2020-12/schema', '$id': 'signir-2.0',
              'description': ('SignIR 2.0 graph. JSON Schema covers structure only; cross-field rules '
                              '(references, evidence text, gloss-only bases) are enforced by signir.events.schema.'),
              **schema}
    return json.dumps(schema, indent=2, sort_keys=True) + '\n'


if __name__ == '__main__':
    PATH.write_text(schema_text(), encoding='utf-8', newline='\n')
    print(f'Wrote {PATH}')
