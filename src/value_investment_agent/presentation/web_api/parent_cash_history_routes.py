"""Bounded, read-only projection of existing parent cash task checkpoints."""
import re
import logging
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from itertools import islice
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, Request
from starlette.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from ...application.research.parent_cash_task_completion_v1 import (
    _case_entry, registered_cash_task_spec, run_and_seal_parent_cash_task, seal_completed_parent_cash_task,
    valuation_receipt_path,
    preflight_parent_cash_task, read_valuation_publication, valuation_blockage_path,
)
from ...application.portfolio.private_journal_lock import LockTimeout
from .live_operating_research_routes import resolve_research_task_root
from . import parent_cash_funding_revisions as funding
from .local_auth import authorize, LocalAuthorizationError, AUTHORIZATION_REQUIRED
from ...application.research.agent_review.parent_cash_task_v2 import ParentCashTaskServiceV2, STAGE_ORDER
from ...application.research.agent_review.parent_cash_task_v3 import ParentCashTaskServiceV3


def _numbered_task_with_observed_investing_cash(service, task_id):
    task = service.read(task_id)
    if "spec_binding" not in task or task.get("error_code") in {
            "PARENT_IMPLEMENTATION_CHANGED_REPLAY_REQUIRED", "PARENT_SOURCE_OR_CHECKPOINT_INVALID"}:
        return task

    from ...application.research.direct_owner_cash_staged_v3 import _load_spec
    from ...application.research.parent_direct_owner_cash_sources import read_parent_direct_owner_cash_sources

    spec = _load_spec(service.root, task["spec_binding"])
    source = spec.get("quarterly_financing_source")
    if source is None:
        return task
    try:
        year = date.fromisoformat(spec["valuation_date"]).year + 1
        period_end = f"{year}-09-30"
        statement = read_parent_direct_owner_cash_sources(
            root=service.root, symbol=spec["symbol"], issuer_name=spec["issuer_name"],
            sources=[dict(path=source["path"], sha256=source["sha256"], period_end=period_end,
                          available_at=source["acquired_at"])],
            evaluated_at=datetime.now(timezone.utc),
        )["statements"][0]
        fields = statement["cash_flow"]
        proceeds = fields["investment_recovery_cash_cny"]
        payments = fields["investment_paid_cny"]
        income = fields["investment_income_cash_cny"]
        task["observed_investing_cash"] = dict(
            classification="HISTORICAL_STANDALONE_NOT_FORECAST",
            period_end=period_end, currency="CNY",
            recovered_cny=proceeds["current"], invested_cny=payments["current"],
            net_principal_cash_cny=str(Decimal(proceeds["current"]) - Decimal(payments["current"])),
            cash_investment_income_cny=income["current"],
            source_binding=statement["source_binding"],
            physical_pages=sorted({row["physical_page"] for row in (proceeds, payments, income)}),
        )
        if statement["checks"]["cash_statement_reconciled"]:
            task["observed_investing_cash"]["reconciled_ytd_cash"] = {
                key: fields[key]["current"]
                for key in (
                    "opening_cash_and_equivalents_cny", "cfo_cny", "cfi_cny",
                    "cff_cny", "fx_cny", "closing_cash_and_equivalents_cny",
                )
            }
    except (ValueError, TypeError, KeyError, OSError, ArithmeticError):
        task["observed_investing_cash"] = dict(classification="SOURCE_NOT_REPLAYABLE")
    return task


def _comparison_quote(alignment):
    if (alignment.get("status") != "ALIGNED_FOR_RESEARCH_COMPARISON"
            or alignment.get("currentpricecomparison") is not True):
        return None
    quote = _qualified_close(alignment)
    if quote is None:
        raise ValueError("PARENT_TASK_ALIGNMENT_QUOTE_INVALID")
    return quote


def _qualified_close(alignment):
    quote = alignment.get("quote")
    if not quote or quote.get("status") != "QUALIFIED":
        return None
    session = quote["quote_date"]
    amount = Decimal(quote["current_price"])
    if (session != quote["latest_completed_session"]
            or date.fromisoformat(session).isoformat() != session
            or not amount.is_finite() or amount <= 0):
        raise ValueError("PARENT_TASK_ALIGNMENT_QUOTE_INVALID")
    return dict(trade_date=session, close_cny=str(amount))



def _settled_base_policy(service, predecessor, prior):
    response = prior.get("responses", {}).get("base.policy")
    if not isinstance(response, dict):
        return False
    match = re.fullmatch(
        r"runtime/research-task-execution-v1/parent-cash-task-v3/"
        r"(rt-[0-9a-f]{32})/response-([0-9a-f]{64})\.json", response.get("path", ""),
    )
    if match is None:
        return False
    owner, reservation = match.groups()
    state = prior
    if owner != predecessor:
        # read() has verified the inherited response against the seed lineage.
        if "base.policy" not in prior.get("reused_stages", ()):
            return False
        _, state, _ = service._load(owner)
        if (state["responses"].get("base.policy") != response
                and response not in state.get("returned_responses", ())):
            return False
    charge = state["reservations"].get(reservation)
    return (isinstance(charge, dict) and charge.get("scenario") == "base.policy"
            and charge.get("status") == "SETTLED")


def _read_debt_timing_sensitivity(root, task_id, symbol, head):
    """Read an explicitly registered, task-bound sensitivity without sealing a valuation."""
    from ...application.product.common import require_inside
    from ...application.research.direct_owner_cash_research_v1 import _bound, _read

    directory = root / "runtime" / "parent-cash-task-backed-receipts" / task_id
    path = require_inside(root / "runtime", directory / "debt-timing-sensitivity.json",
                          "debt timing sensitivity registration")
    if not path.is_file():
        return None
    try:
        if path.stat().st_size > 4096:
            raise ValueError("SENSITIVITY_REGISTRATION_TOO_LARGE")
        registration = json.loads(path.read_bytes())
        if (registration["symbol"] != symbol or registration["task_id"] != task_id
                or registration["task_head"] != head):
            raise ValueError("SENSITIVITY_TASK_IDENTITY_CHANGED")
        binding = registration["receipt_binding"]
        receipt = _read(root, binding)
        if (receipt["scope"] != "CONDITIONAL_SENSITIVITY_NOT_CURRENT_VALUATION"
                or receipt["action"] != "no_order"
                or receipt["f2_status"] != "NOT_EVALUATED_FOR_THIS_SENSITIVITY"):
            raise ValueError("SENSITIVITY_SCOPE_INVALID")
        cases = {}
        for name, case in receipt["cases"].items():
            result = case["result"]
            if "error" in result:
                cases[name] = {"status": "REJECTED", "reason": result["error"]}
            else:
                if result["formal_eligibility"] is not False or result["action"] != "no_order":
                    raise ValueError("SENSITIVITY_RESULT_SCOPE_INVALID")
                value = Decimal(result["per_share_value"])
                if not value.is_finite() or value < 0:
                    raise ValueError("SENSITIVITY_VALUE_INVALID")
                annual_cash = [
                    {
                        "year": row["year"],
                        "debt_repayment_cny": row["cash_policy"]["debt_repayment"],
                        "cash_distribution_limit_cny": row["cash_distribution_limit_cny"],
                        "total_owner_distribution_cny": row["total_owner_distribution_cny"],
                        "closing_cash_cny": row["closing_cash_cny"],
                        "closing_debt_cny": row["closing_debt_cny"],
                    }
                    for row in result.get("annual_rows", [])
                ]
                cases[name] = {
                    "status": "CALCULATED", "per_share_value": str(value),
                    "annual_cash": annual_cash,
                }
        base = {"status": "VERIFIED_CONDITIONAL_SENSITIVITY", "cases": cases,
                "receipt_sha256": binding["sha256"], "f2_status": receipt["f2_status"],
                "valuation_basis": receipt["valuation_basis"]}
    except (OSError, ValueError, TypeError, KeyError, ArithmeticError):
        return {"status": "SENSITIVITY_UNAVAILABLE"}

    payout_registration = directory / "payout-stress.json"
    try:
        payout_registration = require_inside(directory, payout_registration, "payout stress registration")
        if not payout_registration.exists():
            return base
        if payout_registration.stat().st_size > 4096:
            raise ValueError("PAYOUT_STRESS_REGISTRATION_TOO_LARGE")
        successor = json.loads(payout_registration.read_bytes())
        if (successor["schema_version"] != "yili-interim-payout-stress-registration-v1"
                or successor["task_id"] != task_id or successor["symbol"] != symbol
                or successor["task_head"] != head or successor["parent_receipt_binding"] != binding):
            raise ValueError("PAYOUT_STRESS_IDENTITY_CHANGED")
        payout_binding = successor["receipt_binding"]
        require_inside(directory, root / payout_binding["path"], "payout stress receipt")
        payout = _read(root, payout_binding)
        if (payout["schema_version"] != "yili-interim-payout-stress-v1"
                or payout["scope"] != receipt["scope"] or payout["f2_status"] != receipt["f2_status"]
                or payout["valuation_basis"] != receipt["valuation_basis"]
                or payout["predecessor_binding"]["sha256"] != binding["sha256"]
                or payout["action"] != "no_order" or payout["formal_eligibility"] is not False):
            raise ValueError("PAYOUT_STRESS_SCOPE_INVALID")
        sources = successor["source_bindings"]
        if set(sources) != {"proposal", "resolution"} or set(payout["source_bindings"]) != set(sources):
            raise ValueError("PAYOUT_STRESS_SOURCE_SET_INVALID")
        for name, source in sources.items():
            if source["sha256"] != payout["source_bindings"][name]["sha256"]:
                raise ValueError("PAYOUT_STRESS_SOURCE_IDENTITY_CHANGED")
            require_inside(directory, root / source["path"], "payout stress original")
            _bound(root, source)
        assumption = payout["cash_assumption"]
        amount, year = assumption["gross_amount_cny"], assumption["year"]
        if (assumption["classification"] != "HYPOTHETICAL_OWNER_DISTRIBUTION_STRESS"
                or assumption["actual_payment_verified"] is not False
                or assumption["implementation_verified"] is not False
                or assumption["actual_payment_date"] is not None
                or assumption["actual_record_date"] is not None
                or type(year) is not int or year != 2027
                or not isinstance(amount, str) or not re.fullmatch(r"[0-9]{1,18}\.[0-9]{2}", amount)
                or Decimal(amount) <= 0 or set(payout["cases"]) != set(cases)):
            raise ValueError("PAYOUT_STRESS_ASSUMPTION_INVALID")
        rejected_years = {}
        for name, case in payout["cases"].items():
            error = case["result"].get("error")
            if error is None:
                if case["result"]["formal_eligibility"] is not False or case["result"]["action"] != "no_order":
                    raise ValueError("PAYOUT_STRESS_RESULT_SCOPE_INVALID")
                continue
            rejected = re.fullmatch(
                r"DIRECT_OWNER_(?:UNFUNDED_CASH_REQUIREMENT|SCHEDULED_DISTRIBUTION_REQUIRES_BORROWING_OR_CASH"
                r"|SCHEDULED_DISTRIBUTION_EXCEEDS_CAPACITY):([0-9]{4})", error,
            )
            if not rejected or int(rejected[1]) not in {row["year"] for row in case["years"]}:
                raise ValueError("PAYOUT_STRESS_REJECTION_INVALID")
            rejected_years[name] = int(rejected[1])
        base["payout_stress"] = dict(
            status="VERIFIED", amount_cny=amount, year=year, actual_payment_verified=False,
            receipt_sha256=payout_binding["sha256"], rejected_years=rejected_years,
        )
    except (OSError, ValueError, TypeError, KeyError, ArithmeticError):
        base["payout_stress"] = {"status": "UNAVAILABLE"}
    return base


def register_parent_cash_history_routes(api: FastAPI, *, project, sessions, port):
    root = resolve_research_task_root(project)
    service = ParentCashTaskServiceV2(root)
    numbered_service = ParentCashTaskServiceV3(root)
    # When execution uses a sibling worktree, retain read-only access to V3
    # history created in the code checkout. Writes and budget stay at root.
    code_root = Path(project).resolve()
    archived_numbered_service = (ParentCashTaskServiceV3(code_root)
                                 if code_root != Path(root).resolve() else None)

    def reply(value, status=200):
        return JSONResponse(value, status_code=status, headers={"Cache-Control": "no-store"})

    def denied(request):
        try:
            authorize(request, session=sessions, port=port)
        except LocalAuthorizationError as error:
            return reply({"action": "no_order", "status": error.code},
                         401 if error.code == AUTHORIZATION_REQUIRED else 403)
        return None

    def run_numbered(task_id, *, publication_only=False):
        try:
            execute = seal_completed_parent_cash_task if publication_only else run_and_seal_parent_cash_task
            execute(numbered_service, task_id)
        except (ValueError, KeyError, TypeError, OSError, ArithmeticError) as error:
            logging.getLogger(__name__).warning(
                "Parent cash valuation unavailable for %s (%s)", task_id,
                str(error) if re.fullmatch(r"[A-Z0-9_]{3,120}", str(error)) else type(error).__name__
            )

    @api.post("/api/v1/operating-research/parent-cash-tasks/v3")
    async def create_numbered(request: Request, background: BackgroundTasks):
        error = denied(request)
        if error is not None:
            return error
        return await run_in_threadpool(prepare_numbered, await request.body(), background)

    def prepare_numbered(raw, background):
        try:
            if len(raw) > 2048:
                raise ValueError("PARENT_V3_REQUEST_TOO_LARGE")
            body = json.loads(raw)
            if not isinstance(body, dict) or set(body) != {"spec_binding", "request_key"}:
                raise ValueError("PARENT_V3_REQUEST_INVALID")
            preflight_parent_cash_task(numbered_service, body["spec_binding"])
            task = numbered_service.create(**body)
            if task["status"] in {"QUEUED", "SUCCEEDED"}:
                background.add_task(run_numbered, task["task_id"])
            return reply(task, 202)
        except (ValueError, TypeError, KeyError, OSError, PermissionError) as exc:
            return reply({"action": "no_order", "status": "PARENT_V3_TASK_REJECTED",
                          "reason": str(exc)}, 422)

    @api.post("/api/v1/operating-research/parent-cash-tasks/by-company")
    async def create_numbered_for_company(request: Request, background: BackgroundTasks):
        error = denied(request)
        if error is not None:
            return error
        return await run_in_threadpool(prepare_numbered_for_company, await request.body(), background)

    def prepare_numbered_for_company(raw, background):
        try:
            if len(raw) > 128:
                raise ValueError("PARENT_V3_REQUEST_TOO_LARGE")
            body = json.loads(raw)
            if (not isinstance(body, dict) or set(body) not in ({"symbol"}, {"symbol", "continue_from_task_id"})
                    or not isinstance(body["symbol"], str)
                    or not re.fullmatch(r"[0-9]{6}", body["symbol"])):
                raise ValueError("PARENT_V3_REQUEST_INVALID")
            symbol = body["symbol"]
            binding = registered_cash_task_spec(numbered_service, symbol)
            if binding is None:
                return reply(dict(status="BLOCKED", reason="PARENT_V3_BOUND_COMPANY_INPUTS_MISSING",
                                  symbol=symbol, action="no_order"), 409)
            from hashlib import sha256
            if "continue_from_task_id" in body:
                predecessor = body["continue_from_task_id"]
                if not isinstance(predecessor, str) or not re.fullmatch(r"rt-[0-9a-f]{32}", predecessor):
                    raise ValueError("PARENT_V3_INVALID_CONTINUATION_TASK")
                prior = numbered_service.read(predecessor)
                if (prior.get("terminal_cash_review") == "RESEARCH_PAYOUT_V4"
                        and prior.get("error_code") == "BASE_TERMINAL_PARENT_DRAFT_TERM_SOURCE_INVALID"):
                    if prior.get("status") != "FAILED" or prior.get("spec_binding") != binding:
                        raise ValueError("PARENT_V3_CONTINUATION_NOT_AVAILABLE")
                    entry = _case_entry(Path(root).resolve(), binding)
                    plan = (entry or {}).get("gross_capex_plan_binding")
                    if plan is None:
                        return reply(dict(status="BLOCKED", reason="PARENT_V3_GROSS_CAPEX_PLAN_REQUIRED",
                                          symbol=symbol, action="no_order"), 409)
                    digest = sha256(json.dumps([predecessor, plan], sort_keys=True).encode()).hexdigest()
                    task = numbered_service.create(
                        spec_binding=binding, request_key="value-gross-capex-v1-" + digest[:48],
                        seed_task_id=predecessor, replay_from_stage="base.policy",
                        gross_capex_plan_binding=plan,
                    )
                    if task["status"] in {"QUEUED", "SUCCEEDED"}:
                        background.add_task(run_numbered, task["task_id"])
                    return reply(task, 202)
                if prior.get("terminal_cash_review") == "RESEARCH_PAYOUT_V4":
                    reservations = prior.get("reservations")
                    if (prior.get("status") != "FAILED" or prior.get("spec_binding") != binding
                            or prior.get("error_code") !=
                                "BASE_TERMINAL_PARENT_V3_NO_POSITIVE_SUPPORTED_TERMINAL_DISTRIBUTION"
                            or "base.policy" not in prior.get("completed_stages", ())
                            or Decimal(prior["reserved_cost"]) != 0
                            or not isinstance(reservations, dict)
                            or any(not isinstance(row, dict) or row.get("status") != "SETTLED"
                                   for row in reservations.values())
                            or not _settled_base_policy(numbered_service, predecessor, prior)):
                        raise ValueError("PARENT_V3_CONTINUATION_NOT_AVAILABLE")
                    digest = sha256(predecessor.encode()).hexdigest()
                    task = numbered_service.create(
                        spec_binding=binding, request_key="value-base-receipts-v1-" + digest[:54],
                        seed_task_id=predecessor, replay_from_stage="base.policy",
                    )
                    if task["status"] in {"QUEUED", "SUCCEEDED"}:
                        background.add_task(run_numbered, task["task_id"])
                    return reply(task, 202)
                if (prior.get("status") == "FAILED" and prior.get("spec_binding") == binding
                        and prior.get("error_code") in {
                            "PARENT_V3_ECONOMIC_DIRECT_INPUT_DATED_SHARE_FACT_REQUIRED",
                            "PARENT_V3_ECONOMIC_DIRECT_OWNER_NO_POSITIVE_SUPPORTED_TERMINAL_DISTRIBUTION",
                        }
                        and len(prior.get("completed_stages", ())) == 9
                        and all(row["status"] == "SETTLED" for row in prior.get("reservations", {}).values())):
                    digest = sha256(predecessor.encode()).hexdigest()
                    task = numbered_service.create(
                        spec_binding=binding, request_key="value-payout-review-v3-" + digest[:54],
                        seed_task_id=predecessor, replay_from_stage="base.terminal",
                    )
                    if task["status"] in {"QUEUED", "SUCCEEDED"}:
                        background.add_task(run_numbered, task["task_id"])
                    return reply(task, 202)
                if (prior.get("status") == "FAILED" and prior.get("spec_binding") == binding
                        and prior.get("terminal_cash_review") == "RESEARCH_PAYOUT_V3"
                        and prior.get("error_code") ==
                            "BASE_TERMINAL_PARENT_V3_NO_POSITIVE_SUPPORTED_TERMINAL_DISTRIBUTION"
                        and "base.policy" in prior.get("completed_stages", ())
                        and all(row["status"] == "SETTLED" for row in prior.get("reservations", {}).values())):
                    digest = sha256(predecessor.encode()).hexdigest()
                    task = numbered_service.create(
                        spec_binding=binding, request_key="value-payout-review-v4-" + digest[:54],
                        seed_task_id=predecessor, replay_from_stage="base.terminal",
                    )
                    if task["status"] in {"QUEUED", "SUCCEEDED"}:
                        background.add_task(run_numbered, task["task_id"])
                    return reply(task, 202)
                is_earnings_rebuild = prior.get("error_code") == (
                    "BASE_TERMINAL_PARENT_V3_UNSUPPORTED_STATIONARY_CASH_CONVERSION")
                if is_earnings_rebuild and prior.get("spec_binding") == binding:

                    entry = _case_entry(Path(numbered_service.root), binding) or {}
                    annual_pin = entry.get("terminal_parent_prior_annual_receipt")
                    if annual_pin is not None:
                        if (prior["status"] != "FAILED"
                                or "base.policy" not in prior.get("completed_stages", ())
                                or any(row["status"] == "RESERVED"
                                       for row in prior.get("reservations", {}).values())):
                            raise ValueError("PARENT_V3_CONTINUATION_NOT_AVAILABLE")
                        inputs = [binding, annual_pin]
                        if "terminal_parent_cash_method" in entry:
                            inputs.append(entry["terminal_parent_cash_method"])
                        digest = sha256(json.dumps(inputs, sort_keys=True)
                                        .encode("utf-8")).hexdigest()
                        task = numbered_service.create(
                            spec_binding=binding, request_key="value-cohort-" + digest[:60],
                            seed_task_id=predecessor, replay_from_stage="base.terminal",
                        )
                        if task["status"] in {"QUEUED", "SUCCEEDED"}:
                            background.add_task(run_numbered, task["task_id"])
                        return reply(task, 202)
                earnings_request_key = "value-earn1-" + binding["sha256"]
                earnings_task_id = "rt-" + sha256(
                    ("parent-cash-task-v3:" + earnings_request_key).encode()).hexdigest()[:32]
                is_financing_rebuild = (predecessor == earnings_task_id and prior.get("error_code") ==
                                        "BASE_POLICY_PARENT_V3_FORECAST_DEBT_NEGATIVE")
                financing_request_key = "value-earn2-" + binding["sha256"]
                financing_task_id = "rt-" + sha256(
                    ("parent-cash-task-v3:" + financing_request_key).encode()).hexdigest()[:32]
                rebuild_operating = is_earnings_rebuild and predecessor == financing_task_id
                cash_rebuild_key = "value-cash-rebuild-" + binding["sha256"][:60]
                cash_rebuild_id = "rt-" + sha256(
                    ("parent-cash-task-v3:" + cash_rebuild_key).encode()).hexdigest()[:32]
                rebuild_interest = predecessor == cash_rebuild_id and prior.get("error_code") in {
                    "BASE_POLICY_PARENT_DRAFT_REJECTED_OR_UNPUBLISHED",
                    "BASE_POLICY_PARENT_FINANCING_ABOVE_DISCLOSED_PROCEEDS:2026",
                }
                if (prior["status"] != "FAILED"
                        or prior.get("spec_binding") != binding
                        or (not is_earnings_rebuild and not is_financing_rebuild and not rebuild_interest
                            and prior.get("error_code") !=
                            "BASE_POLICY_PARENT_PROVIDER_OR_SETTLEMENT_AMBIGUOUS")
                        or "base.operating" not in prior.get("completed_stages", ())):
                    raise ValueError("PARENT_V3_CONTINUATION_NOT_AVAILABLE")
                reused = prior.get("reused_stages", ())
                if is_earnings_rebuild and (
                        "base.policy" not in prior.get("completed_stages", ())
                        or "base.operating" not in reused or "base.policy" in reused):
                    raise ValueError("PARENT_V3_CONTINUATION_NOT_AVAILABLE")
                key = ("value-interest1-" + binding["sha256"][:60] if rebuild_interest else
                       cash_rebuild_key if rebuild_operating else
                       financing_request_key if is_financing_rebuild else
                       earnings_request_key if is_earnings_rebuild else
                       "value-policy-recovery-" + sha256(predecessor.encode()).hexdigest()[:56])
                task = numbered_service.create(spec_binding=binding, request_key=key,
                    seed_task_id=predecessor,
                    replay_from_stage="base.operating" if rebuild_operating else "base.policy")
                if task["status"] in {"QUEUED", "SUCCEEDED"}:
                    background.add_task(run_numbered, task["task_id"])
                return reply(task, 202)
            request_key = "value-web-" + binding["sha256"]
            former_id = "rt-" + sha256(("parent-cash-task-v3:" + request_key)
                                       .encode("utf-8")).hexdigest()[:32]
            options = {}
            base = getattr(numbered_service, "base", None)
            if base is not None and (Path(base) / former_id / "input.json").is_file():
                former = numbered_service.read(former_id)
                if (former.get("status") == "RUNNING" and
                        "bear.policy" in former.get("completed_stages", ())):
                    try:
                        former = numbered_service.revalidate_interrupted_financing(former_id)
                    except LockTimeout:
                        return reply(former, 202)
                if (former.get("status") == "FAILED" and re.fullmatch(
                        r"BEAR_POLICY_PARENT_FINANCING_(?:ABOVE_DISCLOSED_PROCEEDS|BELOW_CONTRACTUAL_PRINCIPAL):20[0-9]{2}",
                        former.get("error_code") or "")):
                    request_key = "value-fin1-" + binding["sha256"]
                    options.update(seed_task_id=former_id, replay_from_stage="bear.policy")
                elif (former.get("status") == "FAILED"
                      and former.get("error_code") == "BEAR_POLICY_PARENT_V3_FORECAST_DEBT_NEGATIVE"
                      and "bear.operating" in former.get("completed_stages", ())
                      and not any(row["status"] == "RESERVED"
                                  for row in former.get("reservations", {}).values())):
                    request_key = "value-bfin1-" + binding["sha256"]
                    options.update(seed_task_id=former_id, replay_from_stage="bear.policy")
                if (former.get("status") == "FAILED" and
                        former.get("error_code") == "BEAR_OPERATING_PARENT_V3_CONFLICTING_JSON_KEY"):
                    request_key = "value-wire1-" + binding["sha256"]
                    options["seed_task_id"] = former_id
                elif (former.get("status") == "FAILED" and former.get("error_code") ==
                      "BEAR_TERMINAL_PARENT_V3_UNSUPPORTED_STATIONARY_CASH_CONVERSION"):
                    if (former.get("fixed_financing_research") is True
                            and not any(row["status"] == "RESERVED"
                                        for row in former.get("reservations", {}).values())):
                        request_key = "value-bop2-" + binding["sha256"]
                        options.update(seed_task_id=former_id, replay_from_stage="bear.operating")
                    elif not former.get("fixed_financing_research"):
                        request_key = "value-tail1-" + binding["sha256"]
                        options.update(seed_task_id=former_id, replay_from_stage="bear.terminal")
                elif (former.get("status") == "FAILED" and
                      former.get("error_code") == "BEAR_POLICY_PARENT_V3_INVALID_JSON" and
                      "bear.operating" in former.get("completed_stages", ()) and
                      not any(row["status"] == "RESERVED"
                              for row in former.get("reservations", {}).values())):
                    # One deterministic retry is tied to the original task.
                    request_key = "value-policy1-" + binding["sha256"]
                    options.update(seed_task_id=former_id, replay_from_stage="bear.policy")
                elif (former.get("status") == "FAILED" and
                      former.get("error_code") == "BEAR_OPERATING_PARENT_V3_YEARS_OR_SERIES_INVALID" and
                      not any(row["status"] == "RESERVED"
                              for row in former.get("reservations", {}).values())):
                    request_key = "value-op1-" + binding["sha256"]
                    options.update(seed_task_id=former_id, replay_from_stage="bear.operating")
            task = numbered_service.create(
                spec_binding=binding, request_key=request_key, **options)
            if (request_key.startswith("value-bop2-") and task["status"] == "FAILED"
                    and task.get("error_code") ==
                    "BASE_POLICY_PARENT_V3_ECONOMIC_DIRECT_OWNER_UNFUNDED_CASH_REQUIREMENT:2027"
                    and "bear.terminal" in task.get("completed_stages", ())
                    and not any(row["status"] == "RESERVED"
                                for row in task.get("reservations", {}).values())):
                request_key = "value-basecash1-" + binding["sha256"]
                task = numbered_service.create(
                    spec_binding=binding, request_key=request_key,
                    seed_task_id=task["task_id"], replay_from_stage="base.operating",
                )
            if (request_key.startswith("value-basecash1-") and task["status"] == "FAILED"
                    and task.get("error_code") ==
                    "BASE_TERMINAL_PARENT_V3_UNSUPPORTED_STATIONARY_CASH_CONVERSION"
                    and "base.policy" in task.get("completed_stages", ())
                    and not any(row["status"] == "RESERVED"
                                for row in task.get("reservations", {}).values())):
                request_key = "value-basetail1-" + binding["sha256"]
                task = numbered_service.create(
                    spec_binding=binding, request_key=request_key,
                    seed_task_id=task["task_id"], replay_from_stage="base.terminal",
                )
            if (request_key.startswith("value-basetail1-") and task["status"] == "FAILED"
                    and task.get("error_code") ==
                    "BASE_TERMINAL_PARENT_V3_UNSUPPORTED_STATIONARY_CASH_CONVERSION"
                    and "base.policy" in task.get("completed_stages", ())
                    and not any(row["status"] == "RESERVED"
                                for row in task.get("reservations", {}).values())):
                task = numbered_service.create(
                    spec_binding=binding, request_key="value-basehist1-" + binding["sha256"],
                    seed_task_id=task["task_id"], replay_from_stage="base.terminal",
                )
            if (request_key.startswith("value-bfin1-") and task["status"] == "FAILED"
                    and task.get("error_code") == "BASE_POLICY_PARENT_DRAFT_TERM_SOURCE_INVALID"
                    and "bear.operating" in task.get("completed_stages", ())
                    and not any(row["status"] == "RESERVED"
                                for row in task.get("reservations", {}).values())):
                task = numbered_service.create(
                    spec_binding=binding, request_key="value-coupon1-" + binding["sha256"],
                    seed_task_id=task["task_id"], replay_from_stage="bear.policy",
                )
            if (request_key.startswith("value-fin1-") and task["status"] == "FAILED"
                    and task.get("error_code") ==
                    "BASE_TERMINAL_PARENT_V3_UNSUPPORTED_STATIONARY_CASH_CONVERSION"):
                request_key = "value-fin2-" + binding["sha256"]
                task = numbered_service.create(
                    spec_binding=binding, request_key=request_key,
                    seed_task_id=task["task_id"], replay_from_stage="base.terminal",
                )
            if (request_key.startswith("value-fin2-") and task["status"] == "FAILED"
                    and task.get("error_code") ==
                    "BASE_TERMINAL_PARENT_V3_UNSUPPORTED_STATIONARY_CASH_CONVERSION"):
                request_key = "value-fin3-" + binding["sha256"]
                task = numbered_service.create(
                    spec_binding=binding, request_key=request_key,
                    seed_task_id=task["task_id"], replay_from_stage="base.operating",
                )
            if (request_key.startswith(("value-fin1-", "value-fin2-", "value-fin3-"))
                    and task["status"] == "RUNNING"):
                try:
                    task = numbered_service.resume_if_interrupted(task["task_id"])
                except LockTimeout:
                    return reply(task, 202)
            if task["status"] in {"QUEUED", "SUCCEEDED"}:
                background.add_task(run_numbered, task["task_id"])
            return reply(task, 202)
        except (ValueError, TypeError, KeyError, OSError, ArithmeticError) as exc:
            reason = str(exc)
            return reply(dict(status="PARENT_V3_TASK_REJECTED", action="no_order",
                              reason=reason if re.fullmatch(r"[A-Z0-9_]{3,120}", reason)
                              else "PARENT_V3_INPUT_VERIFICATION_FAILED"), 422)

    @api.get("/api/v1/operating-research/parent-cash-tasks/v3/{task_id}")
    def read_numbered(task_id: str, request: Request):
        error = denied(request)
        if error is not None:
            return error
        if not re.fullmatch(r"rt-[0-9a-f]{32}", task_id):
            return reply({"action": "no_order", "status": "INVALID_TASK_ID"}, 422)
        try:
            primary_base = getattr(numbered_service, "base", None)
            if (primary_base is None or (Path(primary_base) / task_id).exists()
                    or archived_numbered_service is None):
                return reply(_numbered_task_with_observed_investing_cash(numbered_service, task_id))
            return reply(_numbered_task_with_observed_investing_cash(archived_numbered_service, task_id))
        except (ValueError, TypeError, KeyError, OSError, PermissionError):
            return reply({"action": "no_order", "status": "PARENT_V3_TASK_UNAVAILABLE"}, 422)

    @api.get("/api/v1/operating-research/parent-cash-tasks/v3/{task_id}/valuation")
    def read_numbered_valuation(task_id: str, symbol: str, request: Request):
        error = denied(request)
        if error is not None:
            return error
        if not re.fullmatch(r"rt-[0-9a-f]{32}", task_id) or not re.fullmatch(r"[0-9]{6}", symbol):
            return reply(dict(status="INVALID_TASK_OR_SYMBOL", action="no_order"), 422)
        from datetime import datetime, timezone
        from hashlib import sha256
        from ...application.research.parent_cash_task_alignment_v3 import _align_verified_parent_cash_task
        from ...application.research.parent_cash_task_distribution_receipt_v1 import replay as replay_parent_cash_task_receipt

        try:
            candidates = [(task_root, valuation_receipt_path(task_root, task_id))
                          for task_root in dict.fromkeys((Path(root).resolve(), code_root))]
            available = [(task_root, path) for task_root, path in candidates if path.is_file()]
            if not available:
                blocked = []
                for task_root, _ in candidates:
                    if not valuation_blockage_path(task_root, task_id).is_file():
                        continue
                    task_service = (numbered_service if task_root == Path(root).resolve()
                                    else archived_numbered_service)
                    spec, state, head = task_service._load(task_id)
                    source = task_service._bound(spec["spec_binding"])
                    if source.get("symbol") != symbol:
                        raise ValueError("PARENT_TASK_VALUATION_IDENTITY_MISMATCH")
                    publication = read_valuation_publication(task_root, task_id, head)
                    if publication["valuation_receipt_status"] == "BLOCKED":
                        blocked.append(publication)
                if len(blocked) > 1:
                    raise ValueError("PARENT_TASK_DUPLICATE_PUBLICATION_STATUS")
                if blocked:
                    return reply(dict(status="PARENT_TASK_VALUATION_BLOCKED", action="no_order",
                                      task_id=task_id, symbol=symbol,
                                      reason=blocked[0]["valuation_blockage"]["reason_code"],
                                      **blocked[0]), 409)
                response = dict(status="PARENT_TASK_VALUATION_NOT_SEALED", action="no_order")
                task_services = [
                    service for service in (numbered_service, archived_numbered_service)
                    if getattr(service, "base", None) is not None
                    and (Path(service.base) / task_id).is_dir()
                ]
                if len(task_services) > 1:
                    raise ValueError("PARENT_TASK_DUPLICATE_TASK_STATE")
                if task_services:
                    task_service = task_services[0]
                    spec, state, _ = task_service._load(task_id)
                    if task_service._bound(spec["spec_binding"]).get("symbol") == symbol:
                        response["task_status"] = state["status"]
                        code = state.get("error_code")
                        if isinstance(code, str) and re.fullmatch(r"[A-Z0-9_]{3,120}", code):
                            response["task_error_code"] = code
                            if state["status"] == "FAILED":
                                response["reason"] = code
                return reply(response, 404)
            if len(available) != 1:
                raise ValueError("PARENT_TASK_DUPLICATE_VALUATION_RECEIPT")
            task_root, path = available[0]
            if path.stat().st_size > 64 * 1024:
                raise ValueError("PARENT_TASK_VALUATION_RECEIPT_TOO_LARGE")
            binding = dict(path=path.relative_to(task_root).as_posix(),
                           sha256=sha256(path.read_bytes()).hexdigest())
            now = datetime.now(timezone.utc)
            result = replay_parent_cash_task_receipt(root=task_root, receipt_binding=binding, now=now)
            if (result["symbol"] != symbol or result["provenance"]["task_id"] != task_id
                    or result["action"] != "no_order" or result["formal_eligibility"] is not False
                    or result["main_range_adopted"] is not False):
                raise ValueError("PARENT_TASK_VALUATION_IDENTITY_MISMATCH")
            valuations = result["valuation"]["assumptions"]["scenario_calculations"]
            scenarios = {name: dict(per_share_value=valuations[name]["per_share_value"],
                                    annual_years=len(valuations[name]["annual_rows"]),
                                    terminal_method=valuations[name]["terminal_method"],
                                    terminal_steady_distribution_cny=(
                                        valuations[name]["terminal_steady_distribution_cny"]),
                                    annual_cash_path=[
                                        dict(
                                            year=row["year"],
                                            direct_operating_cash_cny=row["direct_operating_cash_cny"],
                                            closing_cash_cny=row["closing_cash_cny"],
                                            closing_debt_cny=row["closing_debt_cny"],
                                            closing_book_equity_cny=row["closing_book_equity_cny"],
                                            total_owner_distribution_cny=(
                                                row["total_owner_distribution_cny"]
                                                if "total_owner_distribution_cny" in row
                                                else row["conditional_distribution_cny"]
                                            ),
                                        )
                                        for row in valuations[name]["annual_rows"]
                                    ])
                         for name in ("bear", "base", "bull")}
            alignment = _align_verified_parent_cash_task(
                root=task_root, receipt_binding=binding, result=result, now=now)
            comparison_quote = _comparison_quote(alignment)
            return reply(dict(status="VERIFIED_CONDITIONAL_VALUATION",
                comparison_quote=comparison_quote, qualified_close=_qualified_close(alignment),
                alignment_status=alignment["status"], alignment_reason_codes=alignment["reason_codes"],
                task_id=task_id, symbol=symbol, valuation_date=result["descriptor"]["point_in_time"]["valuation_date"],
                scenarios=scenarios, receipt_sha256=binding["sha256"],
                input_descriptor_sha256=result["input_descriptor_sha256"], action="no_order",
                formal_eligibility=False, current_comparable=comparison_quote is not None,
                condition_price=None))
        except (ValueError, TypeError, KeyError, OSError, ArithmeticError):
            return reply(dict(status="PARENT_TASK_VALUATION_UNAVAILABLE", action="no_order"), 422)

    @api.get("/api/v1/operating-research/parent-cash-tasks/v3/{task_id}/h1-sensitivity")
    def read_numbered_h1_sensitivity(task_id: str, symbol: str, request: Request):
        error = denied(request)
        if error is not None:
            return error
        if not re.fullmatch(r"rt-[0-9a-f]{32}", task_id) or not re.fullmatch(r"[0-9]{6}", symbol):
            return reply(dict(status="INVALID_TASK_OR_SYMBOL", action="no_order"), 422)
        from datetime import datetime, timezone
        from hashlib import sha256
        from ...application.product.common import require_inside
        from ...application.research.direct_owner_cash_research_v1 import _read
        from ...application.research.parent_h1_valuation_sensitivity_v1 import (
            replay_parent_h1_valuation_sensitivity,
        )

        directory = Path("runtime") / "parent-cash-task-backed-receipts" / task_id
        try:
            available = []
            for task_root in dict.fromkeys((Path(root).resolve(), code_root)):
                path = require_inside(task_root / directory, task_root / directory / "h1-sensitivity.json",
                                      "H1 task sensitivity registration")
                if path.is_file():
                    available.append((task_root, path))
            if not available:
                return reply(dict(status="PARENT_TASK_H1_SENSITIVITY_NOT_REGISTERED", action="no_order"), 404)
            if len(available) != 1:
                raise ValueError("PARENT_TASK_DUPLICATE_H1_SENSITIVITY")
            task_root, path = available[0]
            if path.stat().st_size > 16 * 1024:
                raise ValueError("PARENT_TASK_H1_SENSITIVITY_REGISTRATION_TOO_LARGE")
            reg = json.loads(path.read_bytes())
            if (reg["symbol"] != symbol or reg["task_id"] != task_id
                    or reg["action"] != "no_order"
                    or reg["schema_version"] != "parent-h1-task-sensitivity-registration-v1"):
                raise ValueError("PARENT_TASK_H1_SENSITIVITY_IDENTITY_MISMATCH")
            predecessor = require_inside(task_root / directory, task_root / directory / "receipt.json",
                                         "H1 sensitivity predecessor")
            predecessor_binding = dict(path=predecessor.relative_to(task_root).as_posix(),
                                       sha256=sha256(predecessor.read_bytes()).hexdigest())
            receipt = _read(task_root, predecessor_binding)
            if receipt["inputs"]["task_id"] != task_id:
                raise ValueError("PARENT_TASK_H1_PREDECESSOR_IDENTITY_MISMATCH")
            result = replay_parent_h1_valuation_sensitivity(
                root=task_root, predecessor_binding=predecessor_binding,
                assumptions_binding=reg["assumptions_binding"],
                share_evidence_binding=reg.get("share_evidence_binding"), now=datetime.now(timezone.utc))
            if result["symbol"] != symbol:
                raise ValueError("PARENT_TASK_H1_SENSITIVITY_ISSUER_MISMATCH")
            scenarios = {}
            for name, row in result["scenarios"].items():
                item = {"status": row["status"]}
                if "valuation" in row:
                    item["per_share_value"] = row["valuation"]["per_share_value"]
                else:
                    item["reason"] = row["reason"]
                scenarios[name] = item
            return reply(dict(status=result["status"], symbol=symbol, task_id=task_id,
                period_end=result["period_end"], scenarios=scenarios, formal_eligibility=False,
                condition_price=None, action="no_order"))
        except (ValueError, TypeError, KeyError, OSError, ArithmeticError):
            return reply(dict(status="PARENT_TASK_H1_SENSITIVITY_UNAVAILABLE", action="no_order"), 422)

    @api.post("/api/v1/operating-research/parent-cash-tasks/v3/{task_id}/{operation}")
    def control_numbered(task_id: str, operation: str, request: Request,
                         background: BackgroundTasks):
        error = denied(request)
        if error is not None:
            return error
        if not re.fullmatch(r"rt-[0-9a-f]{32}", task_id) or operation not in {"cancel", "resume", "seal"}:
            return reply({"action": "no_order", "status": "INVALID_TASK_CONTROL"}, 422)
        primary_base = getattr(numbered_service, "base", None)
        if (primary_base is not None and archived_numbered_service is not None
                and not (Path(primary_base) / task_id).exists()
                and (archived_numbered_service.base / task_id).exists()):
            return reply({"action": "no_order", "status": "ARCHIVED_TASK_READ_ONLY"}, 422)
        try:
            if operation == "seal":
                task = numbered_service.read(task_id)
                if task["status"] != "SUCCEEDED" or task.get("mode") != "LIVE_PARENT_CASH_V3":
                    return reply(dict(status="PARENT_TASK_LIVE_SUCCESS_REQUIRED", action="no_order"), 409)
                background.add_task(run_numbered, task_id, publication_only=True)
                return reply(dict(status="VALUATION_SEAL_REQUESTED", task_id=task_id, action="no_order"), 202)
            task = (numbered_service.cancel(task_id) if operation == "cancel"
                    else numbered_service.resume(task_id))
            if operation == "resume" and task["status"] in {"QUEUED", "SUCCEEDED"}:
                background.add_task(run_numbered, task_id)
            return reply(task)
        except (ValueError, TypeError, KeyError, OSError, PermissionError):
            return reply({"action": "no_order", "status": "PARENT_V3_TASK_UNAVAILABLE"}, 422)

    replay_path = "/api/v1/operating-research/parent-cash-tasks/v3/{task_id}/funding-revisions/{receipt_sha256}/replay"

    @api.get(replay_path)
    @api.post(replay_path)
    async def replay_funding_continuation(request: Request, task_id: str, receipt_sha256: str, symbol: str):
        error = denied(request)
        if error is not None:
            return error
        if (not re.fullmatch(r"rt-[0-9a-f]{32}", task_id) or not funding.SHA.fullmatch(receipt_sha256)
                or not re.fullmatch(r"[0-9]{6}", symbol)):
            return reply(dict(status="INVALID_TASK_IDENTITY", action="no_order"), 422)
        create = request.method == "POST"
        if create:
            body = bytearray()
            async for chunk in request.stream():
                if len(body) + len(chunk) > 32:
                    return reply(dict(status="INVALID_REPLAY_REQUEST", action="no_order"), 422)
                body.extend(chunk)
            if body.strip() and not re.fullmatch(rb"\s*\{\s*\}\s*", body):
                return reply(dict(status="INVALID_REPLAY_REQUEST", action="no_order"), 422)
        versions = request.query_params.getlist("version")
        if versions and versions not in (["fixed-payment-v1"], ["maturity-v1"]):
            return reply(dict(status="CONTINUATION_VERSION_UNSUPPORTED", action="no_order"), 422)
        return await run_in_threadpool(funding_continuation, task_id, receipt_sha256, symbol, create,
                                       versions[0] if versions else "fixed-payment-v1")

    def funding_continuation(task_id, digest, symbol, create, version):
        from ...application.research import parent_cash_funding_continuation_v1 as continuation
        from ...application.research import parent_cash_funding_revision_v1 as revision

        try:
            owners = [owner for owner in (numbered_service, archived_numbered_service)
                      if owner is not None and (owner.base / task_id / "input.json").is_file()]
            if not owners:
                return reply(dict(status="TASK_NOT_FOUND", action="no_order"), 404)
            if len(owners) != 1:
                return reply(dict(status="TASK_OWNER_AMBIGUOUS",
                                  action="no_order"), 409)
            owner, = owners
            source_root = Path(owner.root).resolve()
            spec, state, _ = owner._load(task_id)
            binding = spec["spec_binding"]
            if owner._bound(binding).get("symbol") != symbol:
                return reply(dict(status="TASK_NOT_FOUND", action="no_order"), 404)
            folder = funding.directory(source_root, task_id) / digest
            revision._checked_path(source_root, folder)
            receipt = revision._sibling(folder, "receipt", digest)
            if spec["mode"] != "LIVE_PARENT_CASH_V3" or receipt["registered_spec"] != binding:
                raise ValueError("CONTINUATION_PARENT_CHANGED")
            revision._verify_parent(source_root, receipt, task_id)
            parent_head = receipt["parent_head"]
            projected = funding._project(source_root, folder, task_id, symbol, parent_head, binding, {})
            adjustment = receipt["current_reassessment"]["revised_spec"]
            revised = revision._sibling(folder, "reassessment-spec", adjustment)
            matrix = revision._sibling(folder, "financing-evidence", receipt["originals_matrix"])
            terms = funding._financing_terms(revised, matrix)
            if not terms or terms["status"] != "VERIFIED":
                raise ValueError("CONTINUATION_FINANCING_TERMS_UNAVAILABLE")
            identity = dict(task_id=task_id, receipt_sha256=digest, symbol=symbol, parent_head_sha256=parent_head["sha256"],
                            registered_spec_sha256=binding["sha256"], reassessment_spec_sha256=adjustment["sha256"],
                            input_descriptor_sha256=projected["input_descriptor_sha256"], financing_terms=terms,
                            original_task_status=receipt["previous_task_status"], valuation_date=projected["valuation_date"],
                            current_reassessment=projected["current_reassessment"])
            result = continuation.replay_or_read(source_root, Path(root).resolve(), identity, create=create, version=version,
                                                 now=datetime.now(timezone.utc))
            if result is None:
                return reply(dict(status="CONTINUATION_NOT_SEALED", action="no_order"), 404)
            return reply(dict(result, paid_task_status=state["status"],
                              source_owner="EXECUTION_ROOT" if owner is numbered_service else "READ_ONLY_ARCHIVE"))
        except LockTimeout:
            return reply(dict(status="CONTINUATION_IN_PROGRESS", action="no_order"), 409)
        except FileNotFoundError:
            return reply(dict(status="CONTINUATION_INPUT_MISSING", action="no_order"), 404)
        except (OSError, ValueError, KeyError, TypeError, RuntimeError, ArithmeticError, ImportError):
            return reply(dict(status="CONTINUATION_VERIFICATION_FAILED", action="no_order"), 422)

    @api.get("/api/v1/operating-research/parent-cash-tasks/v3/{task_id}/funding-revisions")
    def funding_revisions(request: Request, task_id: str, symbol: str):
        rejection = denied(request)
        if rejection is not None:
            return rejection
        if not re.fullmatch(r"rt-[0-9a-f]{32}", task_id) or not re.fullmatch(r"[0-9]{6}", symbol):
            return reply({"status": "INVALID_TASK_IDENTITY"}, 422)
        try:
            owners = [owner for owner in (numbered_service, archived_numbered_service)
                      if owner is not None and (owner.base / task_id / "input.json").is_file()]
            if not owners:
                return reply({"status": "TASK_NOT_FOUND"}, 404)
            if len(owners) != 1:
                return reply({"status": "TASK_OWNER_AMBIGUOUS"}, 409)
            owner, = owners
            spec, state, head = owner._load(task_id)
            original = spec["spec_binding"]
            if owner._bound(original).get("symbol") != symbol:
                return reply({"status": "TASK_NOT_FOUND"}, 404)
            versions = funding.read_revisions(Path(owner.root).resolve(), task_id, symbol, head, original)
            return reply(dict(task_id=task_id, symbol=symbol, original_task_status=state["status"],
                              revisions=versions, action="no_order", current_comparable=False))
        except funding.RevisionError as error:
            return reply({"status": error.args[0]}, 422)
        except (OSError, ValueError, KeyError, TypeError, RuntimeError):
            return reply({"status": "TASK_BINDING_UNAVAILABLE"}, 422)

    @api.get("/api/v1/operating-research/parent-cash-tasks/history")
    def history(request: Request, symbol: str):
        try:
            authorize(request, session=sessions, port=port)
        except LocalAuthorizationError as error:
            return reply({"action": "no_order", "status": error.code},
                         401 if error.code == AUTHORIZATION_REQUIRED else 403)
        if not re.fullmatch(r"[0-9]{6}", symbol):
            return reply({"action": "no_order", "status": "INVALID_SYMBOL"}, 422)
        try:
            children = list(islice(service.base.iterdir(), 101)) if service.base.exists() else []
            if len(children) > 100:
                raise ValueError("PARENT_TASK_DISCOVERY_LIMIT_EXCEEDED")
            items = []
            for directory in sorted(children):
                if not directory.is_dir() or not re.fullmatch(r"rt-[0-9a-f]{32}", directory.name):
                    continue
                if not (directory / "input.json").is_file():
                    continue
                spec, state, binding = service._load(directory.name)
                source_path = spec["spec_binding"]["path"]
                if not source_path.startswith("runtime/"):
                    raise ValueError("PARENT_TASK_SOURCE_OUTSIDE_RUNTIME")
                source = service._bound(spec["spec_binding"])
                if source.get("action") != "no_order":
                    raise ValueError("PARENT_TASK_SOURCE_INVALID")
                if source.get("symbol") != symbol:
                    continue
                if state["status"] == "SUCCEEDED" and len(state.get("responses", {})) == 9:
                    continue
                years = sorted({ref["period_end"][:4] for ref in source.get("fact_anchors", {}).values()
                                if isinstance(ref, dict) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}",
                                                                         str(ref.get("period_end", "")))})
                reservations = state.get("reservations", {})
                if len(reservations) > 32 or len(state.get("responses", {})) > 9:
                    raise ValueError("PARENT_TASK_PROJECTION_LIMIT_EXCEEDED")
                error_code = state.get("error_code")
                error_stage = next((stage for stage in STAGE_ORDER
                                    if isinstance(error_code, str) and error_code.startswith(
                                        stage.upper().replace(".", "_") + "_")), None)
                items.append({"task_id": directory.name, "status": state["status"],
                    "task_contract": "parent-cash-task-v2",
                    "stage": next((row.get("scenario") for row in reservations.values()
                                   if row.get("status") == "RESERVED"), error_stage),
                    "completed_stages": sorted(state.get("responses", {})),
                    "error_code": state.get("error_code"), "source_years": years,
                    "source_binding": spec["spec_binding"], "record_binding": binding,
                    "reserved_cost_cny": state.get("reserved_cost"),
                    "settled_cost_cny": state.get("settled_cost"),
                    "charges": [{"stage": row.get("scenario"), "status": row.get("status"),
                                 "reserved_cny": row.get("cost"), "settled_cny": row.get("actual_cost")}
                                for row in reservations.values()],
                    "e2_consumption": "UNVERIFIED", "formal": False, "action": "no_order"})
            seen_numbered = set()
            for numbered, archived in ((numbered_service, False),
                                       (archived_numbered_service, True)):
                if numbered is None or not numbered.base.exists():
                    continue
                numbered_children = list(islice(numbered.base.iterdir(), 101))
                if len(numbered_children) > 100:
                    raise ValueError("PARENT_V3_TASK_DISCOVERY_LIMIT_EXCEEDED")
                for directory in sorted(numbered_children):
                    if (not directory.is_dir()
                            or not re.fullmatch(r"rt-[0-9a-f]{32}", directory.name)
                            or not (directory / "input.json").is_file()):
                        continue
                    if directory.name in seen_numbered:
                        raise ValueError("PARENT_V3_DUPLICATE_TASK_ACROSS_ROOTS")
                    seen_numbered.add(directory.name)
                    spec, state, binding = numbered._load(directory.name)
                    source = numbered._bound(spec["spec_binding"])
                    if (source.get("action") != "no_order"
                            or not spec["spec_binding"]["path"].startswith("runtime/")):
                        raise ValueError("PARENT_V3_TASK_SOURCE_INVALID")
                    if source.get("symbol") != symbol:
                        continue
                    reservations = state.get("reservations", {})
                    if len(reservations) > 32 or len(state.get("responses", {})) > 9:
                        raise ValueError("PARENT_V3_TASK_PROJECTION_LIMIT_EXCEEDED")
                    cohort_continuation = False
                    if (not archived and state["status"] == "FAILED"
                            and state.get("error_code") ==
                            "BASE_TERMINAL_PARENT_V3_UNSUPPORTED_STATIONARY_CASH_CONVERSION"
                            and "base.policy" in state["responses"]
                            and not any(row["status"] == "RESERVED" for row in reservations.values())):

                        entry = _case_entry(Path(numbered.root), spec["spec_binding"]) or {}
                        annual_pin = entry.get("terminal_parent_prior_annual_receipt")
                        cohort_continuation = annual_pin is not None and (
                            annual_pin != spec.get("terminal_parent_prior_annual_receipt")
                            or entry.get("terminal_parent_cash_method") != spec.get("terminal_parent_cash_method")
                        )
                    items.append({"task_id": directory.name, "task_contract": "parent-cash-task-v3",
                        "terminal_cohort_continuation": cohort_continuation,
                        "terminal_cash_review": spec.get("terminal_cash_review"),
                        "read_only_archive": archived,
                        "reused_stages": sorted((spec.get("seed") or {}).get("responses", {})),
                        "base_policy_wire": spec.get("base_policy_wire"),
                        "base_operating_wire": spec.get("base_operating_wire"),
                        "base_interest_wire": spec.get("base_interest_wire"),
                        "status": state["status"],
                        "stage": next((row.get("scenario") for row in reservations.values()
                                       if row.get("status") == "RESERVED"), None),
                        "completed_stages": sorted(state.get("responses", {})),
                        "error_code": state.get("error_code"),
                        "source_years": sorted({ref["period_end"][:4]
                            for ref in source.get("fact_anchors", {}).values()
                            if isinstance(ref, dict) and re.fullmatch(
                                r"[0-9]{4}-[0-9]{2}-[0-9]{2}", str(ref.get("period_end", "")))}),
                        "source_binding": spec["spec_binding"], "record_binding": binding,
                        "reserved_cost_cny": state.get("reserved_cost"),
                        "settled_cost_cny": state.get("settled_cost"),
                        "charges": [{"stage": row.get("scenario"), "status": row.get("status"),
                                     "reserved_cny": row.get("cost"),
                                     "settled_cny": row.get("actual_cost")}
                                    for row in reservations.values()],
                        **read_valuation_publication(
                            code_root if archived else Path(root), directory.name, binding),
                        "has_funding_revisions": funding.directory(
                            code_root if archived else Path(root).resolve(), directory.name).is_dir(),
                        "debt_timing_sensitivity": _read_debt_timing_sensitivity(
                            code_root if archived else Path(root).resolve(), directory.name, symbol, binding),
                        "candidate_status": ("COMPILED_CONDITIONAL_NOT_MAIN" if state["status"] == "SUCCEEDED"
                                             else "NOT_COMPILED"),
                        "e2_consumption": "UNVERIFIED", "formal": False, "action": "no_order"})
            return reply({"action": "no_order", "symbol": symbol, "items": items, "formal": False})
        except (ValueError, OSError, KeyError, TypeError, RuntimeError):
            return reply({"action": "no_order", "status": "PARENT_TASK_HISTORY_UNAVAILABLE"}, 422)
