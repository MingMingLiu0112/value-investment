# Thesis risk branch correction

The reproduced flat-position counterexample (P=70, V=100, thesis_intact=False)
now returns watch/no_order instead of proposed_entry. Unknown and broken thesis
reasons remain visible even when price, model, execution or session readiness
blocks action. A held position with a broken thesis retains proposed_exit_review;
this does not create a fill or bypass execution constraints.

Validation: runtime/venv/Scripts/python.exe -m pytest
tests/test_simulation_state.py tests/test_moutai_paper_decisions.py
tests/test_virtual_account.py -q --basetemp runtime/pytest-thesis-risk-20260912

Result: 40 passed. The risk matrix covers flat/held positions, broken/unknown
theses and unavailable price, model, execution or trading session inputs.
This is synthetic behavior and downstream regression evidence, not historical
strategy performance or model admission. No production deployment or workbook
publication was performed. P1 model applicability and P2/P3 integration remain
open; this change alone does not establish R1 or R2 readiness.
