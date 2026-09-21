from pathlib import Path


def test_capital_refresh_exposes_a_dated_window_start():
    script = (Path(__file__).parents[1] / "scripts" / "assess_moutai_current_capital_refresh.py").read_text(encoding="utf-8")
    assert 'parser.add_argument("--start", default="2026-09-14")' in script
    assert 'query.get("seDate") != args.start + "~" + args.through' in script
