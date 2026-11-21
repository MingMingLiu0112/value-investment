"""Read-only first-input projection for verified partial parent cash layouts.

The native fact replay authenticates the two original sources. A sparse printed
comparative remains unknown; this projection never treats it as zero or as a
reconciled cash statement.
"""
from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path

from .first_input_parent_cash_observation_v1 import (
    LIMITATIONS, _read_bound, observe_first_input_parent_cash,
)
from .parent_cash_observation_v2 import extract_numbered_parent_cash_statement
from .parent_cash_layout_observation import observe_parent_cash_rows
from ...infrastructure.filings.first_research_fact_replay_v1 import replay_first_research_facts
from ...infrastructure.filings.first_research_fact_replay_v2 import replay_first_research_facts as replay_v2_facts
from ...infrastructure.filings.pdf_text import extract_pages
from ..product.common import require_inside


NUMBERED_SOURCE_HASHES = frozenset({
    ("2025-12-31", "7a2e321f049401fd34dfbf8c22964e804d16f077ece9382791cb2b2ce0c74676"),
    ("2026-06-30", "33fbc65e9bc5c41a80d2cc5f8ae0eaa2990424c81bb93b90029ccdb05e092ade"),
})
PARTIAL_SOURCE_HASHES = frozenset({
    ("2025-12-31", "474905deeaf0f875fc0a1b097a626c0c7852c427faadc5d7fc7816cbf45ea288"),
    ("2026-06-30", "0e10aa26be46b1cf3cd03f06e834c7fb98d5dd0d661b96f8fddd4af7e846a4f6"),
})


def observe_first_input_parent_cash_by_source(*, root: Path, native_facts_binding: dict,
                                              now: datetime) -> dict:
    """Select a parser by pinned original identity, never by security code.

    Explicit source pairs select their verified partial-table contracts.
    Any matching pair must go through its native replay; a replay failure cannot
    fall back to the legacy parser.
    """
    manifest = json.loads(_read_bound(Path(root).resolve(), native_facts_binding))
    sources = manifest.get("sources")
    if (isinstance(sources, list) and len(sources) == 2 and
            {(source.get("report_period"), source.get("sha256"))
             for source in sources if isinstance(source, dict)} == NUMBERED_SOURCE_HASHES):
        return observe_numbered_first_input_parent_cash(
            root=root, native_facts_binding=native_facts_binding, now=now)
    if (isinstance(sources, list) and len(sources) == 2 and
            {(source.get("report_period"), source.get("sha256"))
             for source in sources if isinstance(source, dict)} == PARTIAL_SOURCE_HASHES):
        return observe_partial_first_input_parent_cash(
            root=root, native_facts_binding=native_facts_binding, now=now)
    return observe_first_input_parent_cash(
        root=root, native_facts_binding=native_facts_binding, now=now)


def observe_partial_first_input_parent_cash(*, root: Path, native_facts_binding: dict,
                                            now: datetime) -> dict:
    """Keep verified printed parent rows; blank FX and financing stay unknown."""
    root = Path(root).resolve()
    base = dict(schema_version="first-input-parent-cash-observation-v2",
                status="UNASSESSABLE", symbol=None, action="no_order",
                formal_eligibility=False, whole_statement_reconciled=False,
                future_cash_proven=False, periods=[], ttm_flows={},
                source_bindings=[], unknown_fields=[], limitations=list(LIMITATIONS))
    try:
        manifest = json.loads(_read_bound(root, native_facts_binding))
        base["symbol"] = manifest.get("symbol")
        if (manifest.get("financial_basis") != "2026-06-30" or
                {(source.get("report_period"), source.get("sha256"))
                 for source in manifest.get("sources", [])} != PARTIAL_SOURCE_HASHES):
            raise ValueError("PARTIAL_FIRST_INPUT_SOURCE_PAIR_INVALID")
        replay = replay_v2_facts(root=root, binding=native_facts_binding, now=now)
        if (replay["symbol"] != manifest["symbol"] or replay["action"] != "no_order" or
                len(replay["sources"]) != 2):
            raise ValueError("PARTIAL_FIRST_INPUT_REPLAY_INVALID")
        statements = {}
        refs = []
        for source in replay["sources"]:
            path = require_inside(root, root / source["path"], "partial first-input original")
            observed = observe_parent_cash_rows(
                pages=extract_pages(path), symbol=replay["symbol"],
                issuer_name=replay["issuer_name"], period=source["report_period"])
            if sha256(path.read_bytes()).hexdigest() != source["sha256"]:
                raise ValueError("PARTIAL_FIRST_INPUT_SOURCE_CHANGED_DURING_PARSE")
            statements[source["report_period"]] = observed
            refs.append(dict(source_id=source["id"], path=source["path"],
                             sha256=source["sha256"], source_url=source["source_url"],
                             report_period=source["report_period"]))
        annual, interim = statements["2025-12-31"], statements["2026-06-30"]
        closing = annual["rows"]["closing_cash_and_equivalents_cny"]["columns"][0]["value"]
        opening = interim["rows"]["opening_cash_and_equivalents_cny"]["columns"][0]["value"]
        if closing != opening:
            raise ValueError("PARTIAL_FIRST_INPUT_CASH_CONTINUITY_INVALID")
        unknown = {period: dict(observed["unknown_fields"],
                                fx_cny="NOT_IN_PARTIAL_OBSERVATION_CONTRACT")
                   for period, observed in statements.items()}
        base.update(status="SOURCE_REPLAYED_PARTIAL_PARENT_CASH_OBSERVATIONS",
                    periods=[dict(report_period=period, rows=statements[period]["rows"],
                                  unknown_fields=unknown[period])
                             for period in ("2025-12-31", "2026-06-30")],
                    unknown_fields=unknown,
                    source_bindings=[dict(native_facts_binding), *refs],
                    limitation="Printed parent cash rows only; blank FX and financing columns remain unknown.")
    except (OSError, ValueError, KeyError, TypeError, IndexError, AttributeError) as error:
        base.update(reason=str(error), periods=[], source_bindings=[], unknown_fields=[])
    return base


def observe_numbered_first_input_parent_cash(*, root: Path, native_facts_binding: dict,
                                             now: datetime) -> dict:
    root = Path(root).resolve()
    base = dict(schema_version="first-input-parent-cash-observation-v2",
                status="UNASSESSABLE", symbol=None, action="no_order",
                formal_eligibility=False, whole_statement_reconciled=False,
                future_cash_proven=False, periods=[], ttm_flows={},
                source_bindings=[], unknown_fields=[], limitations=list(LIMITATIONS))
    try:
        raw = _read_bound(root, native_facts_binding)
        manifest = json.loads(raw)
        base["symbol"] = manifest.get("symbol")
        if (manifest.get("financial_basis") != "2026-06-30" or
                {(source.get("report_period"), source.get("sha256"))
                 for source in manifest.get("sources", [])} != NUMBERED_SOURCE_HASHES):
            raise ValueError("NUMBERED_FIRST_INPUT_IDENTITY_OR_BASIS_INVALID")
        replay = replay_first_research_facts(root=root, binding=native_facts_binding, now=now)
        if (replay["symbol"] != manifest["symbol"] or replay["action"] != "no_order" or
                {source["report_period"] for source in replay["sources"]} !=
                {"2025-12-31", "2026-06-30"} or len(replay["sources"]) != 2):
            raise ValueError("NUMBERED_FIRST_INPUT_SOURCE_SET_INVALID")
        statements = {}
        refs = []
        for source in replay["sources"]:
            path = require_inside(root, root / source["path"], "numbered first-input original")
            statement = extract_numbered_parent_cash_statement(
                pages=extract_pages(path), symbol=replay["symbol"],
                issuer_name=replay["issuer_name"], period=source["report_period"])
            if sha256(path.read_bytes()).hexdigest() != source["sha256"]:
                raise ValueError("NUMBERED_FIRST_INPUT_SOURCE_CHANGED_DURING_PARSE")
            statements[source["report_period"]] = statement
            refs.append(dict(source_id=source["id"], path=source["path"],
                             sha256=source["sha256"], source_url=source["source_url"],
                             report_period=source["report_period"]))
        annual = statements["2025-12-31"]
        interim = statements["2026-06-30"]
        closing = annual["balances"][0].get("closing_cash_and_equivalents_cny")
        opening = interim["balances"][0].get("opening_cash_and_equivalents_cny")
        if closing is None or opening is None or closing != opening:
            raise ValueError("NUMBERED_FIRST_INPUT_CASH_CONTINUITY_INVALID")
        unknown = {period: statement["unknown_fields"] for period, statement in statements.items()}
        base.update(status="SOURCE_REPLAYED_PARTIAL_PARENT_CASH_OBSERVATIONS",
                    periods=[dict(report_period=period, rows=statements[period]["rows"],
                                  balances=statements[period]["balances"],
                                  unknown_fields=unknown[period])
                             for period in ("2025-12-31", "2026-06-30")],
                    unknown_fields=unknown,
                    source_bindings=[dict(native_facts_binding), *refs],
                    limitation="Printed parent cash rows only; unknown columns prevent full TTM and reconciliation.")
    except (OSError, ValueError, KeyError, TypeError, IndexError, AttributeError) as error:
        base.update(reason=str(error), periods=[], source_bindings=[], unknown_fields=[])
    return base
