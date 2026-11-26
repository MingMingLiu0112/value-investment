"""Replay the sealed Yili sensitivity with one hypothetical 2027 payout."""

from copy import deepcopy
from datetime import date
from decimal import Decimal, localcontext
from hashlib import sha256
import json
from pathlib import Path

from ...domain.valuation import direct_parent_owner_cash_v2 as engine
from ...infrastructure.filings.interim_dividend_resolution import parse_interim_dividend_resolution
from ...infrastructure.filings.official_pdf import validate_pdf_original
from ...infrastructure.filings.pdf_text import extract_pages
from ...infrastructure.filings.sse_capital_checkpoint_v1 import parse_sse_capital_checkpoint
from ..product.common import require_inside

VERSION = "yili-interim-payout-stress-v1"
SCOPE = "CONDITIONAL_SENSITIVITY_NOT_CURRENT_VALUATION"
F2_STATUS = "NOT_EVALUATED_FOR_THIS_SENSITIVITY"
PREDECESSOR = "ff2279b53dc6209e97776e94ee94200e412cb76ed42c88901a91f32a44f028b3"
PROPOSAL = {
    "path": "runtime/public-evidence/600887-q3-dividend-20261111-v1/dividend-proposal-2026-10-30.pdf",
    "sha256": "e32dfd4a2f8bf61d77d3bc61052ad0ff489b822fcc188ae4e4717933c22609d7",
}
RESOLUTION = {
    "path": "runtime/f2-600887-egm-update-20261121T015202691652Z/600887-1225681447.pdf",
    "sha256": "b98fd6c8dfb862bd5a4ceede5c51bb8c67c25ef1e76297000f106e2a3e94a462",
}


def _check_hash(path, digest):
    raw = path.read_bytes()
    if sha256(raw).hexdigest() != digest:
        raise ValueError("YILI_PAYOUT_STRESS_SOURCE_CHANGED")
    return raw


def _pages(root, binding):
    path = require_inside(root / "runtime", root / binding["path"], "Yili dividend original")
    _check_hash(path, binding["sha256"])
    validate_pdf_original(path)
    pages = extract_pages(path)
    _check_hash(path, binding["sha256"])
    return pages


def _compile(case):
    try:
        return engine.compile_direct_owner_cash_path_v2(
            opening=case["opening"], years=case["years"], terminal=case["terminal"],
            ordinary_shares="6325360667", cost_of_equity="0.10",
            scope=engine.SCOPE, currency="CNY",
        )
    except ValueError as error:
        if not str(error).startswith((
            "DIRECT_OWNER_UNFUNDED_CASH_REQUIREMENT:",
            "DIRECT_OWNER_SCHEDULED_DISTRIBUTION_REQUIRES_BORROWING_OR_CASH:",
            "DIRECT_OWNER_SCHEDULED_DISTRIBUTION_EXCEEDS_CAPACITY:",
        )):
            raise
        return {"error": str(error)}


def _conditional_years(years, amount):
    if [row["year"] for row in years] != [2027, 2028, 2029] or any(
        Decimal(row["scheduled_owner_distribution_cny"]) != 0 for row in years
    ):
        raise ValueError("YILI_PAYOUT_STRESS_PREDECESSOR_SCHEDULE_CHANGED")
    rows = deepcopy(years)
    rows[0]["scheduled_owner_distribution_cny"] = str(amount)
    return rows


def replay_yili_interim_payout_stress(*, root: Path, predecessor_path: Path):
    """Cold-replay verified originals and the pinned predecessor without writing."""
    root = root.resolve()
    path = require_inside(root.parent, predecessor_path, "Yili payout stress predecessor")
    predecessor = json.loads(_check_hash(path, PREDECESSOR))
    if (predecessor["scope"] != SCOPE or predecessor["action"] != "no_order"
            or predecessor["f2_status"] != F2_STATUS):
        raise ValueError("YILI_PAYOUT_STRESS_PREDECESSOR_SCOPE_INVALID")
    proposal = parse_sse_capital_checkpoint(
        _pages(root, PROPOSAL), symbol="600887", published_date=date(2026, 10, 30),
    )
    resolution = parse_interim_dividend_resolution(
        _pages(root, RESOLUTION), symbol="600887", published=date(2026, 11, 21),
    )
    if (proposal["kind"] != "INTERIM_PROPOSAL_DATED_SHARES"
            or proposal["period_end"] != "2026-10-22"
            or resolution["fiscal_year"] != 2026 or resolution["meeting_date"] != "2026-11-20"
            or resolution["decision"] != "APPROVED"):
        raise ValueError("YILI_PAYOUT_STRESS_DISCLOSURES_UNMATCHED")
    with localcontext() as context:
        context.prec = 48
        eligible = Decimal(proposal["issued_shares"]) - Decimal(proposal["treasury_shares"])
        amount = eligible * Decimal(proposal["proposed_cash_per_share_cny"])
    cases = {}
    for name, old in predecessor["cases"].items():
        if _compile(old) != old["result"]:
            raise ValueError("YILI_PAYOUT_STRESS_PREDECESSOR_REPLAY_MISMATCH")
        # The scheduled slot is used only in this isolated arithmetic. It
        # reserves owner cash ahead of optional payouts without letting new
        # financing fund the stress. The receipt makes no payment assertion.
        case = {key: deepcopy(old[key]) for key in ("opening", "terminal")}
        case["years"] = _conditional_years(old["years"], amount)
        case["result"] = _compile(case)
        cases[name] = case
    return dict(
        schema_version=VERSION, scope=SCOPE, action="no_order", formal_eligibility=False,
        f2_status=F2_STATUS, valuation_basis=predecessor["valuation_basis"],
        predecessor_binding=dict(path=path.relative_to(root.parent).as_posix(), sha256=PREDECESSOR),
        source_bindings=dict(proposal=deepcopy(PROPOSAL), resolution=deepcopy(RESOLUTION)),
        implementation_sha256={
            module.stem: sha256(module.read_bytes()).hexdigest()
            for module in map(Path, (__file__, engine.__file__))
        },
        cash_assumption=dict(
            classification="HYPOTHETICAL_OWNER_DISTRIBUTION_STRESS", year=2027,
            gross_amount_cny=str(amount), eligible_shares_at_proposal_reference=str(eligible),
            gross_per_share_cny=proposal["proposed_cash_per_share_cny"],
            reference_share_date=proposal["period_end"],
            resolution_meeting_date=resolution["meeting_date"],
            resolution_published_date=resolution["published_date"],
            actual_payment_verified=False, implementation_verified=False,
            actual_payment_date=None, actual_record_date=None,
        ),
        cases=cases,
    )

