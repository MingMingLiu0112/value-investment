"""Bounded, read-only projection of existing parent cash task checkpoints."""
import re
import logging
import json
from itertools import islice
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.responses import JSONResponse

from ...application.research.parent_cash_task_completion_v1 import (
    registered_cash_task_spec, run_and_seal_parent_cash_task, seal_completed_parent_cash_task,
    valuation_receipt_path,
    preflight_parent_cash_task, read_valuation_publication, valuation_blockage_path,
)
from ...application.portfolio.private_journal_lock import LockTimeout
from .live_operating_research_routes import resolve_research_task_root
from .local_auth import authorize, LocalAuthorizationError, AUTHORIZATION_REQUIRED
from ...application.research.agent_review.parent_cash_task_v2 import ParentCashTaskServiceV2, STAGE_ORDER
from ...application.research.agent_review.parent_cash_task_v3 import ParentCashTaskServiceV3


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
        try:
            raw = await request.body()
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
        try:
            raw = await request.body()
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
                if (prior.get("status") == "FAILED" and prior.get("spec_binding") == binding
                        and prior.get("error_code") in {
                            "PARENT_V3_ECONOMIC_DIRECT_INPUT_DATED_SHARE_FACT_REQUIRED",
                            "PARENT_V3_ECONOMIC_DIRECT_OWNER_NO_POSITIVE_SUPPORTED_TERMINAL_DISTRIBUTION",
                        }
                        and len(prior.get("completed_stages", ())) == 9
                        and all(row["status"] == "SETTLED" for row in prior.get("reservations", {}).values())):
                    digest = sha256(predecessor.encode()).hexdigest()
                    task = numbered_service.create(
                        spec_binding=binding, request_key="value-payout-review-v2-" + digest[:54],
                        seed_task_id=predecessor, replay_from_stage="base.terminal",
                    )
                    if task["status"] in {"QUEUED", "SUCCEEDED"}:
                        background.add_task(run_numbered, task["task_id"])
                    return reply(task, 202)
                is_earnings_rebuild = prior.get("error_code") == (
                    "BASE_TERMINAL_PARENT_V3_UNSUPPORTED_STATIONARY_CASH_CONVERSION")
                if is_earnings_rebuild and prior.get("spec_binding") == binding:
                    from ...application.research.parent_cash_task_completion_v1 import _case_entry

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
        except (ValueError, TypeError, KeyError, OSError) as exc:
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
                return reply(numbered_service.read(task_id))
            return reply(archived_numbered_service.read(task_id))
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
                                      task_id=task_id, symbol=symbol, **blocked[0]), 409)
                return reply(dict(status="PARENT_TASK_VALUATION_NOT_SEALED", action="no_order"), 404)
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
                                    terminal_method=valuations[name]["terminal_method"])
                         for name in ("bear", "base", "bull")}
            alignment = _align_verified_parent_cash_task(
                root=task_root, receipt_binding=binding, result=result, now=now)
            return reply(dict(status="VERIFIED_CONDITIONAL_VALUATION",
                alignment_status=alignment["status"], alignment_reason_codes=alignment["reason_codes"],
                task_id=task_id, symbol=symbol, valuation_date=result["descriptor"]["point_in_time"]["valuation_date"],
                scenarios=scenarios, receipt_sha256=binding["sha256"],
                input_descriptor_sha256=result["input_descriptor_sha256"], action="no_order",
                formal_eligibility=False, current_comparable=False, condition_price=None))
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
                        from ...application.research.parent_cash_task_completion_v1 import _case_entry

                        entry = _case_entry(Path(numbered.root), spec["spec_binding"]) or {}
                        annual_pin = entry.get("terminal_parent_prior_annual_receipt")
                        cohort_continuation = annual_pin is not None and (
                            annual_pin != spec.get("terminal_parent_prior_annual_receipt")
                            or entry.get("terminal_parent_cash_method") != spec.get("terminal_parent_cash_method")
                        )
                    items.append({"task_id": directory.name, "task_contract": "parent-cash-task-v3",
                        "terminal_cohort_continuation": cohort_continuation,
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
                        "candidate_status": ("COMPILED_CONDITIONAL_NOT_MAIN" if state["status"] == "SUCCEEDED"
                                             else "NOT_COMPILED"),
                        "e2_consumption": "UNVERIFIED", "formal": False, "action": "no_order"})
            return reply({"action": "no_order", "symbol": symbol, "items": items, "formal": False})
        except (ValueError, OSError, KeyError, TypeError, RuntimeError):
            return reply({"action": "no_order", "status": "PARENT_TASK_HISTORY_UNAVAILABLE"}, 422)
