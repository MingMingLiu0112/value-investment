import json
import pytest

from value_investment_agent.application.research.agent_review import operating_horizon_transport_admission_v1 as mod


def test_only_one_extra_closing_brace_is_normalized_without_rewriting_object():
    raw = '{"z":[1,{"x":"y"}]}}'
    normalized = mod.normalize_one_extra_closing_brace(raw)
    assert normalized == '{"z":[1,{"x":"y"}]}'
    assert json.loads(normalized) == {"z": [1, {"x": "y"}]}


@pytest.mark.parametrize("raw", [
    '{"z":1}',
    '{"z":1}}}',
    '{"z":1} trailing',
    'prefix {"z":1}}',
    '{"z":1,"z":2}}',
    '{"z":NaN}}',
])
def test_other_transport_shapes_fail_closed(raw):
    with pytest.raises(ValueError):
        mod.normalize_one_extra_closing_brace(raw)
