from decimal import Decimal
from value_investment_agent.candidate_review import cashflow_secondary


def row(source, value='10', scope=None):
    return {'source_name':source,'value':value,'unit':'CNY','metadata':{'statement_scope':scope}}


ABSTRACT = 'AkShare / Sina financial abstract'
DETAIL = 'AkShare / Sina detailed financial statements'


def test_selects_scoped_statement_after_newer_agreeing_abstract():
    statement = row(DETAIL, scope='consolidated')
    assert cashflow_secondary([row(ABSTRACT),statement], Decimal('10'), 'CNY') is statement


def test_abstract_alone_cannot_prove_scope():
    assert cashflow_secondary([row(ABSTRACT)], Decimal('10'), 'CNY') is None


def test_newer_unscoped_statement_cannot_fall_back_to_old_scoped_one():
    assert cashflow_secondary([row(DETAIL),row(DETAIL,scope='consolidated')], Decimal('10'), 'CNY') is None


def test_conflicting_latest_abstract_still_blocks():
    assert cashflow_secondary([row(ABSTRACT,'12'),row(DETAIL,scope='consolidated')], Decimal('10'), 'CNY') is None
