from hashlib import sha256

import pytest

from value_investment_agent.application.product.source_bound_inputs import verify_package_local_sources


def source(tmp_path):
    path = tmp_path / 'issuer.pdf'
    path.write_bytes(b'synthetic issuer original')
    return {'id': 'synthetic-official', 'location': 'https://static.cninfo.com.cn/test.pdf',
        'local_path': 'issuer.pdf', 'sha256': sha256(path.read_bytes()).hexdigest()}


def test_source_url_remains_distinct_from_verified_local_original(tmp_path):
    row = source(tmp_path)
    verified = verify_package_local_sources(tmp_path, {'sources': [row]})
    assert verified == ((tmp_path / 'issuer.pdf', row['sha256']),)
    assert row['location'].startswith('https://')


def test_source_byte_change_cannot_be_hidden_by_matching_metadata(tmp_path):
    row = source(tmp_path)
    (tmp_path / 'issuer.pdf').write_bytes(b'changed original')
    with pytest.raises(ValueError, match='hash mismatch'):
        verify_package_local_sources(tmp_path, {'sources': [row]})


def test_source_bound_package_requires_all_sources_to_be_locally_bound(tmp_path):
    row = source(tmp_path)
    with pytest.raises(ValueError, match='every source'):
        verify_package_local_sources(tmp_path, {'sources': [row, {'id': 'missing-original'}]})


def test_duplicate_source_ids_are_rejected(tmp_path):
    row = source(tmp_path)
    with pytest.raises(ValueError, match='unique'):
        verify_package_local_sources(tmp_path, {'sources': [row, row]})


def test_source_binding_cannot_escape_the_project(tmp_path):
    row = source(tmp_path)
    row['local_path'] = '../outside.pdf'
    with pytest.raises(ValueError, match='root'):
        verify_package_local_sources(tmp_path, {'sources': [row]})


def test_legacy_descriptors_are_not_claimed_as_locally_verified(tmp_path):
    assert verify_package_local_sources(tmp_path, {'sources': [
        {'id': 'legacy', 'location': 'https://static.cninfo.com.cn/test.pdf', 'sha256': 'a' * 64}
    ]}) == ()
