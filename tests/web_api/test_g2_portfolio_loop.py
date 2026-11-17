"""Run the inherited full-loop rehearsal entirely in repository .tmp storage."""
import pytest

from test_web_first_private_full_loop import test_web_first_single_private_account_full_loop
from value_investment_agent.presentation.web_api import private_routes


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    project = tmp_path / "TEST_ONLY-public-project"
    private = tmp_path / "TEST_ONLY-private"
    project.mkdir()
    private.mkdir()
    journal = private / "portfolio/journal.jsonl"
    # Only storage location is injected: production private-root guards stay intact.
    monkeypatch.setattr(private_routes, "resolve_private_root", lambda **kwargs: journal)
    yield project, private
