import ast
import inspect

from value_investment_agent.institution_metrics import collect_institution_metrics


def test_institution_report_selection_excludes_rejected_before_latest_selection():
    tree = ast.parse(inspect.getsource(collect_institution_metrics))
    statements = [node.value for node in ast.walk(tree)
                  if isinstance(node, ast.Constant) and isinstance(node.value, str)
                  and 'SELECT DISTINCT ON(o.symbol)' in node.value]
    assert len(statements) == 1
    sql = statements[0]
    assert "AND o.review_status <> 'rejected'" in " ".join(sql.split())
    assert sql.index("o.review_status <> 'rejected'") < sql.index('ORDER BY')
    assert 'AND o.symbol IN' in sql
