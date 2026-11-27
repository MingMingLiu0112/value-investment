"""Bound historical inputs for a V3 spec author, without a forecast or task launch."""
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path

from ..product.common import require_inside
from . import direct_owner_cash_agent_facts_v2 as agent
from .parent_direct_operating_observations_v1 import _other_cash
from .parent_note_grid_sources_v1 import VERSION
from .retained_parent_direct_observations import read_retained_parent_d2_preflight
from ...domain.valuation.parent_direct_operating_cash import derive_remaining_period

SCHEMA = "parent-note-grid-source-manifest-v1"


def _observation(statement, column):
    flows, income = statement["cash_flow"], statement["income"]
    selected = dict(revenue=income["revenue"], cost=income["cost"], customer_cash=flows["customer_cash_cny"],
                    supplier_cash=flows["supplier_cash_cny"], cfo=flows["cfo_cny"])
    amounts = {key: agent._finite(row[column]) for key, row in selected.items()}
    period = selected["cfo"]["source_refs"][column + "_period"]
    cash = dict(inflow=flows["operating_inflow_cny"], outflow=flows["operating_outflow_cny"],
                customer_cash=selected["customer_cash"], supplier_cash=selected["supplier_cash"])
    return dict(**amounts, classification="FACT", symbol=statement["symbol"], scope=statement["scope"],
                currency="CNY", period_start=period[:4] + "-01-01", period_end=period,
                other_operating_cash=_other_cash(cash, column),
                source_refs=dict(receipt=statement["receipt_binding"], pdf=statement["source_binding"], column=column,
                                 rows={key: [row["physical_page"], row["excerpt"]]
                                       for key, row in (selected | cash).items()}))


def read_note_grid_agent_facts(*, root, source_binding, now):
    """Reopen the manifest and both originals through the production D2 preflight."""
    from .company_profile_sources_v1 import _bound
    root = Path(root).resolve()
    require_inside(root / "runtime", root / source_binding["path"], "parent source manifest")
    raw = _bound(root, source_binding, limit=16384)
    manifest = json.loads(raw)
    if (set(manifest) != {"schema_version", "source_adapter_version", "symbol", "issuer_name",
                          "owner_sources", "action", "computed_at"}
            or manifest["schema_version"] != SCHEMA or manifest["source_adapter_version"] != VERSION
            or manifest["action"] != "no_order" or len(manifest["owner_sources"]) != 2):
        raise ValueError("NOTE_GRID_AGENT_SOURCE_MANIFEST_INVALID")
    cutoff = datetime.fromisoformat(manifest["computed_at"])
    if now.utcoffset() is None or cutoff.utcoffset() is None or cutoff > now:
        raise ValueError("NOTE_GRID_AGENT_FUTURE_SOURCE")
    annual, interim = manifest["owner_sources"]
    if (any(set(row) != {"period_end", "receipt_binding"} for row in (annual, interim))
            or not annual["period_end"].endswith("-12-31")):
        raise ValueError("NOTE_GRID_AGENT_SOURCE_PERIOD_INVALID")
    result = read_retained_parent_d2_preflight(
        root=root, symbol=manifest["symbol"], issuer_name=manifest["issuer_name"],
        annual_period=annual["period_end"], annual_receipt=annual["receipt_binding"],
        interim_period=interim["period_end"], interim_receipt=interim["receipt_binding"],
        source_adapter_version=VERSION, supporting_root=None, supporting_sources={}, evaluated_at=cutoff)
    statements = result["cash_source_bridge"]["statements"]
    observations = [_observation(s, column) for s in statements for column in ("current", "comparative")]
    derived = derive_remaining_period(full_year=observations[0], first_period=observations[3])
    _bound(root, source_binding)
    result.pop("cash_source_bridge")  # The D2 preflight retains every printed cell.
    facts = {}
    for prefix, statement in zip(("fy", "h1"), statements, strict=True):
        for section, fields in (
            ("income", ("revenue", "cost", "parent_net_profit_cny")),
            ("balance_sheet", ("book_equity_cny", "retained_earnings_cny", "liabilities_cny")),
            ("cash_flow", ("customer_cash_cny", "supplier_cash_cny", "cfo_cny", "gross_capex_cny",
                           "investment_income_cash_cny", "closing_cash_and_equivalents_cny")),
        ):
            for field in fields:
                row = statement[section][field]
                if row["current"] is not None:
                    facts[f"{prefix}_{field}"] = dict(
                        value_cny=agent._finite(row["current"]), period_end=statement["period_end"],
                        section=section, field=field, column="current", scope=agent.SCOPE,
                        currency="CNY", source_refs=row["source_refs"])
    result.update(facts=facts, source_manifest=source_binding, issuer_name=manifest["issuer_name"],
                  scope=agent.SCOPE, currency="CNY", source_adapter_version=VERSION,
                  parent_operating_cash_observations=observations, matched_historical_second_half=derived,
                  historical_financing_observations=[agent._historical_financing_range(s) for s in statements],
                  schema_version="parent-note-grid-agent-source-facts-v1", forecast_scenarios_present=False,
                  quarterly_parent_source=None)
    result["input_fingerprint"] = sha256(agent._canonical(result)).hexdigest()
    return result
