import ast
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize('state,allowed', [
    ('inactive', True), ('failed', True), ('active', False),
    ('activating', False), ('deactivating', False), ('', False),
])
def test_deployment_checks_whole_service_not_only_current_container(state, allowed):
    path = Path(__file__).resolve().parents[1] / 'scripts/deploy_memory_refresh.py'
    tree = ast.parse(path.read_text(encoding='utf-8'))
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                    and n.name == 'require_idle_filing_service')
    commands = []

    def output(command, **kwargs):
        commands.append(command)
        return state + '\n'

    namespace = {'subprocess': SimpleNamespace(check_output=output)}
    exec(ast.unparse(function), namespace)
    if allowed:
        namespace[function.name]()
    else:
        with pytest.raises(RuntimeError, match='not idle'):
            namespace[function.name]()
    assert 'value-investment-agent-filings.service' in commands[0]
