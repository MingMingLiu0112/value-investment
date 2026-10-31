"""Crash-released lock and integrity-checked local enrichment checkpoints."""
from contextlib import contextmanager
import hashlib
import json
import os
from datetime import date, datetime
from pathlib import Path
import re
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
        if not execution.is_relative_to(self.root / 'runtime'):
            raise ValueError('enrichment checkpoint execution binding mismatch')
        execution_raw = execution.read_bytes()
        if hashlib.sha256(execution_raw).hexdigest() != binding['sha256']:
            raise ValueError('enrichment checkpoint execution binding mismatch')
        outcome = json.loads(execution_raw)
        result_binding = outcome.get('result_binding')
        if result_binding:
            result = (self.root / result_binding['path']).resolve()
            if not result.is_relative_to(self.root / 'runtime'):
                raise ValueError('enrichment checkpoint result binding mismatch')
            result_raw = result.read_bytes()
            if hashlib.sha256(result_raw).hexdigest() != result_binding['sha256']:
                raise ValueError('enrichment checkpoint result binding mismatch')
        scheduling = payload.get('scheduling')
        if scheduling is not None or outcome.get('scheduling') is not None:
            if (not isinstance(scheduling, dict) or set(scheduling) != {
                    'symbol', 'financial_period', 'accepted_field_count', 'implementation_sha256'}
                    or scheduling != outcome.get('scheduling')
                    or scheduling['symbol'] != outcome.get('symbol')
                    or not isinstance(scheduling['symbol'], str)
                    or not re.fullmatch(r'[0-9]{6}', scheduling['symbol'])
                    or type(scheduling['accepted_field_count']) is not int
                    or scheduling['accepted_field_count'] < 0
                    or scheduling['financial_period'] is not None and not isinstance(scheduling['financial_period'], str)
                    or not isinstance(scheduling['implementation_sha256'], str)
                    or not re.fullmatch(r'[0-9a-f]{64}', scheduling['implementation_sha256'])):
                raise ValueError('enrichment scheduling binding mismatch')
            if scheduling['financial_period'] is not None:
                period = date.fromisoformat(scheduling['financial_period'])
                if period.isoformat() != scheduling['financial_period'] or (period.month, period.day) != (12, 31):
                    raise ValueError('enrichment scheduling financial period invalid')
            if result_binding:
                result_payload = json.loads(result_raw)
                if (result_payload.get('symbol', scheduling['symbol']) != scheduling['symbol']
                        or result_payload.get('period', scheduling['financial_period']) != scheduling['financial_period']):
                    raise ValueError('enrichment scheduling result identity mismatch')
        return {**payload, 'last_state': outcome.get('state'), 'next_action': outcome.get('next_action')}

    def scheduling_history(self, *, cutoff: datetime):
        """Verified history orders work only; never reuse facts across work keys."""
        if cutoff.utcoffset() is None:
            raise ValueError('scheduling cutoff must be timezone-aware')
        paths = list(self.directory.glob('*.json'))
        if len(paths) > 4096:
            raise ValueError('enrichment progress exceeds bounded checkpoint read budget')
        history = {}
        for path in paths:
            envelope = json.loads(path.read_bytes())
            payload = envelope['payload']
            if (type(payload.get('attempt')) is not int or not 1 <= payload['attempt'] <= 3
                    or not isinstance(payload.get('key'), str)
                    or not re.fullmatch(r'[0-9a-f]{64}', payload['key'])
                    or path.name != f"{payload['key']}-{payload['attempt']}.json"):
                raise ValueError('enrichment scheduling checkpoint identity mismatch')
            checked = self._load_checkpoint(path, payload['key'])
            scheduling = checked.get('scheduling')
            if scheduling is None:
                continue  # Legacy keys do not disclose a period or implementation.
            stamp = datetime.fromisoformat(checked['completed_at'])
            if stamp.utcoffset() is None:
                raise ValueError('enrichment scheduling clock invalid')
            if stamp > cutoff:
                continue
            identity = (scheduling['symbol'], scheduling['financial_period'])
            if identity not in history or history[identity] < stamp:
                history[identity] = stamp
        return history

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
