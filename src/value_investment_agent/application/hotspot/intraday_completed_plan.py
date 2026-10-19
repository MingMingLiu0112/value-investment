"""Pure completed-bar observation over an existing trusted-loader plan binding."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone

from .intraday_bar_observation import BLOCKERS, project_intraday_bar_observation
from .intraday_conditions import evaluate_intraday_condition
from .intraday_plan_observation import AGE, KINDS, _digest, _stamp, evaluate_quote_plan
from ...infrastructure.hotspot.sina_price_case import ENDPOINT, PERIODS


SCHEMA = "intraday-completed-plan-result-v1"
SCOPE = "SINGLE_PROVIDER_COMPLETED_BAR_OBSERVATION_ONLY"


def project_completed_plan(binding: dict, documents: dict, previous=None, *, now: datetime,
                           include_documents: bool = True) -> dict:
    """Return periods/status/evidence and replayable native condition states.

    binding is from bind_quote_plan on a loader-verified plan. documents maps
    60m/15m to retained raw documents (missing/invalid values are preserved).
    previous is this helper's exact prior result, never a quote-plan result.
    The caller alone owns persistence; returned M5 events are not published.
    """
    checked = evaluate_quote_plan(binding, None, previous=None, now=now)
    now = now.astimezone(timezone.utc)
    if not isinstance(documents, dict):
        raise ValueError("Period-to-raw-document mapping required")
    if previous is not None:
        if (not isinstance(previous, dict) or previous.get("schema_version") != SCHEMA
                or previous.get("binding_sha256") != binding["binding_sha256"]
                or previous.get("result_sha256") != _digest({key: value for key, value in previous.items()
                                                            if key != "result_sha256"})
                or previous.get("action") != "no_order" or previous.get("eligibility") is not False
                or previous.get("formal_eligibility") is not False
                or previous.get("m5_admitted") is not False or _stamp(previous["checked_at"]) > now):
            raise ValueError("Foreign, changed or future completed-plan result")
        if (previous.get("symbol") != binding["symbol"] or previous.get("scope") != SCOPE
                or not isinstance(previous.get("periods"), dict)
                or set(previous["periods"]) != set(PERIODS)):
            raise ValueError("Incomplete or foreign prior periods")
    plan = binding["plan"]
    expired = checked["plan_status"] == "STALE_OR_UNAVAILABLE"
    periods, evidence = {}, []
    for period in PERIODS:
        document = documents.get(period)
        age = timedelta(minutes=int(PERIODS[period])) + AGE
        projected = project_intraday_bar_observation(document, symbol=binding["symbol"],
            period=period, now=now, max_age=AGE, max_bar_age=age)
        observation = projected["observation"]
        reason = projected["reason"]
        if expired:
            observation, reason = None, "PLAN_REFERENCE_EXPIRED"
        elif observation is not None and _stamp(observation["source_at"]) < _stamp(plan["data_available_at"]):
            observation, reason = None, "BAR_PRECEDES_PLAN_AVAILABILITY"
        url = ENDPOINT + "?symbol=" + ("sh" if binding["symbol"].startswith("6") else "sz") + binding["symbol"]
        url += "&scale=" + PERIODS[period] + "&ma=no&datalen=8"
        if observation is not None:
            url = observation["source_url"]
            evidence.extend(deepcopy(observation["evidence_refs"]))
        elif previous is not None:
            url = previous["periods"][period]["states"][0]["condition"]["source_url"]
        states = []
        for index, (kind, operator, field) in enumerate(KINDS):
            condition = dict(strategy=plan["strategy"], symbol=binding["symbol"],
                venue="SSE" if binding["symbol"].startswith("6") else "SZSE",
                condition_id=period + ":" + kind,
                rule_version=plan["model_or_rule_version"] + ":" + binding["binding_sha256"],
                source_id="sina", source_url=url, input_kind="COMPLETED_BAR", period=period,
                operator=operator, threshold=str(plan[field]), action="no_order")
            prior = None
            if previous is not None:
                try:
                    old = previous["periods"][period]["states"][index]
                    if old["condition"] != condition or old["kind"] != kind:
                        raise ValueError("Prior completed-bar condition changed")
                    prior = old["state"]
                except (KeyError, IndexError, TypeError) as error:
                    raise ValueError("Incomplete prior completed-bar cursor") from error
            evaluated = evaluate_intraday_condition(condition, observation, previous=prior,
                now=now, max_age=age, namespace="ACTUAL")
            states.append(dict(kind=kind, condition=condition, state=evaluated.state))
        unavailable = next((row["state"] for row in states
                            if row["state"]["status"] == "STALE_OR_UNAVAILABLE"), None)
        period_result = dict(source_result=projected,
            status="INSUFFICIENT_DATA" if unavailable else "COMPLETED_BAR_VERIFIED",
            reason=reason if observation is None or unavailable is None else unavailable["reason"],
            states=states)
        if include_documents:
            period_result["document"] = deepcopy(document)
        else:
            period_result["document_sha256"] = (document or {}).get("sha256")
        periods[period] = period_result
    rows = [row for item in periods.values() for row in item["states"]]
    risk = any(row["kind"] == "INVALIDATION_REFERENCE_LT" and
               row["state"]["status"] == "CONDITION_REVIEW" for row in rows)
    usable = all(row["state"]["status"] != "STALE_OR_UNAVAILABLE" for row in rows)
    confirmed = (usable and all(item["states"][0]["state"]["status"] == "CONDITION_REVIEW"
                                for item in periods.values()) and
        plan.get("opportunity_quality", {}).get("structure_tier") == "STRUCTURE_QUALIFIED_OBSERVATION")
    status = ("RISK_REVIEW" if risk else "INSUFFICIENT_DATA" if not usable else
              "STRUCTURE_CONFIRMED_OBSERVATION" if confirmed else "WAITING_CONFIRMATION")
    result = dict(schema_version=SCHEMA, symbol=binding["symbol"],
        binding_sha256=binding["binding_sha256"], checked_at=now.isoformat(), scope=SCOPE,
        periods=periods, status=status, evidence=evidence,
        blockers=list(dict.fromkeys([*plan["blockers"], *BLOCKERS,
            *(["PLAN_REFERENCE_EXPIRED"] if expired else [])])),
        action="no_order", eligibility=False, formal_eligibility=False, m5_admitted=False,
        admitted=False, b1_eligible=False)
    result["result_sha256"] = _digest(result)
    return result
