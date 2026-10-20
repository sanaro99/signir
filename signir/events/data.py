"""Event-only batch validation and source/output protection."""
from pathlib import Path


def ensure_distinct_paths(inputs, outputs):
    """Reject path aliases, including existing symbolic and hard links."""
    protected = [Path(p) for p in inputs]
    for output in map(Path, outputs):
        for other in protected:
            if (output.resolve() == other.resolve()
                    or output.exists() and other.exists() and output.samefile(other)):
                raise ValueError(f'Output path must not overwrite an input or another output: {output}')
        protected.append(output)


def validate_rows(rows):
    """Validate the event input contract before any model calls."""
    rows = list(rows)
    ids = set()
    for i, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            raise ValueError(f'Pair {i}: expected a JSON object')
        for key in ('id', 'english', 'gloss', 'source_group'):
            value = row.get(key)
            if not isinstance(value, str) or (key != 'gloss' and not value.strip()):
                raise ValueError(f'Pair {i}: requires string {key}; only gloss may be empty')
        provenance = row.get('provenance')
        if (not isinstance(provenance, dict)
                or any(not isinstance(provenance.get(k), str) or not provenance[k].strip()
                       for k in ('kind', 'version'))):
            raise ValueError(f'Pair {i}: provenance requires nonempty string kind and version')
        if row['id'] in ids:
            raise ValueError('Duplicate pair ID: ' + row['id'])
        ids.add(row['id'])
    return rows
