import hashlib
import json
import pytest
from value_investment_agent.application.historical_validation import disclosed_metric_review as service


@pytest.mark.parametrize('fault', ['none', 'value', 'page', 'context', 'source', 'column'])
def test_transcribed_numeric_row_is_bound_without_financial_admission(tmp_path, monkeypatch, fault):
    pdf = tmp_path / 'source.pdf'
    pdf.write_bytes(b'original')
    binding = dict(path='source.pdf', sha256=hashlib.sha256(pdf.read_bytes()).hexdigest(),
                   source_url='https://example.test/annual.pdf')
    workbench = dict(symbol='600887', research={'source_records': [binding]})
    monkeypatch.setattr(service, 'load_existing_workbench_for_presentation', lambda **kwargs: workbench)
    monkeypatch.setattr(service, 'extract_pages', lambda _: ['2025 2024 CNY Revenue 100 90 11.11'])
    request = dict(schema_version='disclosed-metric-transcription-v1', action='no_order', symbol='600887',
        source_binding=dict(binding), rows=[dict(metric_name='revenue', physical_page=1, unit='CNY',
            row_label='Revenue', evidence_excerpt='Revenue 100 90 11.11', required_context=['2025 2024', 'CNY'],
            period_columns={'2025': 0, '2024': 1}, values_by_period={'2025': '100', '2024': '90'})])
    row = request['rows'][0]
    if fault == 'value': row['values_by_period']['2025'] = '101'
    if fault == 'page': row['physical_page'] = 2
    if fault == 'context': row['required_context'] = ['2023 2022']
    if fault == 'source': request['source_binding']['source_url'] = 'https://wrong.test/'
    if fault == 'column': row['period_columns']['2024'] = 0
    path = tmp_path / 'input.json'
    path.write_text(json.dumps(request), encoding='utf-8')
    args = dict(root=tmp_path, path=path, expected_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                workbench_path=tmp_path / 'workbench.json', workbench_sha256='a'*64)
    if fault != 'none':
        with pytest.raises(ValueError): service.review_disclosed_metrics(**args)
        return
    output = service.review_disclosed_metrics(**args)
    assert len(output['facts']) == 2
    assert output['facts'][0]['value'] == '100'
    assert not output['financial_gate_admitted']
    assert not output['forecast_assumptions_approved']
    assert not output['strict_pit_admitted']
    assert output['action'] == 'no_order'


def test_consolidated_context_can_continue_one_page_but_not_be_parent_scope(tmp_path, monkeypatch):
    pdf = tmp_path / 'source.pdf'
    pdf.write_bytes(b'original')
    binding = dict(path='source.pdf', sha256=hashlib.sha256(pdf.read_bytes()).hexdigest(), source_url='https://example.test/annual.pdf')
    monkeypatch.setattr(service, 'load_existing_workbench_for_presentation', lambda **kwargs:
                        dict(symbol='600887', research={'source_records': [binding]}))
    monkeypatch.setattr(service, 'extract_pages', lambda _: ['合并现金流量表 2025 2024 CNY', 'Cash capex 30 20'])
    request = dict(schema_version='disclosed-metric-transcription-v1', action='no_order', symbol='600887',
        source_binding=binding, rows=[dict(metric_name='cash_capex', physical_page=2, context_physical_pages=[1, 2],
            statement_scope='CONSOLIDATED', unit='CNY', row_label='Cash capex', evidence_excerpt='Cash capex 30 20',
            required_context=['2025 2024', 'CNY'], period_columns={'2025': 0, '2024': 1},
            values_by_period={'2025': '30', '2024': '20'})])
    path = tmp_path / 'request.json'
    def run():
        path.write_text(json.dumps(request), encoding='utf-8')
        return service.review_disclosed_metrics(root=tmp_path, path=path,
            expected_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            workbench_path=tmp_path / 'unused.json', workbench_sha256='a'*64)
    assert run()['facts'][0]['context_physical_pages'] == [1, 2]
    request['rows'][0]['statement_scope'] = 'PARENT'
    with pytest.raises(ValueError, match='scope missing'): run()
