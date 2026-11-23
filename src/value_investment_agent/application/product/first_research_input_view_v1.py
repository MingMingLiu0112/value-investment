"""Read/recompile one explicitly registered first input using the existing engine."""
from datetime import datetime
from decimal import Decimal
import json
import re

from ..research.first_research_input_v1 import replay_first_research_input
from ..research.first_input_parent_cash_observation_v2 import observe_first_input_parent_cash_by_source
from ..research.agent_review.web_research import _binding, _raw, MAX_JSON, _json

REGISTRY="config/current-first-research-inputs-v1.json"
SCHEMA="current-first-research-inputs-v1"


def read_first_research_input(*,root,symbol,now:datetime):
    base=dict(schema_version="first-research-input-view-v1",symbol=symbol,action="no_order",
        formal_eligibility=False,main_range_adopted=False,main_valuation_range=None,
        scope="CONDITIONAL_STRESS_RESEARCH_NOT_ADOPTED_MAIN_RANGE",
        current_price=None,condition_price=None,personal_quantity=None,
        user_acceptance="NOT_CONFIRMED",status="NOT_STARTED",
        reason="FIRST_INPUT_NOT_REGISTERED")
    if re.fullmatch(r"[0-9]{6}",symbol) is None:
        raise ValueError("Invalid first-research symbol")
    path=root/REGISTRY
    if not path.exists():
        return base
    try:
        registry=_json(_raw(path,64*1024))
        if (set(registry)!={"schema_version","action","cases"}
                or registry["schema_version"]!=SCHEMA or registry["action"]!="no_order"
                or not isinstance(registry["cases"],dict)):
            raise ValueError("First-input registry contract mismatch")
        entry=registry["cases"].get(symbol)
        if entry is None:return base
        if not isinstance(entry,dict) or set(entry)!={"receipt"}:
            raise ValueError("First-input registry entry invalid")
        ref=entry["receipt"]
        receipt_path=_binding(root,ref)
        import hashlib
        raw=_raw(receipt_path,MAX_JSON)
        if hashlib.sha256(raw).hexdigest()!=ref["sha256"]:
            raise ValueError("First-input receipt changed")
        receipt=_json(raw)
        if receipt.get("symbol")!=symbol or receipt.get("action")!="no_order":
            raise ValueError("First-input receipt issuer mismatch")
        if receipt.get("schema_version") == "parent-remaining-year-successor-receipt-v1":
            from .parent_remaining_year_successor_view import read_parent_remaining_year_successor_view
            return read_parent_remaining_year_successor_view(
                root=root, receipt_binding=ref, symbol=symbol, now=now)
        if receipt.get("schema_version") == "parent-owner-distribution-successor-receipt-v2":
            from .parent_owner_distribution_successor_view_v2 import (
                read_parent_owner_distribution_successor_view,
            )
            return read_parent_owner_distribution_successor_view(
                root=root, receipt_binding=ref, symbol=symbol, now=now)
        if receipt.get("schema_version") == "direct-owner-cash-first-input-receipt-v1":
            for binding in receipt.get("source_bindings",[]):
                _binding(root,binding,runtime_only=False)
            for key in ("spec_binding","result_binding"):
                _binding(root,receipt[key])
            from .direct_owner_cash_view_v1 import read_direct_owner_cash_view
            return read_direct_owner_cash_view(root=root,receipt_binding=ref,now=now)
        if receipt.get("schema_version") not in {
                "first-research-input-receipt-v1", "first-research-input-receipt-v2"}:
            raise ValueError("FIRST_INPUT_RECEIPT_SCHEMA_UNSUPPORTED")
        # Public reads do not expose arbitrary local paths or private inputs.
        for binding in receipt.get("source_bindings",[]):
            _binding(root,binding,runtime_only=False)
        for key in ("spec_binding","package_binding","proposal_binding"):
            _binding(root,receipt[key],runtime_only=key!="spec_binding")
        if receipt.get("schema_version") == "first-research-input-receipt-v2":
            from ..research.first_research_input_v2 import replay_first_research_input_v2
            result=replay_first_research_input_v2(root=root,receipt_binding=ref,now=now)
        elif receipt.get("schema_version") == "first-research-input-receipt-v1":
            result=replay_first_research_input(root=root,receipt_binding=ref,now=now)
        else:
            raise ValueError("FIRST_INPUT_RECEIPT_SCHEMA_UNSUPPORTED")
        def bound_json(binding):
            target=_binding(root,binding,runtime_only=False)
            data=_raw(target,MAX_JSON)
            if hashlib.sha256(data).hexdigest()!=binding["sha256"]:
                raise ValueError("First-input consumed source changed after replay")
            return _json(data)
        package=bound_json(receipt["package_binding"])
        spec=bound_json(receipt["spec_binding"])
        assumptions=bound_json(spec["assumption_binding"])
        native=bound_json(spec["native_facts_binding"])
        parent_cash=observe_first_input_parent_cash_by_source(root=root,
            native_facts_binding=spec["native_facts_binding"],now=now)
        from ..research.quarter_financial_read_model_v1 import read_quarter_financial_ocr
        from ..research.quarter_income_facts_v2 import read_quarter_income_facts
        from ..research.first_research_financial_update_v1 import compare_first_input_financial_update
        financial_update=compare_first_input_financial_update(symbol=symbol,
            financial_basis=native["financial_basis"],native_facts=native,
            q3_read_model=read_quarter_financial_ocr(root,symbol,now),
            income_read_model=read_quarter_income_facts(root,symbol,now))
        if parent_cash.get("symbol") != symbol or parent_cash.get("action") != "no_order":
            raise ValueError("Parent cash observation issuer boundary changed")
        if (result["research_case"]["symbol"]!=symbol or result["action"]!="no_order"
                or result["formal_eligibility"] is not False or result["main_range_adopted"] is not False):
            raise ValueError("First-input result changes formal research boundaries")
        # Reuse the exact fact consumed by the cold compiler, not the latest
        # reported share count or an independently rounded balance-sheet line.
        share_id=spec["capital_bindings"]["ordinary_shares"]
        share_fact,=(row for row in native["facts"] if row["id"]==share_id)
        share_source,=(row for row in native["sources"] if row["id"]==share_fact["source_id"])
        opening_capital=dict(
            shares=share_fact["value"], share_basis=spec["share_basis"],
            period_end=share_fact["period_end"], fact_id=share_id,
            physical_page=share_fact["physical_page"],
            source_url=share_source.get("source_url"), source_sha256=share_source["sha256"],
        )
        view = dict(base,status="SOURCE_BOUND_FIRST_INPUT_COMPILED",reason=None,
            input_descriptor_sha256=result["input_descriptor_sha256"],
            opening_capital=opening_capital,
            input_fingerprint=result["input_fingerprint"],receipt_binding=ref,
            financial_basis=result["research_case"]["financial_period"],
            research_as_of=result["research_case"]["as_of"],
            input_computed_at=spec["point_in_time"]["computed_at"],
            research_case=result["research_case"],valuation=result["valuation"],
            valuation_status=result["valuation_status"],annual_ledgers=result["annual_ledgers"],
            blockers=result["blockers"],source_bindings=result["source_bindings"],
            compilation_scope=result["compilation_scope"],scenario_label_scope=result["scenario_label_scope"],
            sources=package["sources"],operating_assumptions=assumptions,
            native_fact_count=len(native["facts"]),
            parent_cash_observation=parent_cash,
            financial_update_observation=financial_update,
            source_review="NATIVE_FACT_ROWS_COLD_REPLAYED_NOT_ECONOMIC_APPROVAL",
            investment_conclusion="PRIMARY_RANGE_REJECTED_CONDITIONAL_PRESSURE_RESEARCH_ONLY")
        from ..research.pending_candidate_alignment import (
            _load_bound_alignment,
            candidate_alignment_config_path,
        )

        if not candidate_alignment_config_path(root, ref["sha256"]).is_file():
            return view

        analysis = dict(
            status="CONDITIONAL_ANALYSIS_VERIFIED", arithmetic_complete=True, action="no_order",
            symbol=symbol, valuation_date=view["financial_basis"], research_as_of=view["research_as_of"],
            valuation=view["valuation"], input_descriptor_sha256=view["input_descriptor_sha256"],
            review_binding=dict(candidate_binding=ref, package_binding=receipt["package_binding"]),
            source_bindings=result["source_bindings"],
            consumed_operating_inputs=dict(ordinary_shares=share_fact["value"]),
            joint_capital_review=dict(economic_path=dict(currency=next(iter(package["facts"]["scenario_inputs"].values()))["currency"])),
            official_fact_anchors=[dict(field="ordinary_shares", source_id=share_fact["source_id"],
                source_value=share_fact["value"], unit=share_fact["unit"], period_end=share_fact["period_end"])],
            source_catalog=[dict(kind="official_issuer_filing",
                issuer_identity=dict(security_code=symbol), local_path=share_source["path"],
                sha256=share_source["sha256"], location=share_source["source_url"],
                source_available_at=share_source["available_at"])],
            consumed_opening_capital_excerpt=dict(
                binding={key: share_source[key] for key in ("path", "sha256")},
                source_url=share_source["source_url"], available_at=share_source["available_at"],
                physical_page=share_fact["physical_page"], excerpt=share_fact["excerpt"],
                period_end=share_fact["period_end"]),
            opening_capital_original=({key: share_source[key] for key in ("path", "sha256")}
                if share_source.get("path") else None),
        )
        view["pending_candidate_alignment"] = _load_bound_alignment(
            root=root, analysis=analysis, now=now, input_schema="first-research-input-alignment-input-v1")
        alignment = view["pending_candidate_alignment"]
        if financial_update is None:
            from ..research.first_research_financial_update_v1 import compare_aligned_quarter_update

            view["financial_update_observation"] = compare_aligned_quarter_update(
                symbol=symbol, financial_basis=native["financial_basis"],
                native_facts=native, alignment=alignment)

        for check in alignment["checks"]:
            reconciliation = check["details"].get("reconciliation") or {}
            payable = reconciliation.get("opening_parent_dividend_payable")
            if not payable or check["id"] != "distributions":
                continue
            original = payable["original_binding"]
            reported_source = any(
                source.get("sha256") == original["sha256"]
                and source.get("report_period") == view["financial_basis"]
                for source in parent_cash.get("source_bindings", ())
            )
            balance = next((row["balances"][0].get("closing_cash_and_equivalents_cny")
                for row in parent_cash.get("periods", ())
                if row.get("report_period") == view["financial_basis"] and row.get("balances")), None)
            if not reported_source or balance is None:
                continue
            residual = Decimal(balance) - Decimal(payable["parent_dividend_payable_cny"])
            ledgers = result["annual_ledgers"]
            if residual >= 0 and set(ledgers) == {"bear", "base", "bull"} and all(
                Decimal(ledger["rows"][0]["opening_cash"]) == residual for ledger in ledgers.values()
            ):
                payable["conditional_opening_cash_match"] = dict(
                    reported_parent_cash_cny=str(balance), model_opening_cash_cny=str(residual),
                    scope="CONDITIONAL_NET_CASH_MATCH_NOT_PAYMENT_PROOF", action="no_order",
                )
        return view
    except (ValueError,OSError,KeyError,TypeError,OverflowError) as error:
        return dict(base,status="UNASSESSABLE",reason=str(error))
