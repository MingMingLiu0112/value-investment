from pathlib import Path

from value_investment_agent.backup import sha256_file


def test_sha256_file_is_stable(tmp_path: Path) -> None:
    file_path = tmp_path / 'sample.bin'
    file_path.write_bytes(b'agent backup')
    assert sha256_file(file_path) == sha256_file(file_path)
