import pytest
from value_investment_agent.financing_table import amount_from_fragments


@pytest.mark.parametrize('parts,expected',[
    (['9,929,420,31','9.26'],'9929420319.26'),
    (['82,634,482.1','8'],'82634482.18'),
    (['236,232,405.','55'],'236232405.55'),
    (['10.00'],'10.00'),
])
def test_layout_fragments_reconstruct_exact_amounts(parts,expected):
    assert amount_from_fragments(parts)==expected


@pytest.mark.parametrize('parts',[
    [],[''],['1,234.56','78'],['1,23','4,56.78'],['12','text'],
    ['12.','3'],['1','2','.00'],['NaN'],['12.00','-10.00'],
])
def test_ambiguous_missing_and_invalid_fragments_block(parts):
    assert amount_from_fragments(parts) is None
