from value_investment_agent.evidence_dependencies import affected_point_ids


def point(id, field='revenue', source='pdf', metadata=None, symbol='000333'):
    return dict(data_point_id=id, field_name=field, source_id=source,
                metadata=metadata or {}, symbol=symbol, period_label='2025-12-31')


def test_transitive_verification_and_derived_dependencies():
    rows = [point('bad', source='secondary'),
            point('official', metadata={'secondary_data_point_id':'bad'}),
            point('margin', field='net_margin', source='derived',
                  metadata={'input_source_ids':{'revenue':'pdf'}}),
            point('downstream', field='score', source='score',
                  metadata={'input_source_ids':{'net_margin':'derived'}})]
    assert affected_point_ids(rows, ['bad']) == {'bad','official','margin','downstream'}


def test_shared_pdf_other_fields_and_other_symbols_are_not_invalidated():
    rows = [point('bad'),
            point('cash_ratio', field='cash_ratio', metadata={'input_source_ids':{'cash':'pdf'}}),
            point('other_company', symbol='600519', metadata={'input_source_ids':{'revenue':'pdf'}})]
    assert affected_point_ids(rows, ['bad']) == {'bad'}


def test_repaired_source_alias_and_explicit_input_period():
    rows = [point('bad', source='new', metadata={'provenance_repair':{'previous_source_id':'old'}}),
            point('ratio', field='net_margin', metadata={'input_facts':{
                'revenue':{'source_id':'old','period':'2025-12-31'}}}),
            point('other_year', field='net_margin', metadata={'input_facts':{
                'revenue':{'source_id':'old','period':'2024-12-31'}}})]
    assert affected_point_ids(rows, ['bad']) == {'bad','ratio'}


def test_exact_fact_id_distinguishes_reverified_input_in_same_document():
    rows = [point('bad'), point('good'),
            point('old_ratio', field='net_margin', metadata={'input_facts': {
                'revenue': {'source_id': 'pdf', 'data_point_id': 'bad'}}}),
            point('new_ratio', field='net_margin', metadata={'input_facts': {
                'revenue': {'source_id': 'pdf', 'data_point_id': 'good'}}})]
    assert affected_point_ids(rows, ['bad']) == {'bad', 'old_ratio'}
    assert affected_point_ids(rows, ['good']) == {'good', 'new_ratio'}
