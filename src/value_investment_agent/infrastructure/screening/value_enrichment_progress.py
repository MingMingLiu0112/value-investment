"""Crash-released lock and integrity-checked local enrichment checkpoints."""
from contextlib import contextmanager
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from uuid import uuid4


def digest(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest()


class ValueEnrichmentProgress:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.directory = (self.root / 'runtime/value-evidence-enrichment/progress-v1').resolve()
        self.staging = (self.root / '.tmp/value-enrichment-progress').resolve()
        if not self.directory.is_relative_to(self.root) or not self.staging.is_relative_to(self.root):
            raise ValueError('progress path outside repository')

    @contextmanager
    def locked(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        with (self.directory / 'writer.lock').open('a+b') as stream:
            stream.seek(0, 2)
            if stream.tell() == 0:
                stream.write(b'0')
                stream.flush()
            stream.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                yield self
            finally:
                stream.seek(0)
                if os.name == 'nt':
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(stream, fcntl.LOCK_UN)

    def load(self, key):
        paths = [self.directory / (key + '-' + str(attempt) + '.json') for attempt in range(1, 4)]
        retained = [path for path in paths if path.exists()]
        if not retained:
            return None
        return self._load_checkpoint(retained[-1], key)

    def _load_checkpoint(self, path, key):
        envelope = json.loads(path.read_bytes())
        payload = envelope['payload']
        if envelope['sha256'] != digest(payload) or payload['key'] != key:
            raise ValueError('enrichment progress integrity mismatch')
        binding = payload['execution_binding']
        execution = (self.root / binding['path']).resolve()
        if (not execution.is_relative_to(self.root / 'runtime')
                or hashlib.sha256(execution.read_bytes()).hexdigest() != binding['sha256']):
            raise ValueError('enrichment checkpoint execution binding mismatch')
        outcome = json.loads(execution.read_bytes())
        result_binding = outcome.get('result_binding')
        if result_binding:
            result = (self.root / result_binding['path']).resolve()
            if (not result.is_relative_to(self.root / 'runtime')
                    or hashlib.sha256(result.read_bytes()).hexdigest() != result_binding['sha256']):
                raise ValueError('enrichment checkpoint result binding mismatch')
        return {**payload, 'last_state': outcome.get('state'), 'next_action': outcome.get('next_action')}

    def save(self, payload):
        self.staging.mkdir(parents=True, exist_ok=True)
        temporary = self.staging / (uuid4().hex + '.json')
        try:
            with temporary.open('xb') as stream:
                stream.write(json.dumps({'payload': payload, 'sha256': digest(payload)},
                    sort_keys=True, allow_nan=False).encode())
                stream.flush()
                os.fsync(stream.fileno())
            # Publish append-only checkpoints. An interrupted/restarted writer
            # cannot replace an earlier attempt or its bound execution receipt.
            os.link(temporary, self.directory / (payload['key'] + '-' + str(payload['attempt']) + '.json'))
        finally:
            temporary.unlink(missing_ok=True)

    def completed_sources(self, *, cutoff: datetime):
        """Discover source declarations only from integrity-bound, completed work.

        The caller must re-evaluate original/independent evidence. Checkpoints
        are scheduling history, never authority to accept a financial fact.
        """
        if cutoff.utcoffset() is None:
            raise ValueError('enrichment consumption cutoff must be timezone-aware')
        declarations = {}
        for path in sorted(self.directory.glob('*.json')):
            envelope = json.loads(path.read_bytes())
            payload = envelope['payload']
            if envelope['sha256'] != digest(payload):
                raise ValueError('enrichment progress integrity mismatch')
            completed = payload.get('completed_at')
            if completed is None:
                continue  # Old scheduling receipts establish no adoption availability.
            stamp = datetime.fromisoformat(completed)
            if stamp.utcoffset() is None:
                raise ValueError('enrichment checkpoint availability must be timezone-aware')
            if stamp > cutoff:
                continue
            self._load_checkpoint(path, payload['key'])
            attempt_path = (self.root / payload['execution_binding']['path']).resolve()
            outcome = json.loads(attempt_path.read_bytes())
            result_binding = outcome.get('result_binding')
            if not result_binding:
                continue
            result = json.loads((self.root / result_binding['path']).read_bytes())
            if not result.get('adopted_points'):
                continue
            source = result['source_extraction']['identity']['source']
            identity = (source['symbol'], source['period'])
            previous = declarations.get(identity)
            if previous is None or previous[0] < stamp:
                declarations[identity] = (stamp, source)
        if len(declarations) > 128:
            raise ValueError('retained enrichment replay exceeds 128-source budget')
        return [item[1] for _, item in sorted(declarations.items())]

    def registered_adoption(self, symbol: str, *, cutoff: datetime):
        """Read the latest symbol binding from checkpoints, never scan run folders."""
        if cutoff.utcoffset() is None:
            raise ValueError('enrichment consumption cutoff must be timezone-aware')
        paths = list(self.directory.glob('*.json'))
        if len(paths) > 4096:
            raise ValueError('enrichment progress exceeds bounded checkpoint read budget')
        candidates = []
        for path in paths:
            envelope = json.loads(path.read_bytes())
            payload = envelope['payload']
            adoption = payload.get('registered_adoption')
            if not adoption or adoption.get('symbol') != symbol:
                continue
            if envelope['sha256'] != digest(payload):
                raise ValueError('enrichment progress integrity mismatch')
            stamp = datetime.fromisoformat(payload['completed_at'])
            if stamp.utcoffset() is None:
                raise ValueError('enrichment progress clock invalid')
            if stamp <= cutoff:
                candidates.append((stamp, path, payload))
        if not candidates:
            return None
        _, path, payload = max(candidates, key=lambda row: (row[0], row[1].name))
        self._load_checkpoint(path, payload['key'])
        outcome = json.loads((self.root / payload['execution_binding']['path']).read_bytes())
        return dict(payload['registered_adoption'], result_binding=outcome['result_binding'])
