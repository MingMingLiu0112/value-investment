"""Probe the actual mounted production gate with explicit synthetic evidence."""
import hashlib
from pathlib import Path
import sys

from value_investment_agent import financial_quality
from value_investment_agent.quality import accepted_verification


def check():
    assert hashlib.sha256(Path(financial_quality.__file__).read_bytes()).hexdigest() == sys.argv[1]
    point = {'field_name': 'interest_bearing_debt', 'validation_status': 'verified',
             'metadata': {'automatic_cross_source_verification': True}}
    assert not financial_quality._accepted(point)
    assert not accepted_verification(point)
    for flag in (None, False, 'true', 'false', 0, 1):
        point['metadata']['complete_debt_verified'] = flag
        assert not financial_quality._accepted(point)
    point['metadata']['complete_debt_verified'] = True
    assert accepted_verification(point)
    point['metadata']['evidence_quarantine'] = True
    assert not accepted_verification(point)
    del point['metadata']['evidence_quarantine']
    point['metadata']['automatic_cross_source_verification'] = False
    assert not accepted_verification(point)
    point['metadata']['automatic_cross_source_verification'] = True
    point['metadata']['derivation_formula'] = (
        'short_term_borrowings + current_portion_long_term_debt + long_term_borrowings + bonds_payable')
    assert not accepted_verification(point)
    point['field_name'] = 'debt_ratio'
    del point['metadata']['complete_debt_verified']
    assert accepted_verification(point)
    print('Installed hash and explicit-scope gates passed; synthetic inputs only')


if __name__ == '__main__':
    check()
