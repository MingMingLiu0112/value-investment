"""Read existing native facts and hash-bound official originals, without writes."""
import hashlib
import json
from datetime import datetime
from pathlib import Path


def load_parent_facts(root, relative_path, *, cutoff):
    root = Path(root).resolve()
    def contained(relative):
        path = (root / relative).resolve()
        if not path.is_relative_to(root):
            raise ValueError('source outside root')
        return path
    raw = contained(relative_path).read_bytes()
    packet = json.loads(raw)
    if cutoff.tzinfo is None:
        raise ValueError('aware cutoff required')
    sources = {}
    for source in packet['sources']:
        if source['id'] in sources:
            raise ValueError('duplicate source')
        if datetime.fromisoformat(source['available_at']) > cutoff:
            raise ValueError('future source')
        if hashlib.sha256(contained(source['path']).read_bytes()).hexdigest() != source['sha256']:
            raise ValueError('source hash mismatch')
        sources[source['id']] = source
    facts = []
    for fact in packet['facts']:
        if fact.get('scope') != 'parent':
            continue
        if fact['source_id'] not in sources or not fact.get('physical_page'):
            raise ValueError('unbound fact')
        facts.append(fact)
    return dict(facts=facts, sources=sources,
                native_sha256=hashlib.sha256(raw).hexdigest(), action='no_order')
