"""Synthetic orchestration fixtures, not real-company admission evidence."""
import json

import pytest

from value_investment_agent.application.product.common import sha256_file
from value_investment_agent.application.product.daily_batch import run_daily_batch, previous_case_from_run


def test_failed_company_does_not_hide_independent_company(tmp_path):
    def run_case(**kwargs):
        if kwargs["symbol"] == "000651":
            raise ValueError("source fingerprint changed")
        directory = kwargs["output_dir"]
        directory.mkdir()
        receipt = {"status": "RESEARCH_RUN_COMPLETED_WITH_ADMISSION_STATUS", "symbol": "600519",
                   "recommendation_type": "NO_ACTION", "research_as_of": "2026-10-08",
                   "quote_check": {"status": "QUOTE_VERIFIED_BUT_RESEARCH_STALE", "quote_date": "2026-10-09"},
                   "outputs": {}}
        (directory / "receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
        return receipt
    result = run_daily_batch(root=tmp_path, cases={"000651": {}, "600519": {}},
        symbols=["000651", "600519"], output_dir=tmp_path / "runtime/run", run_case=run_case)
    assert result["failed_case_count"] == 1
    assert result["cases"][1]["quote_date"] == "2026-10-09"
    assert result["action"] == "no_order"
    assert result["canonical_workbook_written"] is False
    assert (tmp_path / "runtime/run/batch-report.md").is_file()


def test_previous_run_requires_its_own_unchanged_workbench(tmp_path):
    folder = tmp_path / "runtime/previous/600519"
    folder.mkdir(parents=True)
    workbench = folder / "workbench.json"
    workbench.write_text("{}", encoding="utf-8")
    receipt = {"symbol": "600519", "action": "no_order", "canonical_workbook_written": False,
               "outputs": {"workbench": {"path": workbench.relative_to(tmp_path).as_posix(), "sha256": sha256_file(workbench)}}}
    (folder / "receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
    result = previous_case_from_run(root=tmp_path, case={}, previous_run=folder.parent, symbol="600519")
    assert result["previous_workbench_sha256"] == sha256_file(workbench)
    workbench.write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        previous_case_from_run(root=tmp_path, case={}, previous_run=folder.parent, symbol="600519")


def test_daily_batch_refuses_overwrite_and_duplicate_selection(tmp_path):
    folder = tmp_path / "runtime/run"
    folder.mkdir(parents=True)
    with pytest.raises(FileExistsError):
        run_daily_batch(root=tmp_path, cases={}, symbols=[], output_dir=folder, run_case=None)
    with pytest.raises(ValueError, match="distinct registered"):
        run_daily_batch(root=tmp_path, cases={"600519": {}}, symbols=["600519", "600519"],
                        output_dir=tmp_path / "runtime/new", run_case=None)
def test_new_registered_company_without_prior_batch_row_remains_runnable(tmp_path):
    import json
    from value_investment_agent.application.product.daily_batch import previous_case_from_run
    prior=tmp_path/'runtime/previous'; prior.mkdir(parents=True)
    (prior/'batch-receipt.json').write_text(json.dumps({'action':'no_order',
        'canonical_workbook_written':False,'cases':[{'symbol':'600519'}]}),encoding='utf-8')
    case={'package':'registered.json'}
    assert previous_case_from_run(root=tmp_path,case=case,previous_run=prior,symbol='600887')==case
