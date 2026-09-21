from contextlib import contextmanager
from types import SimpleNamespace
import json
import pytest

from value_investment_agent import cli


@pytest.mark.parametrize('failed_names', [{'bad'}, {'good', 'bad', 'last'}, set()])
def test_later_failure_cannot_erase_prior_report(monkeypatch, capsys, failed_names):
    class Connection:
        def __init__(self):
            self.pending = []
            self.persisted = []

        def commit(self):
            self.persisted.extend(self.pending)
            self.pending.clear()

        def rollback(self):
            self.pending.clear()

    db = Connection()

    @contextmanager
    def connect(_):
        yield db
        db.commit()

    monkeypatch.setattr(cli, 'connect', connect)
    monkeypatch.setattr(cli, 'get_settings', lambda: SimpleNamespace(database_url='test'))
    monkeypatch.setattr(cli, 'begin_run', lambda *args: 'run')
    monkeypatch.setattr(cli, 'claim_disclosures_for_extraction', lambda *args: [
        dict(disclosure_id=name, local_path=name, sha256='hash')
        for name in ['good', 'bad', 'last']])

    def extract(path):
        if str(path) in failed_names:
            raise ValueError('Invalid PDF')
        return dict(sha256='hash', candidates=[{'value': 1}])

    def store(connection, ident, candidates):
        connection.pending.append(('candidate', ident))
        return len(candidates)

    def finish(connection, ident, count=0, error=None):
        connection.pending.append(('failed' if error else 'extracted', ident))

    runs = []
    monkeypatch.setattr(cli, 'extract_candidates', extract)
    monkeypatch.setattr(cli, 'store_filing_candidates', store)
    monkeypatch.setattr(cli, 'finish_disclosure_extraction', finish)
    monkeypatch.setattr(cli, 'end_run', lambda *args: runs.append((args[-2], args[-1])))
    if failed_names:
        with pytest.raises(SystemExit) as error:
            cli.extract_filing_candidates_batch(3)
        assert error.value.code == 1
    else:
        cli.extract_filing_candidates_batch(3)
    expected = []
    for name in ['good', 'bad', 'last']:
        expected.extend([('failed', name)] if name in failed_names else
                        [('candidate', name), ('extracted', name)])
    assert db.persisted == expected
    status = 'failed' if failed_names else 'succeeded'
    summary = dict(requested=3, candidates_stored=3-len(failed_names), failed=len(failed_names))
    assert runs == [(status, summary)]
    assert json.loads(capsys.readouterr().out) == {'status': status, **summary}
