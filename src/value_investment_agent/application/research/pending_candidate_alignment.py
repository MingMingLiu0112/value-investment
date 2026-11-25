"""Read-only evidence alignment for a recomputed, unapproved research candidate.

Reuse native quote/coverage/validity/bridge contracts. Publication coverage is
not effective corporate-action coverage. No date rolling or price adjustment.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal, localcontext
import json
import re
import unicodedata
from urllib.parse import urlparse

from ...event_scan import event_scan_from_payload
from ...model_validity import evaluate_model_validity
from ...price_bridge import bridge_with_quote
from ...quote_session_conversion import quote_snapshot_from_bundle_file
from ...quote_snapshot import QuoteSnapshot, QUOTE_STATUS_PENDING_EXTERNAL_DATA
from ...research_artifact_codecs import ValuationResultCodec
from ..product.common import load_json_object, sha256_file
from ..product.daily_event_observation import (
    verify_retained_event_coverage, verify_retained_event_snapshot,
)
from ..product.quote_bridge import admit_quote_for_research

_event_pages_for_read = ContextVar("pending_alignment_event_pages", default=None)


@contextmanager
def pending_alignment_read_scope():
    """Share decoded text only across alignments within one public read."""
    token = _event_pages_for_read.set({})
    try:
        yield
    finally:
        _event_pages_for_read.reset(token)


SCHEMA = "pending-candidate-alignment-v1"
INPUT_SCHEMA = "pending-candidate-alignment-input-v1"
CONFIG_DIRECTORY = "config/pending-candidate-alignments-v1"
CHECK_IDS = ("quote", "capital_structure", "distributions", "material_events", "financial_updates")


def _number(value):
    if not isinstance(value, str):
        raise ValueError("DECIMAL_STRING_REQUIRED")
    number = Decimal(value)
    if not number.is_finite() or number < 0:
        raise ValueError("NONNEGATIVE_FINITE_AMOUNT_REQUIRED")
    return number


def _day(value):
    if not isinstance(value, str):
        raise ValueError("EXACT_DATE_STRING_REQUIRED")
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError("EXACT_DATE_STRING_REQUIRED")
    return parsed


def _shanghai_mixed_cash_schedule(compact_text):
    return (
        "委托中国结算上海分公司通过其资金清算系统" in compact_text
        and "自行发放对象" in compact_text
        and "红利由公司自行发放" in compact_text
    )


def _cash_terms(pages, symbol):
    """Narrow SSE cash scheme, including an explicitly excluded repurchase account.

    This verifies declared gross entitlement/schedule, not receipt, absence of
    amendments, or completeness of a period's corporate actions.
    """
    from decimal import ROUND_HALF_UP
    import unicodedata
    from ...corporate_actions import extract_distribution_dates
    from ...infrastructure.hotspot.cash_implementation import parse_cash_implementation_pages
    try:
        return parse_cash_implementation_pages(pages, symbol=symbol)
    except ValueError:
        pass
    compact = lambda s: re.sub(r"\s+", "", unicodedata.normalize("NFKC", s))
    if not pages or len(pages) > 16 or any(not p.strip() for p in pages):
        raise ValueError("UNSUPPORTED_CASH_IMPLEMENTATION_LAYOUT")
    text = compact("".join(pages))
    # This exact negative declaration excludes noncash distributions. Other
    # mentions still block; do not generally strip negation or infer its scope.
    cash_only_text = text.replace("本次权益分派不涉及派送红股或转增股本。", "")
    if (len(text) > 120000 or f"证券代码:{symbol}" not in compact(pages[0])
            or "权益分派实施公告" not in compact(pages[0]) or "差异化分红送转:否" not in text
            or any(word in cash_only_text for word in ("更正", "修订", "取消", "作废", "撤销", "送红股", "转增股本", "配股", "拆股", "合股", "股份转换"))):
        raise ValueError("UNSUPPORTED_CASH_IMPLEMENTATION_LAYOUT")
    scheme_heading = r"(?:\(三\)|3\.)分配方案:"
    schemes = [(i, m[1]) for i, p in enumerate(pages, 1)
               if (m := re.search(scheme_heading + r"(.*?)三、相关日期", compact(p)))]
    if not schemes:
        # Strip only a standalone physical page number equal to its own index.
        # Keep every other line and require both complete section boundaries.
        def without_edge_page_number(page, index):
            lines = page.strip().splitlines()
            if lines and lines[0].strip() == str(index):
                lines = lines[1:]
            if lines and lines[-1].strip() == str(index):
                lines = lines[:-1]
            return "\n".join(lines)
        joined = "".join(compact(without_edge_page_number(p, i))
                         for i, p in enumerate(pages, 1))
        spans = list(re.finditer(scheme_heading + r"(.*?)三、相关日期", joined))
        starts = [i for i, p in enumerate(pages, 1) if re.search(scheme_heading, compact(p))]
        if len(spans) == len(starts) == 1:
            schemes = [(starts[0], spans[0][1])]
    number = r"((?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)(?:\.[0-9]+)?)"
    terms = re.fullmatch(r"本次利润分配以方案实施前的公司总股本扣除回购专用账户内的股份"
        + number + r"股为基数,每股派发现金红利" + number
        + r"元\(含税\),共计派发现金红利" + number + r"元。", schemes[0][1]) if len(schemes) == 1 else None
    all_shares = False
    if terms is None and len(schemes) == 1:
        terms = re.fullmatch(r"本次利润分配以方案实施前的公司总股本" + number
            + r"股为基数,(?:向全体股东)?每股派发现金红利" + number
            + r"元\(含税\),共计派发现金红利" + number + r"元。", schemes[0][1])
        all_shares = terms is not None
    if terms is None:
        raise ValueError("UNSUPPORTED_CASH_IMPLEMENTATION_LAYOUT")
    shares, cash, total = (Decimal(v.replace(",", "")) for v in terms.groups())
    header = re.findall(r"A股每股现金红利([0-9.]+)元", compact(pages[0]))
    if (min(shares, cash, total) <= 0 or shares != shares.to_integral_value()
            or (shares * cash).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) != total
            or len(header) != 1 or Decimal(header[0]) != cash):
        raise ValueError("CASH_IMPLEMENTATION_HEADER_OR_TOTAL_MISMATCH")
    # Join only this exact wrapped header and row; preserve column mapping in
    # the existing native extractor, never locate dates by numeric proximity.
    tables = []
    for p in pages:
        normalized = unicodedata.normalize("NFKC", p)
        pattern = (r"股份类别\s*股权登记日\s*最后交易日\s*除权\(息\)\s*日\s*现金红利发放日"
                   r"\s*A\s*股\s+(20\d{2}/\d{1,2}/\d{1,2})\s+[-−—]\s+"
                   r"(20\d{2}/\d{1,2}/\d{1,2})\s+(20\d{2}/\d{1,2}/\d{1,2})")
        tables.append("\n".join("股份类别 股权登记日 最后交易日 除权(息)日 现金红利发放日\nA股 "
            + m[0] + " - " + m[1] + " " + m[2] for m in re.findall(pattern, normalized)))
    candidates = extract_distribution_dates(tables)
    dates = {}
    for field in ("record_date", "ex_date", "cash_payment_date"):
        values = {r["value"] for r in candidates if r["field"] == field}
        if len(values) != 1:
            raise ValueError("CASH_IMPLEMENTATION_DATE_TABLE_MISSING_OR_CONFLICTING")
        dates[field] = values.pop()
    publication = re.search(r"董事会(20\d{2})年(\d{1,2})月(\d{1,2})日$", text)
    if not publication or not dates["record_date"] < dates["ex_date"] <= dates["cash_payment_date"]:
        raise ValueError("CASH_IMPLEMENTATION_CHRONOLOGY_INVALID")
    published = date(*map(int, publication.groups())).isoformat()
    if published > dates["record_date"]:
        raise ValueError("CASH_IMPLEMENTATION_PUBLICATION_AFTER_RECORD")
    period_titles = re.findall(r"(20[0-9]{2})年(年度|中期|半年度)权益分派实施公告", compact(pages[0]))
    period = dict(zip(("distribution_year", "distribution_period"), period_titles[0])) if len(period_titles) == 1 else {}
    meetings = re.findall(
        r"本次利润分配方案经公司(20[0-9]{2})年([0-9]{1,2})月([0-9]{1,2})日的"
        r"(20[0-9]{2})年年度股东会审议通过。", text)
    if meetings:
        if len(meetings) != 1 or period.get("distribution_period") != "年度":
            raise ValueError("CASH_IMPLEMENTATION_ANNUAL_MEETING_AMBIGUOUS")
        meeting_year, meeting_month, meeting_day, fiscal_year = meetings[0]
        meeting = date(int(meeting_year), int(meeting_month), int(meeting_day))
        if fiscal_year != period["distribution_year"] or meeting.isoformat() > published:
            raise ValueError("CASH_IMPLEMENTATION_ANNUAL_MEETING_CONFLICT")
        period["referenced_approval_meeting_date"] = meeting.isoformat()
    return dict(parser_version=("sse-full-share-cross-page-cash-scheme-v1" if all_shares
                               else "sse-repurchase-excluded-gross-cash-scheme-v1"), symbol=symbol,
        cash_per_share=str(cash), eligible_distribution_shares=str(shares), total_gross_cash=str(total),
        published_date=published, **dates, **period, currency="CNY", body_terms_reconciled=True,
        term_pages=dict(scheme=[schemes[0][0]], chronology=sorted({r["page"] for r in candidates})),
        amendment_chain_verified=False, cash_payment_status="DECLARED_SCHEDULE_NOT_PROOF_OF_RECEIPT",
        action="no_order")



def _close_report_checkpoint(reports, end):
    """Collect exact ordinary-share observations and retain conflicting originals."""
    as_of = end.isoformat()
    anchors = [
        {"ordinary_shares": report["terms"]["ordinary_shares"],
         "evidence_binding": report["binding"], "published_date": report["published_date"]}
        for report in reports
        if report["status"] == "NATIVE_REPORT_FIELDS_VERIFIED"
        and report["terms"]["period_end"] == as_of
        and _day(report["published_date"]) <= end
    ]
    values = {_number(anchor["ordinary_shares"]) for anchor in anchors}
    if len(values) != 1:
        return dict(status=("EXACT_CLOSING_REPORT_ANCHORS_CONFLICT" if values
                            else "EXACT_CLOSING_REPORT_ANCHOR_MISSING"),
                    as_of=as_of, ordinary_shares=None, anchors=anchors,
                    continuity_to_opening_verified=False)
    return dict(status="EXACT_REPORT_DATE_SHARES_VERIFIED", as_of=as_of,
                ordinary_shares=str(next(iter(values))), evidence_binding=anchors[0]["evidence_binding"],
                anchors=anchors, continuity_to_opening_verified=False)


def _native_basis_fields(analysis, start, end, now, native_sources, read, cache, cash_rows):
    """Consume full native originals; never promote manual excerpts/empty lists.

    Reporting date, publication date and actual source availability are separate.
    Unsupported originals remain explicit. These facts do not certify absence of
    other opening pending schemes, amendments or intervening effective actions.
    """
    from ...infrastructure.filings.pdf_text import extract_pages
    from ...infrastructure.filings.official_pdf import validate_pdf_original
    from ...infrastructure.filings.interim_capital_distribution import parse_interim_capital_distribution
    from ...quote_sessions import CHINA

    result = dict(status="NO_SUPPORTED_SOURCE_FIELDS", reports=[], unresolved_sources=[],
        opening_pending_actions=dict(status="UNVERIFIED", known_completed_actions=[]),
        distribution_inclusion=dict(status="NOT_VERIFIED", comparisons=[]),
        historical_availability_proven=False, complete_action_coverage=False,
        materiality_approved=False, formal_eligibility=False, action="no_order")
    seen = set()
    for (path, sha, url), available in sorted(native_sources.items()):
        identity = (sha, url)
        if identity in seen:
            continue
        seen.add(identity)
        binding = dict(path=path, sha256=sha)
        source = dict(binding=binding, source_url=url, source_available_at=available)
        try:
            stamp = datetime.fromisoformat(available)
            parsed_url = urlparse(url)
            if (stamp.utcoffset() is None or stamp > now or parsed_url.scheme != "https"
                    or parsed_url.hostname != "static.cninfo.com.cn"
                    or not re.fullmatch(r"/finalpage/\d{4}-\d{2}-\d{2}/\d+\.PDF", parsed_url.path, re.I)):
                raise ValueError("NATIVE_FIELD_SOURCE_UNAVAILABLE")
            published = _day(parsed_url.path.split("/")[2])
            if published > end or published > stamp.astimezone(CHINA).date():
                raise ValueError("NATIVE_FIELD_PUBLICATION_AFTER_CUTOFF")
            original = read(binding)
            if sha not in cache:
                validate_pdf_original(original)
                cache[sha] = extract_pages(original)
            try:
                terms = parse_interim_capital_distribution(cache[sha], symbol=analysis["symbol"])
            except ValueError as legacy_error:
                # Dispatch unsupported layouts, never downgrade a contradiction
                # already discovered by the richer native parser.
                if str(legacy_error) not in {
                    "FULL_INTERIM_REPORT_IDENTITY_REQUIRED", "INTERIM_FIELD_MISSING_OR_AMBIGUOUS"
                }:
                    raise
                page_values = cache[sha].values() if isinstance(cache[sha], dict) else cache[sha]
                if any(re.search(r"三、\s*股份总数\s*[0-9]", unicodedata.normalize("NFKC", p)) for p in page_values):
                    raise
                from ...infrastructure.filings.sse_capital_checkpoint_v1 import parse_sse_capital_checkpoint
                checkpoint = parse_sse_capital_checkpoint(cache[sha], symbol=analysis["symbol"],
                                                        published_date=published.isoformat())
                checkpoint_end = _day(checkpoint["period_end"])
                if checkpoint_end > published:
                    raise ValueError("NATIVE_CHECKPOINT_AFTER_PUBLICATION")
                # A report saying the total AND structure did not change can
                # bridge the consumed prior-year ordinary-share anchor only.
                # It is not a same-day market share count or an action review.
                opening = str(analysis["consumed_operating_inputs"]["ordinary_shares"])
                bound_hashes = {b["sha256"] for b in analysis["source_bindings"]}
                anchored = any(a.get("field") == "ordinary_shares"
                    and a.get("period_end") == start.isoformat() and a.get("unit") == "shares"
                    and a.get("source_value") == opening
                    and any(s.get("id") == a.get("source_id") and s.get("sha256") in bound_hashes
                            for s in analysis.get("source_catalog", []))
                    for a in analysis.get("official_fact_anchors", []))
                bridged = (checkpoint.get("unchanged_report_period") is True and anchored
                    and checkpoint.get("period_start") == date(start.year+1, 1, 1).isoformat()
                    and start == date(start.year, 12, 31))
                checkpoint = dict(checkpoint,
                    ordinary_shares=opening if bridged else None,
                    inherited_opening_class_scope=bridged,
                    classification="DERIVED_FACT" if bridged else "FACT",
                    derivation="已消费的期初普通股股数，加上本报告期股份总数及股本结构未变的原件声明" if bridged else None,
                    continuity_after_period_end=False)
                result["reports"].append(dict(**source, terms=checkpoint,
                    published_date=published.isoformat(), consumed_opening_fact=False,
                    status="NATIVE_CAPITAL_CHECKPOINT_VERIFIED"))
                continue
            report_end = _day(terms["period_end"])
            if report_end > published:
                raise ValueError("NATIVE_REPORT_PERIOD_AFTER_PUBLICATION")
            fact_id = "cninfo:" + parsed_url.path.rsplit("/", 1)[1].split(".")[0]
            consumed = any(a.get("source_id") == fact_id and a.get("field") == "ordinary_shares"
                and a.get("period_end") == terms["period_end"] and a.get("unit") == "shares"
                and a.get("source_value") == terms["ordinary_shares"]
                for a in analysis.get("official_fact_anchors", [])) and any(
                    b["sha256"] == sha for b in analysis["source_bindings"])
            if report_end == start and (not consumed or Decimal(terms["ordinary_shares"])
                    != Decimal(analysis["consumed_operating_inputs"]["ordinary_shares"])):
                raise ValueError("NATIVE_REPORT_NOT_MATCHED_TO_CONSUMED_OPENING_FACT")
            report = dict(**source, terms=terms, published_date=published.isoformat(),
                consumed_opening_fact=consumed and report_end == start,
                status="NATIVE_REPORT_FIELDS_VERIFIED")
            result["reports"].append(report)
            if report["consumed_opening_fact"]:
                pending = result["opening_pending_actions"]
                pending["status"] = "KNOWN_BUYBACK_COMPLETED_OTHER_PENDING_SCHEMES_UNVERIFIED"
                pending["known_completed_actions"].append(dict(kind="BUYBACK_CANCELLATION",
                    shares=terms["cancelled_shares"], completed_by=terms["period_end"],
                    evidence_binding=binding, physical_pages=terms["term_pages"]["cancellation"]))
                for row in cash_rows:
                    cash_terms = row.get("native_terms")
                    if (cash_terms is None or _day(row["ex_date"]) > start
                            or _day(row["cash_payment_date"]) > start):
                        continue
                    with localcontext() as context:
                        context.prec = 80
                        difference = (Decimal(terms["declared_ordinary_dividend_cny"])
                                      - Decimal(cash_terms["total_gross_cash"]))
                    result["distribution_inclusion"]["comparisons"].append(dict(
                        distribution_id=row["id"], report_binding=binding,
                        implementation_evidence=deepcopy(row["evidence"]),
                        reported_dividend_cny=terms["declared_ordinary_dividend_cny"],
                        implementation_total_cny=cash_terms["total_gross_cash"],
                        difference_cny=str(difference),
                        status="AMOUNT_DIFFERENCE_REQUIRES_RECONCILIATION" if difference
                            else "AMOUNT_MATCH_NOT_MODEL_INCLUSION_PROOF",
                        price_deduction_applied="0"))
        except (OSError, ValueError, KeyError, TypeError, ArithmeticError) as error:
            # A successfully consumed cash implementation is not an unsupported
            # interim report, but still does not prove complete period coverage.
            if any(r.get("native_terms") is not None and any(
                    e["binding"]["sha256"] == sha and e["source_url"] == url
                    for e in r["evidence"]) for r in cash_rows):
                continue
            result["unresolved_sources"].append(dict(**source, reason=str(error)))
    if result["reports"]:
        result["status"] = "NATIVE_FIELDS_VERIFIED_CHAIN_INCOMPLETE"
    result["closing_capital"] = _close_report_checkpoint(result["reports"], end)
    if result["distribution_inclusion"]["comparisons"]:
        result["distribution_inclusion"]["status"] = "SOURCE_AMOUNTS_COMPARED_INCLUSION_UNVERIFIED"
    return result


def _verify_period_buyback_cancellation(row, *, symbol, before, after, end, cache, window_sources):
    """Check the supplied pair of issuer originals for one effective decrease."""
    from ...infrastructure.filings.opening_action_terms import parse_opening_action_terms
    from ...infrastructure.filings.operating_event_terms import parse_operating_event_terms

    proof = {"status": "NATIVE_CANCELLATION_PAIR_UNVERIFIED",
             "reason": "UNIQUE_OFFICIAL_PURCHASE_AND_CANCELLATION_REQUIRED"}
    refs = {(e["binding"]["path"], e["binding"]["sha256"], e["source_url"])
            for e in row["evidence"]}
    candidates, confirmations = [], []
    for key in sorted(refs & window_sources):
        path, sha, url = key
        published = _day(urlparse(url).path.split("/")[2])
        if published > end:
            continue
        for parser, expected_field, destination in (
                (parse_operating_event_terms, "scheduled_cancellation_date", candidates),
                (parse_opening_action_terms, "confirmed_cancellation_date", confirmations)):
            try:
                parsed = parser(cache[sha], symbol=symbol)
                terms = parsed["terms"]
            except ValueError:
                continue
            if (parsed["symbol"] == symbol and parsed["published_date"] == published.isoformat()
                    and expected_field in terms):
                destination.append((parsed, {"path": path, "sha256": sha}))
    if len(candidates) != 1 or len(confirmations) != 1:
        return proof
    purchase, purchase_ref = candidates[0]
    confirmation, confirmation_ref = confirmations[0]
    planned, actual = purchase["terms"], confirmation["terms"]
    if (purchase_ref["sha256"] == confirmation_ref["sha256"]
            or planned.get("purchase_state") != "COMPLETED"
            or planned.get("cancellation_state") != "SCHEDULED_UNCONFIRMED"
            or actual["completion_notice_on"] != purchase["published_date"]
            or planned["scheduled_cancellation_date"] != row["effective_date"]
            or actual["confirmed_cancellation_date"] != row["effective_date"]
            or not _day(purchase["published_date"]) <= _day(row["effective_date"]) <= _day(confirmation["published_date"])
            or _number(actual["cancelled_shares"]) != before - after
            or Decimal(planned["cumulative_purchased_shares"]) != before - after
            or Decimal(planned["planned_post_cancellation_shares"]) != after
            or _number(actual["issued_shares"]) != after):
        proof["reason"] = "CANCELLATION_PAIR_TERMS_OR_RUNNING_SHARE_COUNT_MISMATCH"
        return proof
    return dict(status="NATIVE_BUYBACK_CANCELLATION_MATCHED", reason=None,
                effective_date=row["effective_date"], confirmation_date=confirmation["published_date"],
                capital_as_of=actual["capital_as_of"], shares_before=str(before), shares_after=str(after),
                purchase_binding=purchase_ref, confirmation_binding=confirmation_ref,
                confirmation_physical_pages=confirmation["term_pages"]["confirmed_cancellation"])


def _covered_share_cancellations(announced, action_rows, *, symbol, start, end, read, cache):
    """Match executed cancellations disclosed in the event window against the replayed ledger."""
    from ...infrastructure.filings.pdf_text import extract_pages
    from ...infrastructure.filings.official_pdf import validate_pdf_original
    from ...quote_sessions import CHINA
    from ...infrastructure.filings.opening_action_terms import parse_opening_action_terms

    observed_cancellations, gaps = [], []
    for identity, event in announced.items():
        title = event.get("title", "")
        cancellation_notice = "回购" in title and any(
            term in title for term in ("注销完成", "完成回购注销", "调整回购股份注销后")
        )
        distribution_adjustment = all(term in title for term in ("调整", "利润分配方案", "每股分红金额"))
        if not (cancellation_notice or distribution_adjustment):
            continue
        try:
            source, = event["evidence_refs"]
            original = read(dict(path=source["path"], sha256=source["sha256"]))
            validate_pdf_original(original)
            pages = cache.get(source["sha256"])
            if pages is None:
                pages = extract_pages(original)
            # A price-only adjustment can have the same title as a cancellation
            # confirmation. Only rule it out when the original has readable text.
            if distribution_adjustment and not cancellation_notice:
                compact = "".join("".join(pages).split())
                if compact and "注销" not in compact:
                    continue
            parsed = parse_opening_action_terms(pages, symbol=symbol)
            terms = parsed["terms"]
            publication = datetime.fromisoformat(event["published_at"]).astimezone(CHINA).date()
            effective = _day(terms["confirmed_cancellation_date"])
            if _day(parsed["published_date"]) != publication or effective > publication:
                raise ValueError("CANCELLATION_PUBLICATION_OR_EFFECTIVE_DATE_MISMATCH")
        except (ValueError, KeyError):
            gaps.append("COVERED_CANCELLATION_ORIGINAL_UNRESOLVED: " + identity)
            observed_cancellations.append(dict(announcement_id=identity, status="ORIGINAL_UNRESOLVED"))
            continue
        if not start < effective <= end:
            continue
        binding = dict(path=source["path"], sha256=source["sha256"])
        matches = [row["id"] for row in action_rows
                   if row.get("native_cancellation", {}).get("status") == "NATIVE_BUYBACK_CANCELLATION_MATCHED"
                   and row["effective_date"] == effective.isoformat()
                   and row["native_cancellation"]["confirmation_binding"] == binding]
        status = "MATCHED" if len(matches) == 1 else "LEDGER_MISMATCH"
        if status != "MATCHED":
            gaps.append("COVERED_CANCELLATION_REQUIRES_UNIQUE_LEDGER_ROW: " + identity)
        observed_cancellations.append(dict(announcement_id=identity, status=status,
            evidence_binding=binding, effective_date=effective.isoformat(), matched_ledger_ids=matches))
    return observed_cancellations, gaps


def _continuous_publication_window(windows, start, end):
    next_day = start.toordinal()
    intervals = sorted((_day(window["scan_from"]).toordinal(), _day(window["scan_to"]).toordinal())
                       for window in windows)
    for first, last in intervals:
        if first > next_day:
            return False
        next_day = max(next_day, last + 1)
        if next_day > end.toordinal():
            return True
    return False

def _cross_date_row_proofs(*, start, end, action_rows, cash_rows, cancellations,
                           cash_implementations, announcements, dispositions, complete_ids,
                           conflicts, publication_window_covered):
    """Match ledger rows to replayed native proofs, without granting economic closure."""
    ledger = {row["id"]: ("SHARE_ACTION", row) for row in action_rows}
    ledger.update({row["id"]: ("CASH_DISTRIBUTION", row) for row in cash_rows
                   if _day(row["ex_date"]) <= end
                   and start < max(_day(row["ex_date"]), _day(row["cash_payment_date"]))})
    proof_rows, by_ledger, by_original = [], {}, {}
    for kind, observations in (("SHARE_ACTION", cancellations), ("CASH_DISTRIBUTION", cash_implementations)):
        for observation in observations:
            identity = observation["announcement_id"]
            binding = observation.get("evidence_binding")
            announcement = announcements.get(identity)
            originals = announcement[2] if announcement else ()
            digest = binding.get("sha256") if isinstance(binding, dict) else None
            sources = [url for url, original_digest in originals if digest is not None and digest == original_digest
                       and binding.get("source_url", url) == url]
            source_url = sources[0] if len(sources) == 1 else None
            ids = observation.get("matched_ledger_ids", [])
            proof = dict(kind=kind, announcement_id=identity, evidence_binding=binding, source_url=source_url,
                         native_status=observation["status"], ledger_ids=ids)
            index = len(proof_rows)
            proof_rows.append(proof)
            if source_url is not None:
                by_original.setdefault((identity, source_url, digest), []).append(index)
            if (not publication_window_covered or identity not in complete_ids
                    or identity in conflicts or source_url is None
                    or dispositions.get(identity) != kind or len(ids) != 1 or observation["status"] not in {
                        "MATCHED", "ENTITLEMENT_MATCHED_PAYMENT_UNRESOLVED"
                    }):
                continue
            row_id, = ids
            if row_id in ledger and ledger[row_id][0] == kind:
                by_ledger.setdefault(row_id, []).append(index)

    duplicate_proofs = {i for indices in by_original.values() if len(indices) > 1 for i in indices}
    matched, used = [], set()
    for row_id, (kind, row) in ledger.items():
        indices = by_ledger.get(row_id, [])
        if len(indices) != 1 or indices[0] in duplicate_proofs:
            continue
        index, = indices
        used.add(index)
        match = dict(ledger_id=row_id, **proof_rows[index])
        if kind == "CASH_DISTRIBUTION":
            match.update(cash_payment_proven=False, model_inclusion=row["model_inclusion"])
        matched.append(match)

    unmatched_ledger = sorted(set(ledger) - {row["ledger_id"] for row in matched})
    unmatched_proofs = [row for index, row in enumerate(proof_rows) if index not in used]
    ambiguous_ledger = sorted(row_id for row_id, indices in by_ledger.items() if len(indices) > 1)
    status = "MATCHED" if matched and not (unmatched_ledger or unmatched_proofs) else (
        "UNRESOLVED" if ledger or proof_rows else "NO_IN_PERIOD_ROWS")
    return dict(status=status, matched_rows=matched, unmatched_ledger_ids=unmatched_ledger,
                unmatched_native_proofs=unmatched_proofs, ambiguous_ledger_ids=ambiguous_ledger,
                duplicate_native_proofs=[proof_rows[i] for i in sorted(duplicate_proofs)])


def _cross_date_action_facts(*, ledger_binding, ledger, start, end, windows, action_rows,
                             cash_rows, cancellations, cash_implementations):
    """Project replayed announcement facts without certifying interval continuity."""
    complete = [window for window in windows
                if window.get("source_integrity_verified") is True
                and window["full_calendar_window_elapsed"] is True
                and window.get("coverage_status") == "COMPLETE"]
    covered = _continuous_publication_window(complete, start, end)
    dispositions = {row["announcement_id"]: row["disposition"]
                    for row in ledger["reviewed_documents"]}
    complete_ids = {event["announcement_id"] for window in complete
                    for event in window["announcements"]}
    announcements = {}
    original_owners = {}
    conflicts = set()
    for window in windows:
        for event in window["announcements"]:
            identity = event["announcement_id"]
            originals = sorted({(ref["source_url"], ref["sha256"]) for ref in event["evidence_refs"]})
            metadata = (event.get("title"), event.get("published_at"), originals)
            for original in originals:
                owner = original_owners.setdefault(original, identity)
                if owner != identity:
                    conflicts.update((owner, identity))
            if identity in announcements and announcements[identity] != metadata:
                conflicts.add(identity)
            announcements[identity] = metadata

    actions_by_id = {row["id"]: row for row in action_rows}
    cash_by_id = {row["id"]: row for row in cash_rows}
    facts_by_announcement = {}
    purchases = {}
    for observation in cancellations:
        if observation["status"] != "MATCHED" or observation["announcement_id"] not in announcements:
            continue
        row_id, = observation["matched_ledger_ids"]
        proof = actions_by_id[row_id]["native_cancellation"]
        facts_by_announcement.setdefault(observation["announcement_id"], []).append(dict(
            kind="CONFIRMED_BUYBACK_CANCELLATION", ledger_id=row_id, native_proof=proof))
        purchase = proof["purchase_binding"]
        purchases.setdefault((purchase["path"], purchase["sha256"]), []).append(row_id)
    for window in complete:
        for event in window["announcements"]:
            identity = event["announcement_id"]
            refs = event["evidence_refs"]
            if len(refs) != 1:
                continue
            for row_id in purchases.get((refs[0]["path"], refs[0]["sha256"]), []):
                fact = dict(kind="PURCHASE_LINKED_TO_CONFIRMED_CANCELLATION", ledger_id=row_id)
                facts = facts_by_announcement.setdefault(identity, [])
                if fact not in facts:
                    facts.append(fact)
    for observation in cash_implementations:
        if (observation["status"] not in {"MATCHED", "ENTITLEMENT_MATCHED_PAYMENT_UNRESOLVED"}
                or observation["announcement_id"] not in announcements):
            continue
        row_id, = observation["matched_ledger_ids"]
        row = cash_by_id[row_id]
        facts_by_announcement.setdefault(observation["announcement_id"], []).append(dict(
            kind="CASH_ENTITLEMENT_AND_SCHEDULE", ledger_id=row_id, terms=observation["terms"],
            cash_payment_proven=False, model_inclusion=row["model_inclusion"]))

    rows = []
    for identity, (title, published_at, originals) in sorted(announcements.items()):
        facts = facts_by_announcement.get(identity, [])
        disposition = dispositions.get(identity)
        status = "UNRESOLVED"
        if identity in conflicts:
            status = "ANNOUNCEMENT_METADATA_CONFLICT"
        elif identity in complete_ids and len(facts) == 1:
            kind = facts[0]["kind"]
            expected = "CASH_DISTRIBUTION" if kind == "CASH_ENTITLEMENT_AND_SCHEDULE" else "SHARE_ACTION"
            if disposition == expected:
                status = "SCHEDULE_TERMS_ONLY" if expected == "CASH_DISTRIBUTION" else "NATIVE_TERMINAL_MATCHED"
        rows.append(dict(announcement_id=identity, title=title, published_at=published_at,
                         originals=[dict(source_url=url, sha256=sha) for url, sha in originals],
                         disposition=disposition, status=status, facts=facts))

    return dict(schema_version="cross-date-action-facts-v1", action="no_order",
                candidate_binding=deepcopy(ledger["candidate_binding"]),
                input_descriptor_sha256=ledger["input_descriptor_sha256"],
                ledger_binding=deepcopy(ledger_binding), valuation_date=start.isoformat(),
                comparison_date=end.isoformat(), publication_window_covered=covered,
                coverage_observation_bindings=[deepcopy(w["observation_binding"]) for w in complete],
                announcements=rows, row_proof_reconciliation=_cross_date_row_proofs(
                    start=start, end=end, action_rows=action_rows, cash_rows=cash_rows,
                    cancellations=cancellations, cash_implementations=cash_implementations,
                    announcements=announcements, dispositions=dispositions,
                    complete_ids=complete_ids, conflicts=conflicts, publication_window_covered=covered),
                effective_action_continuity_proven=False,
                current_price_basis_compatible=False,
                status="BLOCKED", reason_codes=[
                    *([] if covered else ["COMPLETE_ACTION_PUBLICATION_WINDOW_REQUIRED"]),
                    *(["ANNOUNCEMENT_METADATA_CONFLICT"] if conflicts else []),
                    *(["NATIVE_ANNOUNCEMENT_DISPOSITIONS_UNRESOLVED"]
                      if not rows or any(row["status"] != "NATIVE_TERMINAL_MATCHED" for row in rows) else []),
                    "NATIVE_INTERVAL_CONTINUITY_AND_EXACT_MODEL_CONSUMPTION_REQUIRED",
                ])


def _attach_confirmed_unlock_facts(reconciliation, windows, capital_events):
    """Join already replayed issuer confirmations to the exact cross-date notice."""
    facts = (reconciliation or {}).get("cross_date_action_facts")
    if facts is None:
        return
    completed_ids = {
        event["announcement_id"] for window in windows
        if window["observation_binding"] in facts["coverage_observation_bindings"]
        for event in window["announcements"]
    }
    rows = {row["announcement_id"]: row for row in facts["announcements"]}
    unlocks = {}
    for event in capital_events:
        if event["classification"] == "ISSUER_CONFIRMED_RESTRICTED_SHARE_UNLOCK":
            unlocks.setdefault(event["announcement_id"], []).append(event)
    for identity, events in unlocks.items():
        if len(events) != 1 or identity not in completed_ids:
            continue
        event, = events
        notice = rows[identity]
        confirmation = event["issuer_reported_listing_confirmation"]
        report_id = confirmation["announcement_id"]
        if report_id == identity or report_id not in completed_ids:
            continue
        report = rows[report_id]
        if (notice["status"] != "UNRESOLVED" or notice["facts"]
                or notice["disposition"] not in {None, "NO_CAPITAL_OR_DISTRIBUTION_EFFECT"}
                or notice["title"] != event["title"] or notice["published_at"] != event["published_at"]
                or notice["originals"] != [dict(source_url=event["source_url"],
                                             sha256=event["source_binding"]["sha256"])]
                or report["status"] == "ANNOUNCEMENT_METADATA_CONFLICT"
                or report["originals"] != [dict(source_url=confirmation["source_url"],
                                             sha256=confirmation["binding"]["sha256"])]):
            continue
        notice["facts"] = [dict(kind="ISSUER_CONFIRMED_RESTRICTED_SHARE_UNLOCK",
                                native_proof=deepcopy(event))]
        notice["status"] = "NATIVE_TERMINAL_MATCHED"

    if rows and all(row["status"] == "NATIVE_TERMINAL_MATCHED" for row in rows.values()):
        unresolved = "NATIVE_ANNOUNCEMENT_DISPOSITIONS_UNRESOLVED"
        if unresolved in facts["reason_codes"]:
            facts["reason_codes"].remove(unresolved)


def _market_value_share_corroboration(binding, *, symbol, comparison_date, now, read):
    """Replay closing market-value arithmetic without certifying registered capital."""
    from fractions import Fraction

    from ...quote_sessions import CHINA

    observed = datetime.fromisoformat(binding["observed_at"])
    expected = (
        f"https://yunhq.sse.com.cn:32042/v1/sh1/snap/{symbol}"
        "?select=name%2Clast%2Cprev_close%2CtotalShares%2CnonRestrictedShares%2CtotalValue%2Ctradephase"
    )
    if (binding["source_url"] != expected or observed.utcoffset() is None
            or observed > now or observed.astimezone(CHINA).date() != comparison_date):
        raise ValueError("SSE_CLOSING_VALUE_SOURCE_OR_CLOCK_INVALID")
    ref = binding["response_binding"]
    path = read(ref)
    if path.stat().st_size > 16384:
        raise ValueError("SSE_CLOSING_VALUE_RESPONSE_TOO_LARGE")
    packet = json.loads(path.read_bytes(), parse_float=Decimal)
    time = packet.get("time")
    cutoff = int(observed.astimezone(CHINA).strftime("%H%M%S"))
    if (packet.get("code") != symbol or packet.get("date") != int(comparison_date.strftime("%Y%m%d"))
            or type(time) is not int or not 150000 <= time <= cutoff
            or time % 100 >= 60 or (time // 100) % 100 >= 60):
        raise ValueError("SSE_CLOSING_VALUE_SYMBOL_OR_SESSION_MISMATCH")
    snap = packet.get("snap")
    if (not isinstance(snap, list) or len(snap) != 7 or not isinstance(snap[6], str)
            or snap[6].strip() != "E110"
            or not all(isinstance(value, Decimal) and value.is_finite() and value > 0
                       for value in (snap[1], snap[5]))):
        raise ValueError("SSE_CLOSING_VALUE_FIELDS_INVALID")
    implied = Fraction(snap[5]) / Fraction(snap[1])
    if implied.denominator != 1:
        raise ValueError("SSE_CLOSING_VALUE_SHARE_COUNT_NOT_INTEGRAL")
    return dict(status="CLOSE_MARKET_VALUE_DERIVED_SHARE_CORROBORATION", share_count=implied.numerator,
                date=comparison_date.isoformat(), closing_quote_cny=str(snap[1]),
                raw_total_value_cny=str(snap[5]), evidence_binding=deepcopy(ref),
                exact_registry_count=False, continuity_verified=False, action="no_order")


def _reconcile(root, analysis, ref, end, windows, now, read, source_windows=(), *,
               closing_export=None, verified_pdf_pages=None):
    """Replay source-anchored public research arithmetic, never approve materiality.

    Unknown opening pending state/closing shares remain explicit gaps. Every
    original excerpt is re-extracted; listed cash paid before valuation is retained
    but never deducted again. Effective share changes/cash inside the interval
    require a separately recomputed valuation, not a mechanical price adjustment.
    """
    from ...corporate_actions import validate_cash_distribution
    from ...infrastructure.filings.pdf_text import extract_pages
    from ...infrastructure.filings.official_pdf import validate_pdf_original

    from ...quote_sessions import CHINA

    ledger = load_json_object(read(ref), "candidate public basis reconciliation")
    start = _day(analysis["valuation_date"])
    if (ledger["schema_version"] != "pending-candidate-basis-reconciliation-v1"
            or ledger["candidate_binding"] != analysis["review_binding"]["candidate_binding"]
            or ledger["input_descriptor_sha256"] != analysis["input_descriptor_sha256"]
            or _day(ledger["valuation_date"]) != start
            or end is None or _day(ledger["comparison_date"]) != end or end < start
            or ledger["currency"] != "CNY" or ledger["share_basis"] != "ordinary_share_unadjusted"):
        raise ValueError("RECONCILIATION_EXACT_BASIS_MISMATCH")
    cache = {} if verified_pdf_pages is None else verified_pdf_pages
    evidence = []
    native_sources = {}
    for source in analysis.get("source_catalog", []):
        if (source.get("kind") == "official_issuer_filing"
                and (source.get("issuer_identity") or {}).get("security_code") == analysis["symbol"]):
            key = (source["local_path"], source["sha256"], source["location"])
            native_sources[key] = source["source_available_at"]
    window_sources = {
        (source["path"], source["sha256"], source["source_url"])
        for window in windows if window.get("source_integrity_verified") is True
        for announcement in window["announcements"]
        for source in announcement["evidence_refs"]
    }
    for window in [*windows, *source_windows]:
        for announcement in window["announcements"]:
            for source in announcement["evidence_refs"]:
                key = (source["path"], source["sha256"], source["source_url"])
                native_sources[key] = window["acquired_at"]

    def anchors(rows, *, numbers=(), dates=(), consumed_issuer_verified=False):
        if not isinstance(rows, list) or not rows:
            raise ValueError("PUBLIC_ORIGINAL_EXCERPTS_REQUIRED")
        texts = []
        for item in rows:
            binding = item["binding"]
            path = read(binding)
            stamp = datetime.fromisoformat(item["available_at"])
            key = (binding["path"], binding["sha256"], item["source_url"])
            if key not in native_sources:
                raise ValueError("ANCHOR_NOT_BOUND_TO_NATIVE_OFFICIAL_SOURCE")
            native_available = datetime.fromisoformat(native_sources[key])
            if native_available.utcoffset() is None or native_available > now:
                raise ValueError("NATIVE_ANCHOR_SOURCE_UNAVAILABLE")
            url = urlparse(item["source_url"])
            if (stamp.utcoffset() is None or stamp > now
                    or url.scheme != "https" or url.hostname != "static.cninfo.com.cn"
                    or not re.fullmatch(r"/finalpage/\d{4}-\d{2}-\d{2}/\d+\.PDF", url.path, re.I)
                    or _day(url.path.split("/")[2]) > stamp.astimezone(CHINA).date()):
                raise ValueError("OFFICIAL_RECONCILIATION_SOURCE_UNAVAILABLE")
            if binding["sha256"] not in cache:
                validate_pdf_original(path)
                cache[binding["sha256"]] = extract_pages(path)
            pages = cache[binding["sha256"]]
            page, excerpt = item["physical_page"], item["excerpt"]
            if (type(page) is not int or not 1 <= page <= len(pages)
                    or not isinstance(excerpt, str) or not excerpt.strip()
                    or "".join(excerpt.split()) not in "".join(pages[page - 1].split())
                    or (not consumed_issuer_verified and not re.search(
                        r"(?:证券|公司|股票)代码[:：]?" + analysis["symbol"], "".join(pages[0].split())))):
                raise ValueError("RECONCILIATION_EXCERPT_OR_ISSUER_MISMATCH")
            texts.append(excerpt)
            if binding not in evidence:
                evidence.append(deepcopy(binding))
        text = " ".join(texts)
        numeric = {Decimal(n.replace(",", "")) for n in re.findall(r"\d[\d,]*(?:\.\d+)?", text)}
        if any(value not in numeric for value in numbers):
            raise ValueError("RECONCILIATION_AMOUNT_ABSENT_FROM_ORIGINAL")
        compact = "".join(text.split())
        for day in dates:
            forms = (day.isoformat(), f"{day.year}年{day.month}月{day.day}日",
                     f"{day.year}年{day.month:02}月{day.day:02}日", day.strftime("%Y/%m/%d"),
                     f"{day.year}/{day.month}/{day.day}", f"{day.year}-{day.month}-{day.day}")
            if not any(form in compact for form in forms):
                raise ValueError("RECONCILIATION_DATE_ABSENT_FROM_ORIGINAL")
        return text

    opening = ledger["opening_shares"]
    opening_value = _number(opening["value"])
    if (_day(opening["as_of"]) != start or opening_value <= 0
            or opening_value != opening_value.to_integral_value()
            or opening_value != Decimal(analysis["consumed_operating_inputs"]["ordinary_shares"])):
        raise ValueError("OPENING_SHARES_DIFFER_FROM_CONSUMED_MODEL")
    consumed_excerpt = analysis.get("consumed_opening_capital_excerpt")
    if consumed_excerpt is not None and consumed_excerpt["period_end"] == start.isoformat():
        expected_excerpt = {key: value for key, value in consumed_excerpt.items() if key != "period_end"}
    else:
        expected_excerpt = None
    # The cold compiler already verifies the period against the report headers.
    # Only the exact consumed fact may use that period instead of a date printed
    # in the share-count sentence itself.
    exact_consumed_excerpt = expected_excerpt is not None and opening["evidence"] == [expected_excerpt]
    anchors(opening["evidence"], numbers=[opening_value],
            dates=[] if exact_consumed_excerpt else [start], consumed_issuer_verified=exact_consumed_excerpt)
    original_hashes = {s["sha256"] for s in analysis["source_bindings"]}
    valuation_capital_anchors = {
        anchor["source_id"] for anchor in analysis.get("official_fact_anchors", [])
        if anchor.get("field") == "ordinary_shares"
        and anchor.get("source_value") == opening["value"]
        and anchor.get("unit") == "shares" and anchor.get("period_end") == start.isoformat()
    }
    consumed_capital_originals = {
        (source["location"], source["sha256"])
        for source in analysis.get("source_catalog", [])
        if source.get("kind") == "official_issuer_filing"
        and (source.get("issuer_identity") or {}).get("security_code") == analysis["symbol"]
        and source["sha256"] in original_hashes
    }
    capital_source_ids = {
        anchor["source_id"] for anchor in analysis.get("official_fact_anchors", [])
        if anchor.get("field") == "ordinary_shares"
    }
    catalogued_urls = {url for url, _ in consumed_capital_originals}
    native_opening = True
    for excerpt in opening["evidence"]:
        source_url, digest = excerpt["source_url"], excerpt["binding"]["sha256"]
        source_id = "cninfo:" + urlparse(source_url).path.rsplit("/", 1)[1].split(".")[0]
        exact_original = (source_url, digest) in consumed_capital_originals
        if (digest not in original_hashes or source_id not in capital_source_ids
                or (source_url in catalogued_urls and not exact_original)):
            raise ValueError("OPENING_CAPITAL_SOURCE_NOT_CONSUMED")
        native_opening = native_opening and exact_original and source_id in valuation_capital_anchors
    actions, cash = ledger["share_actions"], ledger["distributions"]
    if not isinstance(actions, list) or not isinstance(cash, list):
        raise ValueError("RECONCILIATION_ACTION_ARRAYS_REQUIRED")
    ids, total, action_rows = set(), opening_value, []
    for row in sorted(actions, key=lambda item: _day(item["effective_date"])):
        if not isinstance(row["id"], str) or not row["id"] or row["id"] in ids:
            raise ValueError("UNIQUE_ACTION_ID_REQUIRED")
        ids.add(row["id"])
        effective, shares = _day(row["effective_date"]), _number(row["shares"])
        if not start < effective <= end or row["kind"] not in {"INCREASE", "DECREASE"} or shares <= 0 or shares != shares.to_integral_value():
            raise ValueError("UNSUPPORTED_EFFECTIVE_SHARE_ACTION")
        anchors(row["evidence"], numbers=[shares], dates=[effective])
        before = total
        with localcontext() as context:
            context.prec = 80
            total += shares if row["kind"] == "INCREASE" else -shares
        if total <= 0:
            raise ValueError("NONPOSITIVE_RECONCILED_SHARE_COUNT")
        action = deepcopy(row)
        if row["kind"] == "DECREASE":
            action["native_cancellation"] = _verify_period_buyback_cancellation(
                row, symbol=analysis["symbol"], before=before, after=total, end=end,
                cache=cache, window_sources=window_sources)
        action_rows.append(action)
    if total <= 0:
        raise ValueError("NONPOSITIVE_RECONCILED_SHARE_COUNT")
    closing, closing_value = ledger.get("closing_shares"), None
    gaps = []
    if closing_export is not None:
        closing_value = _number(closing_export["ordinary_a_shares"])
        if _day(closing_export["comparison_date"]) != end or closing_value != total:
            raise ValueError("SZSE_CAPITAL_EXPORT_ROLLFORWARD_DISAGREEMENT")
        evidence.append(deepcopy(closing_export["evidence_binding"]))
    if closing is None and closing_export is None:
        gaps.append("CLOSING_SHARE_COUNT_UNVERIFIED")
    elif closing is not None:
        closing_value = _number(closing["value"])
        closing_date = _day(closing["as_of"])
        if closing_date != end or closing_value != total:
            raise ValueError("SHARE_ROLLFORWARD_DOES_NOT_RECONCILE")
        anchors(closing["evidence"], numbers=[closing_value], dates=[closing_date])
    period_cash, cash_rows = Decimal(0), []
    native_cash_originals = set()
    for row in cash:
        if not isinstance(row["id"], str) or not row["id"] or row["id"] in ids:
            raise ValueError("UNIQUE_ACTION_ID_REQUIRED")
        ids.add(row["id"])
        amount = validate_cash_distribution(row)
        ex, payment, record = (_day(row[key]) for key in ("ex_date", "cash_payment_date", "record_date"))
        anchors(row["evidence"], numbers=[_number(row["cash_amount"])], dates=[record, ex, payment])
        parsed, parse_error, entitlement = None, None, None
        hashes = {e["binding"]["sha256"] for e in row["evidence"]}
        if len(hashes) == 1:
            try:
                parsed = _cash_terms(cache[next(iter(hashes))], analysis["symbol"])
            except ValueError as error:
                parse_error = str(error)
                from ...infrastructure.filings.szse_cash_entitlement import parse_mixed_cash_entitlement
                try:
                    entitlement = parse_mixed_cash_entitlement(cache[next(iter(hashes))], symbol=analysis["symbol"])
                except ValueError:
                    pass
        if entitlement is not None:
            if (Decimal(entitlement["cash_per_share"]) != amount
                    or any(entitlement[k] != row[k] for k in ("record_date", "ex_date"))
                    or entitlement["clearing_house_scheduled_payment_date"] != row["cash_payment_date"]
                    or any("/finalpage/" + entitlement["published_date"] + "/" not in e["source_url"]
                           for e in row["evidence"])):
                raise ValueError("CASH_LEDGER_DIFFERS_FROM_NATIVE_IMPLEMENTATION_FIELDS")
            parse_error = entitlement["cash_payment_status"]
            gaps.append(parse_error)
        if parsed is not None:
            if (Decimal(parsed["cash_per_share"]) != amount
                    or any(parsed[k] != row[k] for k in ("record_date", "ex_date", "cash_payment_date"))
                    or any('/finalpage/' + parsed["published_date"] + '/' not in e["source_url"] for e in row["evidence"])):
                raise ValueError("CASH_LEDGER_DIFFERS_FROM_NATIVE_IMPLEMENTATION_FIELDS")
        # Each supported native parser describes one implementation per original.
        # Ledger IDs and local archive paths are not economic action identities.
        # Reject aliases before summing or consuming a model-inclusion closure,
        # including distributions before valuation (outside the covered window).
        if parsed is not None or entitlement is not None:
            original_hash, = hashes
            if original_hash in native_cash_originals:
                raise ValueError("DUPLICATE_NATIVE_CASH_IMPLEMENTATION_ORIGINAL")
            native_cash_originals.add(original_hash)
        # Ex-date entitlement and payment timing are independent. Pending
        # payment must not hide an entitlement inside (valuation, comparison].
        ex_in_period = start < ex <= end
        if ex_in_period:
            with localcontext() as context:
                context.prec = 80
                period_cash += amount
        if entitlement is not None:
            treatment = "MIXED_PAYMENT_SCOPE_REQUIRES_REVIEW"
        elif payment > end:
            treatment = "PENDING_PAYMENT_REQUIRES_REVIEW"
            gaps.append("PENDING_DISTRIBUTION_PAYMENT")
        elif ex <= start and payment <= start:
            treatment = "BEFORE_VALUATION_DATE_ALREADY_OUTSIDE_INTERVAL"
        elif ex_in_period:
            treatment = "IN_PERIOD_MODEL_INCLUSION_REQUIRES_RECOMPUTATION"
        else:
            treatment = "OPENING_EX_ENTITLEMENT_PAID_IN_PERIOD_REQUIRES_REVIEW"
            gaps.append("OPENING_DISTRIBUTION_ENTITLEMENT_UNRECONCILED")
        cash_rows.append(dict(**deepcopy(row), period_treatment=treatment,
            ex_entitlement_in_period=ex_in_period,
            payment_pending_at_comparison=None if entitlement is not None else payment > end,
            arithmetic_cash_per_share=str(amount), verified_cash_per_share=str(amount) if parsed or entitlement else None,
            field_semantics_status=("NATIVE_IMPLEMENTATION_FIELDS_VERIFIED" if parsed else
                "NATIVE_ENTITLEMENT_ONLY_VERIFIED" if entitlement else
                "PUBLIC_RESEARCH_ARITHMETIC_NOT_NATIVE_FIELD_VERIFIED"),
            native_terms=parsed, field_semantics_reason=parse_error,
            **({"native_entitlement_only": entitlement} if entitlement is not None else {}),
            price_deduction_applied="0", model_inclusion=treatment if parsed and ex <= start and payment <= start else "NOT_NATIVE_VERIFIED"))
    payable_observation = None
    if exact_consumed_excerpt and any(row["ex_entitlement_in_period"] for row in cash_rows):
        opening_binding = expected_excerpt["binding"]
        opening_pages = cache[opening_binding["sha256"]]
        headings = [i for i, page in enumerate(opening_pages) if re.search(
            r"(?m)^\s*2、母公司资产负债表\s*\r?\n单位：元\s*\r?\n项目\s+期末余额\s+期初余额", page)]
        if len(headings) == 1:
            index = headings[0]
            section = "\n".join(opening_pages[index:index + 4]).split("2、母公司资产负债表", 1)[1]
            parent, separator, _ = section.partition("3、合并利润表")
            payable = list(re.finditer(
                r"(?m)^应付股利[ \t]+([0-9,]+\.[0-9]{2})(?:[ \t]+[0-9,]+\.[0-9]{2})?[ \t\r]*$", parent))
            in_closing_column = False
            if separator and len(payable) == 1:
                from ...infrastructure.filings.first_research_fact_replay_v1 import _native_column

                amount = payable[0][1]
                active_pages = [i + 1 for i in range(index, min(index + 4, len(opening_pages)))
                                if payable[0][0].strip() in opening_pages[i]]
                if len(active_pages) == 1:
                    try:
                        in_closing_column = _native_column(
                            read(opening_binding), active_pages[0], amount,
                            {"header_page": index + 1, "labels": ["期末余额", "期初余额"]},
                        ) == 0
                    except ValueError:
                        pass
            if in_closing_column:
                payable_observation = dict(
                    status="FIRST_INPUT_OPENING_PARENT_DIVIDEND_PAYABLE_REQUIRES_SETTLEMENT_REVIEW",
                    parent_dividend_payable_cny=amount.replace(",", ""), physical_page=active_pages[0],
                    as_of=start.isoformat(), original_binding=deepcopy(opening_binding),
                    cash_payment_proven=False, model_inclusion_verified=False,
                    disallow_automatic_second_equity_deduction=True, action="no_order",
                )
    unconsumed_period_cash = period_cash
    distribution_closures = analysis.get("consumed_implemented_distributions", [])
    if distribution_closures is not None:
        if not isinstance(distribution_closures, list):
            raise ValueError("CONSUMED_IMPLEMENTED_DISTRIBUTIONS_INVALID")
        matched_rows = set()
        for closure in distribution_closures:
            if (not isinstance(closure, dict) or closure.get("status") != "PASS"
                    or closure.get("reason_code") != "IMPLEMENTED_DISTRIBUTION_INCLUDED_IN_MODEL"
                    or closure.get("scope") != "EXACT_IMPLEMENTED_DISTRIBUTION_ONLY_NOT_PERIOD_COMPLETENESS"
                    or closure.get("action") != "no_order"
                    or closure.get("formal_eligibility") is not False):
                raise ValueError("CONSUMED_IMPLEMENTED_DISTRIBUTION_CLOSURE_INVALID")
            matches = [index for index, cash_row in enumerate(cash_rows)
                if cash_row["ex_entitlement_in_period"]
                and not cash_row["payment_pending_at_comparison"]
                and cash_row["native_terms"] is not None
                and Decimal(cash_row["native_terms"]["total_gross_cash"])
                    == Decimal(closure.get("total_cny", "NaN"))
                and cash_row["cash_payment_date"] == closure.get("paid_date")
                and Decimal(cash_row["arithmetic_cash_per_share"])
                    == Decimal(closure.get("per_share_cny", "NaN"))
                and any(e.get("binding") == closure.get("original_binding")
                        for e in cash_row.get("evidence", []))]
            if len(matches) != 1 or matches[0] in matched_rows:
                raise ValueError("CONSUMED_IMPLEMENTED_DISTRIBUTION_NOT_UNIQUELY_RECONCILED")
            index = matches[0]
            matched_rows.add(index)
            cash_rows[index]["model_inclusion"] = "EXACT_IMPLEMENTED_DISTRIBUTION_COLD_RECOMPUTED_IN_CANDIDATE"
            cash_rows[index]["period_treatment"] = "IN_PERIOD_MODEL_INCLUSION_VERIFIED"
            with localcontext() as context:
                context.prec = 80
                unconsumed_period_cash -= Decimal(cash_rows[index]["arithmetic_cash_per_share"])
    pending = ledger.get("opening_pending_actions")
    if pending is None:
        gaps.append("OPENING_PENDING_ACTION_STATE_UNVERIFIED")
    else:
        if (_day(pending["as_of"]) != start or not isinstance(pending["pending_action_ids"], list)
                or any(not isinstance(v, str) or not v for v in pending["pending_action_ids"])
                or not isinstance(pending["rationale"], str) or not pending["rationale"].strip()):
            raise ValueError("OPENING_PENDING_ACTION_REVIEW_INVALID")
        opening_text = anchors(pending["evidence"], dates=[start])
        # An empty list alone never certifies absence. Require an explicit public
        # statement denying outstanding capital/distribution implementations.
        if not pending["pending_action_ids"] and not any(term in "".join(opening_text.split()) for term in
                ("无尚未实施的股本变动及利润分配方案", "不存在尚未实施的股本变动及利润分配方案")):
            gaps.append("OPENING_NO_PENDING_ACTION_STATEMENT_NOT_PROVEN")
        if pending["pending_action_ids"]:
            gaps.append("OPENING_PENDING_ACTION_CHAIN_REQUIRES_REVIEW")
    documents = ledger["reviewed_documents"]
    if not isinstance(documents, list):
        raise ValueError("PUBLIC_REVIEW_DOCUMENT_ARRAY_REQUIRED")
    announced = {}
    announcement_sources = {}
    for window in windows:
        for row in window["announcements"]:
            identity = row["announcement_id"]
            sources = frozenset((ref.get("source_url"), ref["sha256"]) for ref in row["evidence_refs"])
            # Overlapping windows may archive the same PDF to different local paths.
            if identity in announcement_sources and announcement_sources[identity] != sources:
                raise ValueError("PUBLIC_ACTION_ANNOUNCEMENT_ORIGINAL_CONFLICT")
            announcement_sources[identity] = sources
            announced[identity] = row
    reviewed = set()
    for item in documents:
        identity = item["announcement_id"]
        if identity not in announced or identity in reviewed:
            raise ValueError("PUBLIC_REVIEW_SCAN_IDENTITY_MISMATCH")
        if item["disposition"] not in {"NO_CAPITAL_OR_DISTRIBUTION_EFFECT", "SHARE_ACTION", "CASH_DISTRIBUTION", "UNRESOLVED"}:
            raise ValueError("UNSUPPORTED_PUBLIC_RECONCILIATION_DISPOSITION")
        if not isinstance(item["rationale"], str) or not item["rationale"].strip():
            raise ValueError("PUBLIC_RECONCILIATION_RATIONALE_REQUIRED")
        anchors(item["evidence"])
        announced_hashes = {s["sha256"] for s in announced[identity]["evidence_refs"]}
        if any(e["binding"]["sha256"] not in announced_hashes for e in item["evidence"]):
            raise ValueError("PUBLIC_REVIEW_NOT_BOUND_TO_ANNOUNCED_ORIGINAL")
        reviewed.add(identity)
        if item["disposition"] == "UNRESOLVED":
            gaps.append("PUBLIC_ACTION_REVIEW_UNRESOLVED: " + identity)
        disposition = item["disposition"]
        if disposition in {"SHARE_ACTION", "CASH_DISTRIBUTION"}:
            matching_rows = actions if disposition == "SHARE_ACTION" else cash
            if not any(e["binding"]["sha256"] in announced_hashes
                       for row in matching_rows for e in row["evidence"]):
                gaps.append("REVIEWED_ACTION_MISSING_LEDGER_ROW: " + identity)
    if reviewed != set(announced):
        gaps.append("PUBLIC_ACTION_REVIEW_DOES_NOT_COVER_ALL_ANNOUNCEMENTS")
    complete_windows = [window for window in windows
                        if window.get("source_integrity_verified") is True
                        and window["full_calendar_window_elapsed"] is True]
    if not _continuous_publication_window(complete_windows, start, end):
        gaps.append("ACTION_PUBLICATION_WINDOW_MISSING")
    if any(not w["full_calendar_window_elapsed"] for w in windows):
        gaps.append("ACTION_COVERAGE_IS_RETRIEVAL_SNAPSHOT_ONLY")
    # Derive listed cash schedules from the covered originals, independently
    # of the researcher-selected ledger rows and document classifications.
    observed_cash = []
    for identity, event in announced.items():
        title = event.get("title", "")
        suffixes = ("权益分派实施公告", "分红派息实施公告", "利润分配实施公告", "现金分红实施公告")
        if not any(suffix in title for suffix in suffixes):
            continue
        if not title.endswith(suffixes):
            gaps.append("COVERED_CASH_IMPLEMENTATION_LINEAGE_UNRESOLVED: " + identity)
            observed_cash.append(dict(announcement_id=identity, status="LINEAGE_UNRESOLVED"))
            continue
        sources = event["evidence_refs"]
        try:
            if len(sources) != 1:
                raise ValueError("SINGLE_CASH_IMPLEMENTATION_ORIGINAL_REQUIRED")
            source = sources[0]
            original = read(dict(path=source["path"], sha256=source["sha256"]))
            validate_pdf_original(original)
            pages = cache.get(source["sha256"])
            if pages is None:
                pages = extract_pages(original)
            term_field = "native_terms"
            payment_field = "cash_payment_date"
            try:
                terms = _cash_terms(pages, analysis["symbol"])
            except ValueError:
                from ...infrastructure.filings.szse_cash_entitlement import parse_mixed_cash_entitlement

                terms = parse_mixed_cash_entitlement(pages, symbol=analysis["symbol"])
                term_field = "native_entitlement_only"
                payment_field = "clearing_house_scheduled_payment_date"
            publication = datetime.fromisoformat(event["published_at"]).astimezone(CHINA).date()
            if _day(terms["published_date"]) != publication:
                raise ValueError("CASH_IMPLEMENTATION_PUBLICATION_MISMATCH")
        except (OSError, ValueError) as error:
            gaps.append("COVERED_CASH_IMPLEMENTATION_UNVERIFIED: " + identity)
            observed_cash.append(dict(announcement_id=identity, status="UNVERIFIED", reason=str(error)))
            continue
        ex, payment = (_day(terms[k]) for k in ("ex_date", payment_field))
        if ex > end or max(ex, payment) <= start:
            continue
        matches = [
            row for row in cash_rows
            if row.get(term_field) == terms and any(
                anchor["binding"]["sha256"] == source["sha256"]
                and anchor["source_url"] == source["source_url"] for anchor in row["evidence"]
            )
        ]
        status = "MATCHED"
        if len(matches) != 1:
            gaps.append("COVERED_CASH_IMPLEMENTATION_REQUIRES_UNIQUE_LEDGER_ROW: " + identity)
            status = "LEDGER_MISMATCH"
        elif term_field == "native_entitlement_only":
            status = "ENTITLEMENT_MATCHED_PAYMENT_UNRESOLVED"
        settlement = {}
        text = re.sub(r"\s+", "", "".join(pages))
        if _shanghai_mixed_cash_schedule(text):
            if status == "MATCHED":
                status = "ENTITLEMENT_MATCHED_PAYMENT_UNRESOLVED"
                gaps.extend(("SHANGHAI_CLEARING_DIVIDEND_PAYMENT_UNVERIFIED",
                             "ISSUER_DIRECT_DIVIDEND_PAYMENT_UNVERIFIED"))
            settlement = dict(settlement_scope="SHANGHAI_CLEARING_AND_ISSUER_DIRECT",
                              issuer_direct_payment_verified=False,
                              clearing_house_payment_verified=False)
        observed_cash.append(dict(announcement_id=identity, evidence_binding=deepcopy(source),
            status=status, terms=terms,
            matched_ledger_ids=[row["id"] for row in matches], **settlement))
    observed_cancellations, cancellation_gaps = _covered_share_cancellations(
        announced, action_rows, symbol=analysis["symbol"], start=start, end=end, read=read, cache=cache,
    )
    gaps.extend(cancellation_gaps)
    # Exact excerpts/number/date co-occurrence and researcher classifications
    # are not a sealed semantic consumer. No caller-provided review/NO_EFFECT or
    # empty pending list may establish effective-action coverage or price basis.
    native_fields = _native_basis_fields(analysis, start, end, now, native_sources, read, cache, cash_rows)
    for report in native_fields["reports"]:
        if report["binding"] not in evidence:
            evidence.append(deepcopy(report["binding"]))
    closing_capital = native_fields["closing_capital"]
    closing_status = closing_capital["status"]
    if closing_status == "EXACT_CLOSING_REPORT_ANCHOR_MISSING":
        if closing_export is None:
            gaps.append("EXACT_COMPARISON_DATE_NATIVE_CAPITAL_ANCHOR_MISSING")
        else:
            gaps.append("NATIVE_CLOSING_SHARES_OPENING_CONTINUITY_UNVERIFIED")
    elif closing_status == "EXACT_CLOSING_REPORT_ANCHORS_CONFLICT":
        gaps.append("EXACT_COMPARISON_DATE_NATIVE_CAPITAL_ANCHORS_CONFLICT")
    else:
        observed = _number(closing_capital["ordinary_shares"])
        closing_capital["rollforward_comparison"] = dict(
            status="MATCH" if observed == total else "CONFLICT",
            calculated_ordinary_shares=str(total), observed_ordinary_shares=str(observed))
        if observed != total:
            gaps.append("NATIVE_CLOSING_SHARE_COUNT_DIFFERS_FROM_ROLLFORWARD")
        gaps.append("NATIVE_CLOSING_SHARES_OPENING_CONTINUITY_UNVERIFIED")
    gaps.extend(["OPENING_PENDING_SCHEMES_AND_EFFECTIVE_ACTION_CHAIN_INCOMPLETE",
                 "PERIOD_DISTRIBUTION_COVERAGE_AND_MODEL_INCLUSION_UNVERIFIED"])
    if any(c["status"] == "AMOUNT_DIFFERENCE_REQUIRES_RECONCILIATION"
           for c in native_fields["distribution_inclusion"]["comparisons"]):
        gaps.append("REPORT_AND_IMPLEMENTATION_DIVIDEND_AMOUNT_DIFFER")
    if not native_opening:
        gaps.append("OPENING_SHARES_NOT_MATCHED_TO_NATIVE_FACT_ANCHOR")
    # At the identical valuation/close date there is no intervening interval.
    # Native opening facts can be reused without inventing an absence-of-actions
    # statement; full native event validity remains a separate mandatory gate.
    same_basis = (start == end and native_opening and not actions and period_cash == 0
        and all(r["native_terms"] is not None and _day(r["ex_date"]) <= start
                and _day(r["cash_payment_date"]) <= start for r in cash_rows)
        and bool(windows) and all(w.get("source_integrity_verified") is True
            and w["full_calendar_window_elapsed"] for w in windows)
        and any(_day(w["scan_from"]) <= start <= _day(w["scan_to"]) for w in windows))
    if same_basis:
        # Only the absent intervening interval is exempt. Explicit unresolved
        # reviews, pending schemes, amount conflicts and missing action rows
        # remain blockers even when the quote and valuation dates coincide.
        empty_interval_gaps = {
            "CLOSING_SHARE_COUNT_UNVERIFIED",
            "OPENING_PENDING_ACTION_STATE_UNVERIFIED",
            "OPENING_NO_PENDING_ACTION_STATEMENT_NOT_PROVEN",
            "EXACT_COMPARISON_DATE_NATIVE_CAPITAL_ANCHOR_MISSING",
            "NATIVE_CLOSING_SHARES_OPENING_CONTINUITY_UNVERIFIED",
            "OPENING_PENDING_SCHEMES_AND_EFFECTIVE_ACTION_CHAIN_INCOMPLETE",
            "PERIOD_DISTRIBUTION_COVERAGE_AND_MODEL_INCLUSION_UNVERIFIED",
        }
        gaps = [gap for gap in gaps if gap not in empty_interval_gaps]
        same_basis = not gaps
    rounded_capital = None
    if (snapshot_ref := ledger.get("rounded_capital_snapshot_binding")) is not None:
        from ...infrastructure.filings.sse_current_capital_snapshot_v1 import replay_sse_current_capital_snapshot

        observation = replay_sse_current_capital_snapshot(
            receipt_path=read(snapshot_ref), symbol=analysis["symbol"], as_of=now,
        )
        if _day(observation["trade_date"]) != end:
            raise ValueError("ROUNDED_CAPITAL_SNAPSHOT_COMPARISON_DATE_MISMATCH")
        within_range = observation["lower_bound_shares"] <= total <= observation["upper_bound_shares"]
        rounded_capital = dict(observation, rollforward_within_range=within_range,
                               evidence_binding=deepcopy(snapshot_ref))
        evidence.append(deepcopy(snapshot_ref))
        if not within_range:
            gaps.append("ROUNDED_CAPITAL_SNAPSHOT_CONFLICTS_WITH_ROLLFORWARD")
            same_basis = False
    market_value_capital = None
    if (market_binding := ledger.get("closing_market_value_observation")) is not None:
        market_value_capital = _market_value_share_corroboration(
            market_binding, symbol=analysis["symbol"], comparison_date=end, now=now, read=read,
        )
        consistent = market_value_capital["share_count"] == total
        market_value_capital["rollforward_matches"] = consistent
        evidence.append(market_value_capital["evidence_binding"])
        if not consistent:
            gaps.append("SSE_CLOSING_VALUE_IMPLIED_SHARES_CONFLICT_WITH_ROLLFORWARD")
            same_basis = False
    if same_basis:
        closing_value = opening_value
    compatible = same_basis
    arithmetic_complete = closing_value is not None
    if start < end:
        gaps.append("CROSS_DATE_NATIVE_CAPITAL_AND_DISTRIBUTION_CLOSURE_NOT_SUPPORTED")
    if actions:
        gaps.append("EFFECTIVE_SHARE_ACTION_REQUIRES_CANDIDATE_RECOMPUTATION")
    if any(row.get("native_cancellation", {}).get("status") == "NATIVE_CANCELLATION_PAIR_UNVERIFIED"
           for row in action_rows):
        gaps.append("PERIOD_DECREASE_NATIVE_CANCELLATION_UNVERIFIED")
    if unconsumed_period_cash:
        gaps.append("IN_PERIOD_CASH_FLOW_INCLUSION_REQUIRES_CANDIDATE_RECOMPUTATION")
    cross_date_facts = {}
    if start < end:
        cross_date_facts["cross_date_action_facts"] = _cross_date_action_facts(
            ledger_binding=ref, ledger=ledger, start=start, end=end, windows=windows,
            action_rows=action_rows, cash_rows=cash_rows, cancellations=observed_cancellations,
            cash_implementations=observed_cash,
        )
    return dict(status="RECONCILED" if same_basis else "PARTIAL", arithmetic_status="RECONCILED" if arithmetic_complete else "PARTIAL",
        scope="SOURCE_BOUND_PUBLIC_RESEARCH_ARITHMETIC_NOT_FIELD_OR_MATERIALITY_APPROVAL", action="no_order",
        opening_shares=str(opening_value), calculated_closing_shares=str(total),
        opening_shares_semantics="NATIVE_CONSUMED_FACT_MATCHED" if native_opening else "NOT_VERIFIED",
        closing_shares=str(closing_value) if closing_value is not None else None,
        share_actions=action_rows, distributions=cash_rows, period_cash_per_share=str(period_cash),
        unconsumed_period_cash_per_share=str(unconsumed_period_cash),
        opening_parent_dividend_payable=payable_observation,
        implemented_distribution_inclusion_complete=(
            period_cash > 0 and unconsumed_period_cash == 0
            and all(row["status"] == "MATCHED" for row in observed_cash)
        ),
        period_cash_coverage_complete=same_basis,
        native_basis_semantics_verified=same_basis,
        native_source_consumption=native_fields,
        covered_cash_implementations=observed_cash,
        covered_share_cancellations=observed_cancellations,
        szse_exact_closing_capital_observation=deepcopy(closing_export),
        rounded_capital_observation=rounded_capital,
        closing_market_value_corroboration=market_value_capital,
        engineering_gap=None if same_basis else (
            "已消费期初原件；跨日期股本连续性仍缺原生有效行动链消费者，不能仅补同日报告或人工无变动标志放行。"
            if native_fields["reports"] else "绑定原件尚未匹配已支持的正式中报股本及分配字段。"),
        current_price_basis_compatible=compatible, formal_eligibility=False,
        **cross_date_facts,
        reason_codes=list(dict.fromkeys(gaps)), evidence_bindings=[deepcopy(ref), *evidence])


def _check(name, status, reasons, explanation, refs=(), **details):
    return dict(id=name, status=status, reason_codes=list(reasons), explanation=explanation,
                evidence_bindings=deepcopy(list(refs)), details=details)


def _initial(analysis, now):
    return dict(schema_version=SCHEMA, status="BLOCKED", action="no_order",
        formal_eligibility=False, currentpricecomparison=False,
        valuation_date=analysis["valuation_date"], quote_date=None,
        evaluated_at=now.isoformat(), candidate_binding=deepcopy(analysis["review_binding"]["candidate_binding"]),
        input_descriptor_sha256=analysis["input_descriptor_sha256"],
        quote=dict(status="MISSING", current_price=None, quote_date=None,
            latest_completed_session=None, native_status=None, bundle_binding=None,
            reason_codes=["QUOTE_BINDING_MISSING"], explanation="未绑定本候选的合格行情原件。"),
        checks=[_check(name, "MISSING", [name.upper() + "_EVIDENCE_MISSING"],
            "缺少可重放证据，不能认定当前口径已对齐。") for name in CHECK_IDS],
        model_validity=None, price_bridge=None, reason_codes=[], evidence_bindings=[],
        explanation="原始估值日期保持不变；报价核验与经济口径、事件及模型有效性分别检查，不构成买卖或审批。")


def _qualified_quote(root, analysis, ref, now, read):
    path = read(ref)
    _, _, verdict = admit_quote_for_research(root, path, analysis["symbol"],
        analysis["research_as_of"], today=now)
    quote = quote_snapshot_from_bundle_file(path, root, symbol=analysis["symbol"],
        ref_id="candidate-alignment-quote-" + ref["sha256"],
        expected_sha256=ref["sha256"], require_current_b1=True)
    allowed = {"QUOTE_VERIFIED_FOR_RESEARCH_INPUT", "QUOTE_VERIFIED_BUT_RESEARCH_STALE",
               "HISTORICAL_VERIFIED_CLOSE_DISPLAY_ONLY"}
    reasons = list(quote.blockers)
    if verdict.get("status") not in allowed:
        reasons.append("NATIVE_QUOTE_ADMISSION_REJECTED: " + str(verdict.get("reason")))
    if (quote.status != "verified_close" or quote.quote_date is None
            or verdict.get("latest_completed_session") != quote.quote_date.isoformat()):
        reasons.append("QUOTE_NOT_LATEST_QUALIFIED_CLOSE")
    result = dict(status="BLOCKED" if reasons else "QUALIFIED",
        current_price=str(quote.current_price) if not reasons else None,
        quote_date=quote.quote_date.isoformat() if quote.quote_date else None,
        latest_completed_session=verdict.get("latest_completed_session"),
        native_status=verdict.get("status"), bundle_binding=deepcopy(ref),
        reason_codes=reasons,
        explanation="双源、官方交易日历及B1同交易日收盘后采集独立重放；通过只代表报价合格，不代表候选获批或当前低估。")
    return quote, result


def _event_windows(root, analysis, refs, now, read):
    if not isinstance(refs, list):
        raise ValueError("EVENT_OBSERVATION_BINDINGS_ARRAY_REQUIRED")
    windows, scans = [], []
    for ref in refs:
        observation = load_json_object(read(ref), "candidate event observation")
        start, end = date.fromisoformat(observation["scan_from"]), date.fromisoformat(observation["scan_to"])
        if type(observation["full_calendar_window_elapsed"]) is not bool:
            raise ValueError("EXPLICIT_EVENT_COVERAGE_MODE_REQUIRED")
        snapshot = not observation["full_calendar_window_elapsed"]
        verifier = verify_retained_event_snapshot if snapshot else verify_retained_event_coverage
        resource_options = ({"pdf_byte_limit": analysis["event_pdf_byte_limit"]}
                            if "event_pdf_byte_limit" in analysis else {})
        proof = verifier(root, observation, symbol=analysis["symbol"],
            required_from=start, required_to=end, now=now, **resource_options)
        scan = event_scan_from_payload(load_json_object(read(observation["scan_binding"]), "candidate event scan"))
        # Snapshot verifier replays originals; explicitly retain the closure for
        # the after-calculation byte recheck as well.
        for source in observation["source_bindings"]:
            read(dict(path=source["path"], sha256=source["sha256"]))
        scans.append(scan)
        windows.append(dict(observation_binding=deepcopy(ref), scan_binding=deepcopy(observation["scan_binding"]),
            scan_from=start.isoformat(), scan_to=end.isoformat(), acquired_at=observation["acquired_at"],
            source_integrity_verified=True, full_calendar_window_elapsed=not snapshot,
            coverage_status=proof["coverage_status"], announcement_count=len(scan.announcements),
            announcements=[item.as_policy() for item in scan.announcements],
            materiality_approved=False))
    return windows, scans



def _explicit_quarterly_financial_update(pages, symbol, binding):
    from ...infrastructure.filings.native_capital_observation_v1 import _compact
    from ...infrastructure.filings.quarterly_operating_facts_explicit_columns import (
        parse_explicit_columns_quarterly_facts,
    )

    currency_refs = [
        dict(binding, physical_page=index, excerpt=line.strip())
        for index, page in enumerate(pages, 1)
        for line in page.splitlines()
        if _compact(line) == "单位:元币种:人民币审计类型:未经审计"
    ]
    reported = parse_explicit_columns_quarterly_facts(
        pages, symbol=symbol, currency_basis=dict(currency="CNY", evidence_refs=currency_refs),
    )
    fields = {}
    for name in ("revenue", "parent_profit"):
        row = reported["fields"][name]
        fields[name + "_cny"] = dict(value=row["current"], comparative_value=row["comparative"],
            unit=row["currency"], scope=row["scope"], physical_page=row["physical_page"], excerpt=row["excerpt"])
    return dict(status="VERIFIED", period_start=reported["period_start"],
                period_end=reported["period_end"], comparative_start=reported["comparative_start"],
                comparative_end=reported["comparative_end"],
                period_basis="YEAR_TO_DATE_9M_NOT_SINGLE_QUARTER", fields=fields)


def _reported_unlock_completions(pages, period_end):
    date_text = r"(20[0-9]{2})年([0-9]{1,2})月([0-9]{1,2})日"
    pattern = re.compile(
        date_text + r"，公司披露了《([^《》]{1,240}解除限售股份上市流通的提示性公告)》，"
        r"公司[^。；]{1,240}限制性股票于" + date_text + r"上市流通。"
    )
    for physical_page, page in enumerate(pages, 1):
        for match in pattern.finditer(re.sub(r"\s+", "", page)):
            try:
                notice_date = date(*map(int, match.group(1, 2, 3)))
                listing_date = date(*map(int, match.group(5, 6, 7)))
            except ValueError:
                continue
            if notice_date <= listing_date <= _day(period_end):
                yield dict(notice_date=notice_date.isoformat(), listing_date=listing_date.isoformat(),
                           normalized_notice_title=match[4], physical_page=physical_page)


def _operating_events(analysis, windows, now, read, *, parser=None, page_cache=None):
    """Read official originals into research facts, never grant materiality."""
    from ...infrastructure.filings.pdf_text import extract_pages
    from ...infrastructure.filings.official_pdf import validate_pdf_original
    from ...infrastructure.filings.operating_event_terms import (
        BUYBACK_PLAN_TITLES, parse_buyback_cancellation_plan, parse_operating_event_terms,
    )
    from ...quote_sessions import CHINA
    allow_quarterly_report = parser is None
    parser = parser or parse_operating_event_terms
    rows = []
    seen = {}
    unlock_confirmations = []
    for window in windows:
        acquired = datetime.fromisoformat(window["acquired_at"])
        if acquired.utcoffset() is None or acquired > now:
            raise ValueError("OPERATING_EVENT_ACQUISITION_UNAVAILABLE")
        for event in window["announcements"]:
            identity = event["announcement_id"]
            fingerprint = (event["published_at"], event["title"],
                tuple(sorted((ref["sha256"], ref["source_url"]) for ref in event["evidence_refs"])))
            if identity in seen:
                if seen[identity] != fingerprint:
                    raise ValueError("CONFLICTING_OPERATING_EVENT_IDENTITY")
                continue
            seen[identity] = fingerprint
            facts, unresolved = [], []
            for source in event["evidence_refs"]:
                binding = dict(path=source["path"], sha256=source["sha256"])
                try:
                    url = urlparse(source["source_url"])
                    if (url.scheme != "https" or url.hostname != "static.cninfo.com.cn"
                            or not re.fullmatch(r"/finalpage/\d{4}-\d{2}-\d{2}/\d+\.PDF", url.path, re.I)
                            or url.path.rsplit("/", 1)[1].split(".")[0] != identity):
                        raise ValueError("OPERATING_EVENT_OFFICIAL_IDENTITY_MISMATCH")
                    published = _day(url.path.split("/")[2])
                    event_time = datetime.fromisoformat(event["published_at"])
                    if (event_time.utcoffset() is None or event_time > acquired
                            or published > acquired.astimezone(CHINA).date()
                            or event_time.astimezone(CHINA).date() != published):
                        raise ValueError("OPERATING_EVENT_PUBLICATION_MISMATCH")
                    original = read(binding)
                    # The bound read still verifies the file on every pass.
                    # Reuse text only within this alignment, for the same bytes.
                    key = (binding["path"], binding["sha256"])
                    pages = page_cache.get(key) if page_cache is not None else None
                    if pages is None:
                        validate_pdf_original(original)
                        pages = extract_pages(original)
                        if page_cache is not None and len(page_cache) < 128:
                            page_cache[key] = pages
                    pages = list(pages)
                    quarter_title = re.search(r"(20[0-9]{2})年(?:第)?三季度报告$", event["title"]) if allow_quarterly_report else None
                    if not allow_quarterly_report and event["title"].endswith("权益分派实施公告"):
                        distribution = _cash_terms(pages, analysis["symbol"])
                        terms = dict(event_type="PREVALUATION_DISTRIBUTION_SCHEDULE",
                            published_date=distribution["published_date"], effective_date=None,
                            summary="原件列示现金分配及发放日程。",
                            implication="按除息与约定发放日检查是否落在估值基准日前。",
                            affected_model_fields=[],
                            limitations=["实施日程不证明现金实收或其他行动已全部核销。"],
                            terms=distribution, action="no_order")
                    elif quarter_title:
                        from ...infrastructure.filings.native_capital_observation_v1 import parse_native_capital_observation
                        try:
                            update = _explicit_quarterly_financial_update(pages, analysis["symbol"], binding)
                        except ValueError:
                            observation = parse_native_capital_observation(pages, symbol=analysis["symbol"])
                            update = observation.get("financial_update") or {}
                            if observation.get("kind") != "q3":
                                raise ValueError("QUARTERLY_ORIGINAL_NOT_VERIFIED_FOR_EVENT")
                        if (update.get("status") != "VERIFIED"
                                or _day(update["period_end"]) > published
                                or quarter_title[1] != update["period_end"][:4]):
                            raise ValueError("QUARTERLY_ORIGINAL_NOT_VERIFIED_FOR_EVENT")
                        for completion in _reported_unlock_completions(pages, update["period_end"]):
                            unlock_confirmations.append(dict(completion, announcement_id=identity,
                                binding=deepcopy(binding), source_available_at=window["acquired_at"],
                                published_date=published.isoformat(), source_url=source["source_url"]))
                        revenue = update["fields"]["revenue_cny"]["value"]
                        profit = update["fields"]["parent_profit_cny"]["value"]
                        terms = dict(event_type="REPORTED_QUARTERLY_FINANCIAL_UPDATE",
                            published_date=published.isoformat(), effective_date=None,
                            summary=f"{update['period_start']}至{update['period_end']}累计营业收入{revenue}元、归母净利润{profit}元。",
                            implication="核对该候选的收入、利润及预测基期是否需要更新。",
                            financial_update=update, affected_model_fields=["revenue_cny", "parent_profit_cny"],
                            limitations=["前三季度累计披露，不视为单季、全年或预测。"], action="no_order")
                    elif allow_quarterly_report and event["title"].endswith(BUYBACK_PLAN_TITLES):
                        terms = parse_buyback_cancellation_plan(pages, symbol=analysis["symbol"])
                    elif allow_quarterly_report and event["title"].endswith("关于出资设立风险投资基金的进展公告"):
                        header = "".join(pages[0].split())
                        body = "".join("".join(pages[1:]).split())
                        if (not re.search(rf"证券代码[:：]{analysis['symbol']}(?![0-9])", header)
                                or "关于出资设立风险投资基金的进展公告" not in header
                                or "完成了私募投资基金变更事项备案手续" not in body):
                            raise ValueError("FUND_AMENDMENT_ORIGINAL_IDENTITY_MISMATCH")
                        registration = re.findall(r"备案编码[:：]([A-Z0-9]{6})(?![A-Z0-9])", body)
                        dates = re.findall(r"变更备案完成日期[:：](20[0-9]{2})年([0-9]{1,2})月([0-9]{1,2})日", body)
                        if len(registration) != 1 or len(dates) != 1:
                            raise ValueError("FUND_AMENDMENT_UNIQUE_REGISTRATION_REQUIRED")
                        completed = date(*(int(value) for value in dates[0]))
                        if completed > published:
                            raise ValueError("FUND_AMENDMENT_DATE_AFTER_PUBLICATION")
                        terms = dict(
                            event_type="REPORTED_FUND_AMENDMENT_REGISTRATION",
                            published_date=published.isoformat(), effective_date=None,
                            summary=f"原件披露基金{registration[0]}于{completed}完成变更备案。",
                            implication="核对合伙条款和未来资金调用日期；备案本身不证明母公司新增出资或实际付现。",
                            terms=dict(registration_code=registration[0], registration_date=completed.isoformat(),
                                       incremental_parent_cash_verified=False),
                            affected_model_fields=["commitments_outside_capex"],
                            limitations=["不改变候选现金流，不授予重大性批准。"], action="no_order")
                    elif allow_quarterly_report and event["title"].endswith("中期利润分配预案的公告"):
                        from ...infrastructure.filings.sse_capital_checkpoint_v1 import parse_sse_capital_checkpoint

                        proposal = parse_sse_capital_checkpoint(
                            pages, symbol=analysis["symbol"], published_date=published,
                        )
                        if (proposal.get("kind") != "INTERIM_PROPOSAL_DATED_SHARES"
                                or proposal.get("proposal_only") is not True):
                            raise ValueError("INTERIM_DIVIDEND_PROPOSAL_ORIGINAL_NOT_VERIFIED")
                        terms = dict(
                            event_type="REPORTED_INTERIM_DIVIDEND_PROPOSAL",
                            published_date=published.isoformat(), effective_date=None,
                            summary=f"原件拟每股派现{proposal['proposed_cash_per_share_cny']}元。",
                            implication="跟踪股东会决议和实施公告，并核对登记日股本及实际分配。",
                            terms=proposal, affected_model_fields=["shareholder_distributions"],
                            limitations=["预案不代表已实施、已支付或模型已包含；所列股本仅对应原件日期。"],
                            action="no_order",
                        )
                    elif (allow_quarterly_report
                          and event["title"].endswith(("临时股东会决议公告", "临时股东大会决议公告"))
                          and "中期利润分配预案" in "".join("".join(pages).split())):
                        from ...infrastructure.filings.interim_dividend_resolution import parse_interim_dividend_resolution

                        resolution = parse_interim_dividend_resolution(
                            pages, symbol=analysis["symbol"], published=published,
                        )
                        terms = dict(
                            event_type="REPORTED_INTERIM_DIVIDEND_SHAREHOLDER_APPROVAL",
                            published_date=published.isoformat(), effective_date=None,
                            summary=f"股东会于{resolution['meeting_date']}通过中期利润分配预案。",
                            implication="仍须跟踪登记、除息和约定发放原件，随后核对实际支付。",
                            terms=resolution, affected_model_fields=["shareholder_distributions"],
                            limitations=["决议仅证明通过议案，不证明最终每股金额、实施或支付。"],
                            action="no_order",
                        )
                    elif (event["title"].endswith(("年度股东会决议公告", "年度股东大会决议公告"))
                          and any(label in "".join("".join(pages).split())
                                  for label in ("年度利润分配预案", "年度利润分配方案"))):
                        from ...infrastructure.filings.interim_dividend_resolution import parse_annual_dividend_resolution

                        terms = None
                        if not allow_quarterly_report:
                            try:
                                terms = parser(pages, symbol=analysis["symbol"])
                            except ValueError:
                                pass
                        if terms is None:
                            resolution = parse_annual_dividend_resolution(
                                pages, symbol=analysis["symbol"], published=published,
                            )
                            terms = dict(
                                event_type="REPORTED_ANNUAL_DIVIDEND_SHAREHOLDER_APPROVAL",
                                published_date=published.isoformat(), effective_date=None,
                                summary=f"股东会于{resolution['meeting_date']}通过{resolution['fiscal_year']}年度利润分配预案。",
                                implication="结合独立提案和实施公告核对金额、登记与支付。",
                                terms=resolution, affected_model_fields=["shareholder_distributions"],
                                limitations=["表决原件只确认通过，未证明金额、实施或支付。"],
                                action="no_order",
                            )
                    elif allow_quarterly_report and (interim_title := re.search(r"(?:中期|半年度)权益分派实施公告$", event["title"])):
                        heading = re.sub(r"\s+", "", pages[0]) if pages else ""
                        if interim_title[0] not in heading:
                            raise ValueError("INTERIM_IMPLEMENTATION_ORIGINAL_TITLE_MISMATCH")
                        schedule = _cash_terms(pages, analysis["symbol"])
                        terms = dict(
                            event_type="REPORTED_INTERIM_DIVIDEND_IMPLEMENTATION_SCHEDULE",
                            published_date=schedule["published_date"], effective_date=None,
                            summary=f"中期分配实施公告列示每股派现{schedule['cash_per_share']}元。",
                            implication="按公告核对登记、除息及约定发放日，并单独核验实际支付和入模口径。",
                            terms=schedule, affected_model_fields=["shareholder_distributions"],
                            limitations=["公告列示日程，不证明实际支付、模型已包含或比较日股本。"],
                            action="no_order",
                        )
                    elif allow_quarterly_report and (dividend_title := re.search(
                            r"(20[0-9]{2})年度分红派息实施公告$", event["title"])):
                        from ...infrastructure.filings.native_capital_observation_v1 import parse_native_capital_observation

                        observation = parse_native_capital_observation(pages, symbol=analysis["symbol"])
                        if (observation.get("kind") != "dividend_implementation"
                                or observation.get("status") != "VERIFIED"
                                or observation.get("observation_date") != published.isoformat()
                                or observation.get("dividend_fiscal_year") != dividend_title[1]):
                            raise ValueError("DIVIDEND_ORIGINAL_NOT_VERIFIED_FOR_EVENT")
                        cover = "".join(pages[0].split())
                        meetings = re.findall(
                            rf"已获(20[0-9]{{2}})年([0-9]{{1,2}})月([0-9]{{1,2}})日召开的"
                            rf"{dividend_title[1]}年度股东(?:大会|会)审议通过", cover,
                        )
                        if len(meetings) == 1:
                            meeting = date(*map(int, meetings[0]))
                            if meeting <= published:
                                observation["referenced_approval_meeting_date"] = meeting.isoformat()
                        terms = dict(event_type="REPORTED_ANNUAL_DIVIDEND_IMPLEMENTATION_SCHEDULE",
                            published_date=published.isoformat(), effective_date=None,
                            summary=f"原件列示每10股派现{observation['dividend_per_10_shares_cny']}元、"
                                    f"登记日{observation['record_date']}及除息日{observation['ex_date']}。",
                            implication="供期间分配核对；托管代派日程不证明账户到账或模型已扣除现金。",
                            terms=observation, affected_model_fields=["shareholder_distributions"],
                            limitations=["仅核验实施安排；不将公告复述的往期注销计为本次股本行动。"],
                            action="no_order")
                    elif allow_quarterly_report and event["title"].endswith("关于部分限制性股票回购注销完成的公告"):
                        from ...infrastructure.filings.native_capital_observation_v1 import parse_native_capital_observation

                        observation = parse_native_capital_observation(pages, symbol=analysis["symbol"])
                        if (observation.get("kind") != "restricted_share_cancellation_notice"
                                or observation.get("status") != "VERIFIED"
                                or observation.get("observation_date") != published.isoformat()):
                            raise ValueError("CANCELLATION_ORIGINAL_NOT_VERIFIED_FOR_EVENT")
                        terms = dict(event_type="REPORTED_RESTRICTED_SHARE_CANCELLATION_COMPLETED",
                            published_date=published.isoformat(), effective_date=None,
                            summary=f"截至公告日已完成注销{observation['cancelled_shares']}股；"
                                    f"股份总数由{observation['shares_before']}变为{observation['issued_shares_after']}股。",
                            implication="核对该次股本行动，不能证明比较日股本或期间行动覆盖。",
                            terms=observation, affected_model_fields=["ordinary_shares"],
                            limitations=["公告证明截至披露日已完成，未据此推断精确生效日。"],
                            action="no_order")
                    elif allow_quarterly_report and event["title"].endswith("解除限售股份上市流通的提示性公告"):
                        from ...infrastructure.filings.native_capital_observation_v1 import parse_native_capital_observation

                        observation = parse_native_capital_observation(pages, symbol=analysis["symbol"])
                        if (observation.get("kind") != "share_unlock_notice"
                                or observation.get("status") != "VERIFIED"
                                or observation.get("observation_date") != published.isoformat()
                                or _day(observation["share_effective_date"]) < published
                                or observation.get("net_share_change") != "0"):
                            raise ValueError("UNLOCK_ORIGINAL_NOT_VERIFIED_FOR_EVENT")
                        terms = dict(event_type="REPORTED_SHARE_UNLOCK_NOTICE",
                            published_date=published.isoformat(), effective_date=None,
                            planned_implementation_date=observation["share_effective_date"],
                            summary="解除限售通知列示总股数不变，流通结构以登记结算资料为准。",
                            implication="此通知不支持增减股台账，也不证明比较日股本连续性。",
                            share_unlock_observation=observation, affected_model_fields=[],
                            limitations=["仅核验公告所列方案，未确认实际完成。"], action="no_order")
                    else:
                        from ...infrastructure.filings.parent_guarantee_event import TITLE, parse_parent_guarantee_event

                        from ...infrastructure.filings.quarter_operating_breakdown import (
                            TITLE_PATTERN, YTD_TITLE_PATTERN, parse_quarter_operating_breakdown,
                            parse_ytd_operating_breakdown,
                        )

                        if allow_quarterly_report and re.search(TITLE_PATTERN + "$", event["title"]):
                            terms = parse_quarter_operating_breakdown(pages, symbol=analysis["symbol"])
                        elif allow_quarterly_report and re.search(YTD_TITLE_PATTERN + "$", event["title"]):
                            terms = parse_ytd_operating_breakdown(pages, symbol=analysis["symbol"])
                        elif allow_quarterly_report and event["title"].endswith(TITLE):
                            terms = parse_parent_guarantee_event(pages, symbol=analysis["symbol"])
                        else:
                            terms = parser(pages, symbol=analysis["symbol"])
                    if terms["published_date"] != published.isoformat():
                        raise ValueError("OPERATING_EVENT_DOCUMENT_DATE_MISMATCH")
                    facts.append(dict(binding=binding, source_url=source["source_url"],
                        source_available_at=window["acquired_at"], terms=terms))
                except (ValueError, KeyError, TypeError, OSError, ArithmeticError) as error:
                    unresolved.append(dict(binding=binding, reason=str(error)))
            rows.append(dict(announcement_id=identity, title=event["title"],
                published_at=event["published_at"], source_url=event["source_url"],
                status="SOURCE_TERMS_VERIFIED_REQUIRES_CANDIDATE_REVIEW" if facts else "UNSUPPORTED_OR_UNRESOLVED",
                facts=facts, unresolved=unresolved,
                candidate_binding=deepcopy(analysis["review_binding"]["candidate_binding"]),
                input_descriptor_sha256=analysis["input_descriptor_sha256"],
                model_inputs_changed=False, materiality_approved=False, action="no_order"))
    for row in rows:
        for fact in row["facts"]:
            terms = fact["terms"]
            if terms.get("event_type") != "REPORTED_SHARE_UNLOCK_NOTICE":
                continue
            title = re.sub(r"\s+", "", row["title"])
            matches = [item for item in unlock_confirmations
                if item["notice_date"] == terms["published_date"]
                and item["listing_date"] == terms["planned_implementation_date"]
                and item["normalized_notice_title"] == title]
            if len(matches) == 1:
                terms["issuer_reported_listing_confirmation"] = matches[0]
    return rows


def _financial_update_closure_status(analysis, financial_events, *, operating_events=()):
    """Reconcile reported updates to an adapter-proven recomputation closure."""
    closure = analysis.get("consumed_financial_updates")
    if closure is None:
        return None
    candidate = analysis["review_binding"]["candidate_binding"]
    descriptor = analysis["input_descriptor_sha256"]
    if not isinstance(closure, list) or not closure:
        raise ValueError("CONSUMED_FINANCIAL_UPDATE_CLOSURE_REQUIRED")
    expected = {}
    for row in closure:
        if (not isinstance(row, dict)
                or row.get("status") != "EXACT_FINANCIAL_UPDATE_COLD_RECOMPUTED_IN_CANDIDATE"
                or row.get("candidate_binding") != candidate
                or row.get("input_descriptor_sha256") != descriptor
                or row.get("action") != "no_order"
                or not isinstance(row.get("predecessor_receipt_binding"), dict)
                or not isinstance(row.get("predecessor_input_descriptor_sha256"), str)
                or not row["predecessor_input_descriptor_sha256"]):
            raise ValueError("CONSUMED_FINANCIAL_UPDATE_CLOSURE_INVALID")
        source_binding = row.get("source_binding")
        if not isinstance(source_binding, dict):
            raise ValueError("CONSUMED_FINANCIAL_UPDATE_CLOSURE_IDENTITY_INVALID")
        key = (row.get("period_end"), source_binding.get("sha256"))
        if (not isinstance(row.get("period_end"), str)
                or set(source_binding) != {"path", "sha256"}
                or key in expected):
            raise ValueError("CONSUMED_FINANCIAL_UPDATE_CLOSURE_IDENTITY_INVALID")
        expected[key] = row
    observed = []
    for event in financial_events:
        for fact in event["facts"]:
            update = fact["terms"]["financial_update"]
            observed.append((update["period_end"], fact["binding"].get("sha256")))
    unmatched_observed = [key for key in observed if key not in expected]
    unmatched_closure = [key for key in expected if key not in observed]
    financing_statuses = {
        row.get("financing_comparison", {}).get("status") for row in closure
    }
    conflicts = "CONFLICT" in financing_statuses
    financing_unverified = bool(
        financing_statuses - {"CONFLICT", "GROSS_YTD_FLOOR_NOT_CONTRADICTED"}
    )
    cutoff = max(_day(period) for period, _ in expected)
    later_financing = [
        {"announcement_id": event["announcement_id"], "source_binding": fact["binding"],
         "issue": issue}
        for event in operating_events
        if event.get("status") == "SOURCE_TERMS_VERIFIED_REQUIRES_CANDIDATE_REVIEW"
        for fact in event["facts"]
        if fact["terms"].get("event_type") == "REPORTED_ISSUER_FINANCING_ISSUANCE"
        for issue in fact["terms"]["financing_issues"]
        if _day(issue["interest_start"]) > cutoff
    ]
    later_redemptions = [
        {"announcement_id": event["announcement_id"], "source_binding": fact["binding"],
         "effective_date": fact["terms"]["effective_date"],
         "redemptions": deepcopy(fact["terms"]["financing_redemptions"])}
        for event in operating_events
        if event.get("status") == "SOURCE_TERMS_VERIFIED_REQUIRES_CANDIDATE_REVIEW"
        for fact in event["facts"]
        if fact["terms"].get("event_type") == "REPORTED_ISSUER_FINANCING_REDEMPTION"
        and _day(fact["terms"]["effective_date"]) > cutoff
    ]
    if (unmatched_observed or unmatched_closure or conflicts or financing_unverified
            or later_financing or later_redemptions):
        reasons = []
        if unmatched_observed or unmatched_closure:
            reasons.append("FINANCIAL_UPDATE_REQUIRES_RECOMPUTATION")
        if conflicts:
            reasons.append("REPORTED_PARENT_FINANCING_EXCEEDS_FULL_YEAR_POLICY")
        if financing_unverified:
            reasons.append("REPORTED_PARENT_FINANCING_VERIFICATION_REQUIRED")
        if later_financing:
            reasons.append("ISSUER_FINANCING_AFTER_RECOMPUTED_PERIOD_REQUIRES_CASH_RECONCILIATION")
        if later_redemptions:
            reasons.append("ISSUER_REDEMPTION_AFTER_RECOMPUTED_PERIOD_REQUIRES_CASH_RECONCILIATION")
        return {
            "status": "BLOCKED",
            "reason_codes": reasons,
            "scope": "EXACT_CANDIDATE_FINANCIAL_UPDATE_CLOSURE",
            "consumed_closure": deepcopy(closure),
            "unmatched_observed": unmatched_observed,
            "unmatched_closure": unmatched_closure,
            "subsequent_financing_issuance": later_financing,
            "subsequent_financing_redemption": later_redemptions,
        }
    return {
        "status": "PASS", "reason_codes": [],
        "scope": "EXACT_CANDIDATE_FINANCIAL_UPDATE_CLOSURE",
        "consumed_closure": deepcopy(closure),
        "unmatched_observed": [], "unmatched_closure": [],
    }


def _first_input_opening_cancellation(analysis, source_windows, now, read, page_cache):
    """Match a named completion to a capital transition in the consumed report."""
    from ...infrastructure.filings.native_capital_observation_v1 import parse_native_capital_observation
    from ...infrastructure.filings.official_pdf import validate_pdf_original
    from ...infrastructure.filings.pdf_text import extract_pages

    basis = analysis["valuation_date"]
    candidates = [
        dict(window, announcements=[
            event for event in window["announcements"]
            if event["title"].endswith("关于部分限制性股票回购注销完成的公告")
            and datetime.fromisoformat(event["published_at"]).date() <= _day(basis)
        ])
        for window in source_windows
    ]
    matches = [
        fact for row in _operating_events(analysis, candidates, now, read, page_cache=page_cache)
        for fact in row["facts"]
        if fact["terms"]["event_type"] == "REPORTED_RESTRICTED_SHARE_CANCELLATION_COMPLETED"
    ]
    if not matches:
        return None
    report_ref = analysis["opening_capital_original"]
    original = read(report_ref)
    validate_pdf_original(original)
    report = parse_native_capital_observation(extract_pages(original), symbol=analysis["symbol"])
    shares = analysis["consumed_operating_inputs"]["ordinary_shares"]
    if (report.get("status") != "VERIFIED" or report.get("period_end") != basis
            or report.get("ordinary_shares") != shares
            or report.get("cancellation_state") != "REPORTED_RESTRICTED_SHARE_CANCELLATION_COMPLETED_BY_PERIOD_END"):
        return None
    matched = [
        fact for fact in matches
        if (notice := fact["terms"]["terms"])["shares_before"] == report["shares_before"]
        and notice["cancelled_shares"] == report["cancelled_shares"]
        and notice["issued_shares_after"] == shares
        and _day(report["cancellation_date"]) <= _day(notice["completed_by"]) <= _day(basis)
    ]
    if len(matched) != 1:
        return None
    return dict(status="MATCHED_COMPLETED_IN_CONSUMED_OPENING_CAPITAL",
        notice_binding=matched[0]["binding"], report_binding=report_ref,
        completion_reported_by=matched[0]["terms"]["terms"]["completed_by"],
        report_evidence=report["evidence_refs"], opening_shares=shares,
        cancelled_shares=report["cancelled_shares"], in_opening_basis=True,
        period_share_delta="0", action="no_order")


def _annual_approval_schedule_links(rows, *, end, after=None):
    approvals = [
        fact for row in rows for fact in row["facts"]
        if fact["terms"].get("event_type") == "REPORTED_ANNUAL_DIVIDEND_SHAREHOLDER_APPROVAL"
        and _day(fact["terms"]["published_date"]) <= end
    ]
    vote_links = []
    for row in rows:
        for fact in row["facts"]:
            parsed = fact["terms"]
            kind = parsed.get("event_type")
            schedule = parsed["terms"]
            if kind == "REPORTED_ANNUAL_DIVIDEND_IMPLEMENTATION_SCHEDULE":
                fiscal_year = schedule["dividend_fiscal_year"]
                scheduled_payment_date = schedule["agency_payment_date"]
                publication_date = parsed["published_date"]
            elif kind == "PREVALUATION_DISTRIBUTION_SCHEDULE" and schedule.get("distribution_period") == "年度":
                fiscal_year = schedule["distribution_year"]
                scheduled_payment_date = schedule["cash_payment_date"]
                publication_date = schedule["published_date"]
            else:
                continue
            meeting = schedule.get("referenced_approval_meeting_date")
            if not meeting:
                continue
            effective = max(_day(schedule["ex_date"]), _day(scheduled_payment_date))
            if effective > end or (after is not None and effective <= after):
                continue
            matches = [
                vote for vote in approvals
                if str(vote["terms"]["terms"]["fiscal_year"]) == fiscal_year
                and vote["terms"]["terms"]["meeting_date"] == meeting
                and _day(vote["terms"]["published_date"]) <= _day(publication_date)
            ]
            if len(matches) == 1:
                vote_links.append(dict(
                    fiscal_year=fiscal_year, meeting_date=meeting,
                    approval_evidence_binding=matches[0]["binding"],
                    implementation_evidence_binding=fact["binding"],
                    status="APPROVED_AGENDA_MATCHED_TO_HISTORICAL_SCHEDULE",
                    cash_receipt_proven=False, action="no_order",
                ))
    return vote_links


def _opening_chain_research(analysis, rows, reconciliation):
    """Reconcile named observed actions only; never certify an empty universe."""
    start = _day(analysis["valuation_date"])
    shares = Decimal(analysis["consumed_operating_inputs"]["ordinary_shares"])
    confirmations, authorizations, annual, purchases, distribution_schedules = [], [], [], [], []
    for row in rows:
        for fact in row["facts"]:
            parsed = fact["terms"]
            terms = parsed["terms"]
            if _day(parsed["published_date"]) > start:
                continue
            if parsed.get("event_type") == "PREVALUATION_DISTRIBUTION_SCHEDULE":
                distribution_schedules.append(dict(
                    evidence_binding=fact["binding"], cash_per_share=terms["cash_per_share"],
                    ex_date=terms["ex_date"], cash_payment_date=terms["cash_payment_date"],
                    outside_comparison_interval=max(_day(terms["ex_date"]), _day(terms["cash_payment_date"])) <= start,
                    cash_receipt_proven=False))
            if terms.get("purchase_state") == "COMPLETED" and terms.get("cancellation_state") == "SCHEDULED_UNCONFIRMED":
                purchases.append(dict(binding=fact["binding"], terms=terms,
                    published_date=parsed["published_date"], source_url=fact.get("source_url")))
            if "confirmed_cancellation_date" in terms:
                confirmations.append(dict(evidence_binding=fact["binding"],
                    effective_date=terms["confirmed_cancellation_date"],
                    capital_as_of=terms["capital_as_of"], cancelled_shares=terms["cancelled_shares"],
                    completion_notice_on=terms.get("completion_notice_on"),
                    issued_shares=terms["issued_shares"], treasury_shares=terms["treasury_shares"],
                    matches_consumed_opening_shares=Decimal(terms["issued_shares"]) == shares,
                    completed_before_valuation=_day(terms["confirmed_cancellation_date"]) <= start))
            if terms.get("authorization_status") == "CONDITIONAL_AUTHORIZATION_REQUIRES_FOLLOW_UP":
                authorizations.append(dict(evidence_binding=fact["binding"],
                    authorization_text=terms["authorization_text"],
                    amount_cap_text=terms["amount_cap_text"],
                    scheme_determined=False, cash_obligation_established=False,
                    follow_up_status="SUBSEQUENT_SCHEME_IMPLEMENTATION_OR_REVOCATION_NOT_RECONCILED"))
            if "annual_cash_per_share" in terms:
                for cash in (reconciliation or {}).get("distributions", []):
                    implementation = cash.get("native_terms")
                    if implementation is None:
                        continue
                    if implementation.get("parser_version") == "sse-repurchase-excluded-gross-cash-scheme-v1":
                        eligible_shares = implementation["eligible_distribution_shares"]
                    elif (implementation.get("parser_version") == "sse-full-share-cross-page-cash-scheme-v1"
                            and implementation.get("distribution_period") == "年度"
                            and implementation.get("distribution_year") == terms.get("annual_distribution_year")
                            and implementation.get("body_terms_reconciled") is True):
                        eligible_shares = implementation["eligible_distribution_shares"]
                    elif (implementation.get("parser_version") == "sse-explicit-cash-implementation-body-v1"
                            and implementation.get("event_kind") == "EXPLICIT_NONDIFFERENTIAL_CASH_ONLY_IMPLEMENTATION"):
                        eligible_shares = implementation["total_shares"]
                    else:
                        eligible_shares = None
                    matches = (eligible_shares is not None
                        and terms["currency"] == implementation["currency"] == "CNY"
                        and Decimal(terms["annual_cash_per_share"]) == Decimal(implementation["cash_per_share"])
                        and Decimal(terms["annual_total_cash_cny"]) == Decimal(implementation["total_gross_cash"])
                        and Decimal(terms["eligible_distribution_shares"]) == Decimal(eligible_shares)
                        and _day(parsed["published_date"]) <= _day(implementation["published_date"])
                        and _day(implementation["ex_date"]) <= start
                        and _day(implementation["cash_payment_date"]) <= start)
                    annual.append(dict(source_binding=fact["binding"],
                        event_type=parsed["event_type"], implementation_id=cash["id"],
                        annual_cash_per_share=terms["annual_cash_per_share"],
                        annual_total_cash_cny=terms["annual_total_cash_cny"],
                        status="MATCHED_PREVALUATION_IMPLEMENTATION_TERMS" if matches else "TERMS_NOT_MATCHED",
                        price_deduction_applied="0", payment_receipt_proven=False,
                        accounting_one_cent_difference_resolved=False))
    vote_links = _annual_approval_schedule_links(rows, end=start)
    purchase_links = []
    for purchase in purchases:
        terms = purchase["terms"]
        matches = [confirmation for confirmation in confirmations
                   if confirmation["completion_notice_on"] == purchase["published_date"]
                   and confirmation["effective_date"] == terms["scheduled_cancellation_date"]
                   and Decimal(confirmation["cancelled_shares"]) == terms["cumulative_purchased_shares"]
                   and Decimal(confirmation["issued_shares"]) == terms["planned_post_cancellation_shares"]
                   and confirmation["matches_consumed_opening_shares"]
                   and confirmation["completed_before_valuation"]]
        # A pre-cutoff notice with a future schedule establishes a named
        # opening follow-up. An elapsed or same-day schedule gives no opening
        # status without a separate registration confirmation.
        pending_at_opening = (
            _day(purchase["published_date"]) < start < _day(terms["scheduled_cancellation_date"])
        )
        purchase_links.append(dict(purchase_binding=purchase["binding"],
            source_url=purchase["source_url"], published_date=purchase["published_date"],
            opening_status=("DISCLOSED_CANCELLATION_SCHEDULE_AFTER_OPENING"
                            if pending_at_opening else "OPENING_PENDING_STATUS_NOT_ESTABLISHED"),
            cancellation_binding=matches[0]["evidence_binding"] if len(matches) == 1 else None,
            status="MATCHED_COMPLETED_BEFORE_VALUATION" if len(matches) == 1 else "CANCELLATION_NOT_UNIQUELY_RECONCILED",
            purchase_through=terms["through"], scheduled_cancellation_date=terms["scheduled_cancellation_date"],
            purchased_shares=terms["cumulative_purchased_shares"], paid_cny=terms["cumulative_paid_cny"],
            planned_post_cancellation_shares=terms["planned_post_cancellation_shares"],
            action="no_order"))
    return dict(status="KNOWN_ACTIONS_PARTIALLY_RECONCILED" if confirmations or annual or authorizations or purchases or vote_links else "NO_SUPPORTED_OPENING_ACTION",
        candidate_binding=deepcopy(analysis["review_binding"]["candidate_binding"]),
        valuation_date=start.isoformat(), confirmations=confirmations,
        distribution_links=annual, outstanding_authorizations=authorizations, purchase_links=purchase_links,
        prevaluation_distribution_schedules=distribution_schedules, annual_approval_schedule_links=vote_links,
        complete_opening_action_coverage=False, comparison_date_capital_proven=False,
        formal_eligibility=False, action="no_order")


def _buyback_checkpoint_deltas(checkpoints):
    """Difference comparable cumulative disclosures without altering the candidate."""
    grouped = {}
    for point in checkpoints:
        grouped.setdefault((point["plan_start"], point["plan_end"]), []).append(point)
    result = []
    for (plan_start, plan_end), points in sorted(grouped.items()):
        points.sort(key=lambda row: row["through"])
        if len({p["through"] for p in points}) != len(points):
            continue
        for before, after in zip(points, points[1:]):
            shares = after["shares"] - before["shares"]
            with localcontext() as context:
                context.prec = 80
                paid = after["paid_cny"] - before["paid_cny"]
            if shares < 0 or paid < 0 or (shares == 0) != (paid == 0):
                continue
            result.append(dict(plan_start=plan_start, plan_end=plan_end,
                after_date=before["through"], through=after["through"],
                purchase_share_delta=shares, disclosed_cash_delta_cny=str(paid),
                before_binding=deepcopy(before["binding"]), after_binding=deepcopy(after["binding"]),
                scope="MATCHING_DISCLOSED_PLAN_WINDOW_RESEARCH_ONLY", action="no_order"))
    return result


def _basis_followup(analysis, reconciliation, opening_chain, windows, comparison_date,
                    operating_events=()):
    """Explain the exact latest proven checkpoint, never extend it by silence."""
    from ...quote_sessions import CHINA

    reports = ((reconciliation or {}).get("native_source_consumption") or {}).get("reports", [])
    checkpoints, followups = [], []
    for report in reports:
        terms = report.get("terms") or {}
        if (report.get("status") not in {"NATIVE_REPORT_FIELDS_VERIFIED", "NATIVE_CAPITAL_CHECKPOINT_VERIFIED"}
                or terms.get("symbol") != analysis["symbol"]):
            continue
        period, published = _day(terms["period_end"]), _day(report["published_date"])
        if comparison_date is not None and (period > comparison_date or published > comparison_date):
            continue
        checkpoints.append(dict(as_of=period.isoformat(), published_date=published.isoformat(),
            ordinary_shares=terms["ordinary_shares"], issued_shares=terms.get("issued_shares"),
            treasury_shares=terms.get("treasury_shares"), proposal_only=terms.get("proposal_only", False),
            proposed_cash_per_share_cny=terms.get("proposed_cash_per_share_cny")
                if terms.get("proposal_only") is True else None,
            share_scope=terms.get("share_scope"), classification=terms.get("classification", "FACT"),
            derivation=terms.get("derivation"), evidence_binding=deepcopy(report["binding"]),
            source_url=report["source_url"], available_at=report["source_available_at"],
            matches_consumed_opening=report.get("consumed_opening_fact") is True,
            continuity_after_period_end=False,
            subsequent_capital_statement=terms.get("subsequent_capital_state"),
            limitation=("明确报告期间未变可连接原始普通股锚点；预案内总股本只证明所述日期总股数，回购库存不等于注销；均不证明其后至比较日连续性。"
                if report.get("status") == "NATIVE_CAPITAL_CHECKPOINT_VERIFIED"
                else "每股指标影响栏不适用，不是报告期后总股本无任何变动的声明。")))
        if terms.get("interim_proposal_state") == "NO_INTERIM_DISTRIBUTION_OR_CAPITALIZATION_PROPOSED":
            followups.append(dict(report_period_end=period.isoformat(),
                published_date=published.isoformat(), evidence_binding=deepcopy(report["binding"]),
                source_url=report["source_url"], physical_pages=(terms.get("term_pages") or {}).get("proposal", []),
                status="REPORT_NO_INTERIM_PROPOSAL_NOT_AUTHORIZATION_REVOCATION",
                conclusion="该中报的半年度分配预案为不分配、不转增；不能据此认定此前中期分红授权已撤销，或此后全年不再分红。",
                subsequent_distribution_statement=terms.get("subsequent_distribution_state"),
                authorization_resolved=False, zero_future_dividend_proven=False))
    checkpoints.sort(key=lambda row: (row["as_of"], row["published_date"]))
    latest = checkpoints[-1] if checkpoints else None
    capital_events, buyback_checkpoints = [], []
    for event in operating_events:
        for fact in event.get("facts", []):
            terms = fact.get("terms") or {}
            event_type = terms.get("event_type")
            if event_type == "REPORTED_SHARE_UNLOCK_NOTICE":
                confirmation = terms.get("issuer_reported_listing_confirmation")
                observation = terms["share_unlock_observation"]
                if (confirmation and comparison_date is not None
                        and observation["net_share_change"] == "0"
                        and _day(analysis["valuation_date"]) < _day(confirmation["listing_date"]) <= comparison_date
                        and _day(confirmation["published_date"]) <= comparison_date):
                    capital_events.append(dict(
                        announcement_id=event["announcement_id"], title=event["title"],
                        published_at=event["published_at"], event_type=event_type,
                        source_binding=deepcopy(fact["binding"]), source_url=fact["source_url"],
                        source_available_at=fact["source_available_at"],
                        effective_date=confirmation["listing_date"], net_share_change="0",
                        notice_observation=deepcopy(observation),
                        issuer_reported_listing_confirmation=deepcopy(confirmation),
                        issued_share_effect="NO_ISSUED_SHARE_CHANGE_IN_THIS_EVENT",
                        classification="ISSUER_CONFIRMED_RESTRICTED_SHARE_UNLOCK",
                        window_completeness_granted=False, action="no_order"))
                continue
            if event_type not in {
                    "REPORTED_BUYBACK_PROGRESS",
                    "PLAN_SECONDARY_MARKET_SHARE_PURCHASE_COMPLETED",
                    "BUYBACK_CAPITAL_REDUCTION_CREDITOR_NOTICE"}:
                continue
            facts = terms.get("terms") or {}
            if (event_type == "REPORTED_BUYBACK_PROGRESS" and comparison_date is not None
                    and facts.get("plan_start") and facts.get("plan_end")
                    and facts["plan_start"] <= facts["through"] <= facts["plan_end"]
                    and _day(facts["through"]) <= comparison_date
                    and datetime.fromisoformat(event["published_at"]).astimezone(CHINA).date() <= comparison_date):
                buyback_checkpoints.append(dict(plan_start=facts["plan_start"], plan_end=facts["plan_end"],
                    through=facts["through"], shares=facts["cumulative_purchased_shares"],
                    paid_cny=Decimal(facts["cumulative_paid_cny"]), binding=fact["binding"]))
            issued_effect = facts.get("issued_share_effect")
            capital_events.append(dict(
                announcement_id=event["announcement_id"], title=event["title"],
                published_at=event["published_at"], event_type=event_type,
                source_binding=deepcopy(fact["binding"]),
                issued_share_effect=issued_effect or (
                    "NO_ISSUANCE_OR_CANCELLATION_PROVEN_BY_THIS_EVENT_ONLY"
                    if event_type == "REPORTED_BUYBACK_PROGRESS" else None),
                classification=("EXISTING_SHARE_TRANSACTION_NO_ISSUED_SHARE_CHANGE"
                    if issued_effect == "NO_ISSUANCE_OR_CANCELLATION_IN_THIS_PURCHASE_EVENT"
                    else "PLANNED_CANCELLATION_NO_EFFECTIVE_DATE"
                    if event_type == "BUYBACK_CAPITAL_REDUCTION_CREDITOR_NOTICE"
                    else "TREASURY_PURCHASE_OBSERVATION_NOT_CANCELLATION"),
                window_completeness_granted=False, action="no_order"))
    observed = [dict(scan_from=w["scan_from"], scan_to=w["scan_to"],
        acquired_at=w["acquired_at"], announcement_count=w["announcement_count"],
        coverage_status=w["coverage_status"], observation_binding=deepcopy(w["observation_binding"]))
        for w in windows if w.get("source_integrity_verified") is True]
    return dict(schema_version="candidate-basis-followup-v1",
        candidate_binding=deepcopy(analysis["review_binding"]["candidate_binding"]),
        input_descriptor_sha256=analysis["input_descriptor_sha256"],
        status="SOURCE_CHECKPOINTS_PARTIAL" if latest or followups else "NO_SUPPORTED_CHECKPOINT",
        comparison_date=comparison_date.isoformat() if comparison_date else None,
        capital_checkpoints=checkpoints, latest_capital_checkpoint=latest,
        uncovered_capital_interval=dict(after=latest["as_of"], through=comparison_date.isoformat())
            if latest and comparison_date and _day(latest["as_of"]) < comparison_date else None,
        interim_report_followups=followups,
        capital_event_classifications=capital_events,
        buyback_checkpoint_deltas=_buyback_checkpoint_deltas(buyback_checkpoints),
        authorization_followup_required=bool(opening_chain["outstanding_authorizations"]),
        observed_windows=observed,
        next_required_evidence=[
            "具有明确时点及单位的当前普通股股数，以及连接期初的有效股本行动原件。",
            "中期授权后实际方案、实施或撤销的原件；中报无预案不代替后续核验。",
            "当前候选的经营事件影响与重大性复核，不能由公告数量或检索完成代替。"],
        complete_effective_action_coverage=False, current_comparison_granted=False,
        human_approval_granted=False, action="no_order")


def _materiality(root, analysis, ref, windows, scans, now, read):
    """Consume the existing signed packet; never create an approval or transport."""
    from ...event_materiality import event_materiality_review_from_payload
    from ..product.research_materiality_reviews import (
        prepare_materiality_review_handoff, verify_authenticated_materiality,
    )
    route = dict(status="EXACT_MATERIALITY_REVIEW_NOT_BOUND", review_binding=deepcopy(ref))
    if not scans or len(scans) != 1:
        route.update(status="MATERIALITY_SCAN_CARDINALITY_UNSUPPORTED",
                     reason="当前原生材料性消费者要求一个精确扫描；未合并多份扫描或复核。")
        return None, route
    scan_ref = windows[0]["scan_binding"]
    package_ref = analysis["review_binding"].get("package_binding")
    if package_ref is None:
        route.update(status="NATIVE_MATERIALITY_CANDIDATE_ADAPTER_UNSUPPORTED",
                     reason="EXACT_RESEARCH_PACKAGE_MATERIALITY_HANDOFF_NOT_BOUND",
                     engineering_gap="当前研究回执尚未绑定既有材料性复核输入；不能复用其他候选的批准。")
        return None, route
    scan = scans[0]
    preflight = []
    if scan.coverage_status != "COMPLETE" or windows[0].get("full_calendar_window_elapsed") is False:
        preflight.append("materiality handoff requires complete acquired scan coverage")
    if analysis.get("valuation_date") and scan.validity_from != _day(analysis["valuation_date"]):
        preflight.append("materiality scan validity start mismatch")
    if not scan.announcements:
        preflight.append("materiality handoff requires acquired announcements")
    if preflight:
        route.update(status="NATIVE_MATERIALITY_SCAN_PRECONDITIONS_NOT_MET",
                     reason="; ".join(preflight), reason_codes=preflight,
                     engineering_gap=None)
        return None, route
    try:
        # Read-only native handoff replay detects missing v4/current-candidate
        # adapter support explicitly, instead of calling it missing user approval.
        handoff = prepare_materiality_review_handoff(root=root,
            package_path=read(package_ref), package_sha256=package_ref["sha256"],
            scan_path=read(scan_ref), scan_sha256=scan_ref["sha256"], now=now)
    except (ValueError, KeyError, TypeError, AttributeError, OSError) as error:
        unsupported = str(error) == "Exact annual-retention-v2 scenario required; no scalar retention"
        route.update(status="NATIVE_MATERIALITY_CANDIDATE_ADAPTER_UNSUPPORTED" if unsupported else "NATIVE_MATERIALITY_HANDOFF_REJECTED",
            reason=str(error), engineering_gap="既有材料性消费者不支持此候选模型格式；需接通现有适配器。" if unsupported else None)
        return None, route
    route["model_context"] = handoff["model_context"]
    route["unsigned_handoff"] = dict(
        handoff_sha256=handoff["unsigned_response"]["handoff_sha256"],
        package_binding=handoff["package_binding"], scan_binding=handoff["scan_binding"],
        scan_window=handoff["scan_window"], announcement_count=len(handoff["announcements"]),
        human_review_required=True, action="no_order",
    )
    if ref is None:
        return None, route
    packet = load_json_object(read(ref), "existing materiality packet")
    artifact_ref = packet["bindings"]["event_materiality"]
    raw = load_json_object(read(artifact_ref), "existing materiality artifact")
    review = event_materiality_review_from_payload(raw)
    if (review.symbol != analysis["symbol"] or review.scan_sha256 != scan_ref["sha256"]
            or review.reviewed_at > now or review.reviewed_at < scans[0].retrieved_at
            or review.scan_from != scans[0].scan_from or review.scan_to != scans[0].scan_to):
        raise ValueError("MATERIALITY_EXACT_SCAN_OR_AVAILABILITY_MISMATCH")
    verify_authenticated_materiality(root=root, packet=packet,
        model_context=handoff["model_context"], materiality=raw, packet_sha256=ref["sha256"])
    # Native verifier already replays all decisions, signature, trust and completion
    # head. Re-run it after arithmetic too, including changed/revoked trust state.
    route["status"] = "EXISTING_AUTHENTICATED_MATERIALITY_REPLAYED"
    return review, route


def _assess(analysis, valuation, quote, quote_result, windows, scans, reconciliation=None,
            materiality=None, materiality_route=None):
    """Source-bound cross-date reconciliation and model validity are separate."""
    start, end = valuation.valuation_date, quote.quote_date
    reasons = []
    refs = [item["observation_binding"] for item in windows]
    complete_observations = [
        (window, scan) for window, scan in zip(windows, scans, strict=True)
        if window.get("source_integrity_verified") is True
        and window["full_calendar_window_elapsed"] and scan.coverage_status == "COMPLETE"
    ]
    covering = [(window, scan) for window, scan in complete_observations
                if end is not None and scan.scan_from <= start and scan.scan_to >= end]
    complete_windows = [window for window, _ in complete_observations]
    publication_covered = end is not None and start <= end and _continuous_publication_window(
        complete_windows, start, end,
    )
    if not publication_covered:
        reasons.append("EVENT_WINDOW_DOES_NOT_COVER_VALUATION_TO_QUOTE")
    elif not covering:
        reasons.append("MULTI_WINDOW_MATERIALITY_REPLAY_NOT_SUPPORTED")
    # There is no fallback to an older, easier window when any supplied scan is
    # unresolved. Nonempty scans need the existing authenticated review route.
    if any(not w["full_calendar_window_elapsed"] for w in windows):
        reasons.append("INTRADAY_SNAPSHOT_NOT_FULL_WINDOW")
    if materiality is None and any(s.announcements for s in scans):
        reasons.append("EXACT_CANDIDATE_MATERIALITY_REVIEW_NOT_BOUND")
    if materiality is None and any(s.blockers or s.status != "COMPLETE_NO_MATERIAL_EVENT_IN_VALIDITY_WINDOW" for s in scans):
        reasons.append("NATIVE_EVENT_REVIEW_NOT_COMPLETE")
    if materiality_route and materiality_route["status"] == "NATIVE_MATERIALITY_CANDIDATE_ADAPTER_UNSUPPORTED":
        reasons.append("NATIVE_MATERIALITY_CANDIDATE_ADAPTER_UNSUPPORTED")
    if materiality_route and (materiality_route.get("status") == "EXISTING_MATERIALITY_REPLAY_REJECTED"
            or (materiality_route.get("review_binding") is not None
                and materiality_route.get("status") != "EXISTING_AUTHENTICATED_MATERIALITY_REPLAYED")):
        reasons.append("EXPLICIT_MATERIALITY_REVIEW_FAILED_NO_SCAN_FALLBACK")
    selected = covering[0][1] if covering else None
    validity = evaluate_model_validity(model_id=valuation.model_version, symbol=valuation.symbol,
        model_as_of=start, valid_from=start, quote_date=end or start,
        events=[], event_scan_evidence_refs=[], event_scan=selected if materiality is None else None,
        event_materiality=materiality, blockers=reasons)
    if validity.status == "VALID" and validity.blockers:
        validity = replace(validity, status="UNKNOWN", material_event_found=None)
    event_pass = validity.status == "VALID" and not validity.blockers
    checks = [_check("quote", "PASS" if quote_result["status"] == "QUALIFIED" else "BLOCKED",
        quote_result["reason_codes"], quote_result["explanation"],
        [quote_result["bundle_binding"]] if quote_result["bundle_binding"] else [],
        native_status=quote_result["native_status"])]
    shares = Decimal(analysis["consumed_operating_inputs"]["ordinary_shares"])
    if not shares.is_finite() or shares <= 0 or shares != shares.to_integral_value():
        raise ValueError("INVALID_CONSUMED_ORDINARY_SHARES")
    currency = (analysis.get("joint_capital_review") or {}).get("economic_path", {}).get("currency")
    basis_pass = (reconciliation is not None and reconciliation.get("native_basis_semantics_verified") is True
                  and reconciliation["current_price_basis_compatible"]
                  and currency == "CNY")
    basis_reasons = reconciliation["reason_codes"] if reconciliation else ["SOURCE_BOUND_RECONCILIATION_MISSING"]
    checks.append(_check("capital_structure", "PASS" if basis_pass else "BLOCKED",
        [] if basis_pass else list(dict.fromkeys(["CURRENT_SHARE_COUNT_AND_EFFECTIVE_ACTION_CHAIN_NOT_RECONCILED", *basis_reasons])),
        "保留已消费的普通股股数；跨日必须核验期初待生效行动及其后实施、注销、修订链。公告索引完整不证明股本未变。",
        analysis["source_bindings"], valuation_ordinary_shares=str(shares),
        current_ordinary_shares=reconciliation["closing_shares"] if basis_pass else None,
        currency=currency, share_basis="ordinary_share_unadjusted", reconciliation=reconciliation))
    distribution_pass = basis_pass and reconciliation.get("period_cash_coverage_complete") is True
    checks.append(_check("distributions", "PASS" if distribution_pass else "BLOCKED",
        [] if distribution_pass else list(dict.fromkeys(["PERIOD_DISTRIBUTIONS_AND_MODEL_INCLUSION_NOT_RECONCILED", *basis_reasons])),
        "估值已包含条件分配路径；须核验期间实际除息、支付及其是否已内含，不能把预测分红再加回，也不能仅凭本期无公告认定无分配。",
        analysis["source_bindings"], period_from=start.isoformat(), period_to=end.isoformat() if end else None,
        actual_cash_per_share=reconciliation["period_cash_per_share"]
            if distribution_pass else None,
        known_listed_period_cash_per_share=reconciliation["period_cash_per_share"] if reconciliation else None,
        inclusion_status="SOURCE_RECONCILED_NO_UNCONSUMED_PERIOD_CASH" if distribution_pass else "NOT_RECONCILED",
        adjustment_applied=False, reconciliation=reconciliation))
    checks.append(_check("material_events", "PASS" if event_pass else "BLOCKED",
        list(dict.fromkeys([*reasons, *validity.blockers])),
        "原生扫描重放只确认原件与检索范围；当日快照和待材料性复核公告不能授予模型VALID。",
        refs, windows=windows, publication_window_continuous=publication_covered,
        materiality_review_route=materiality_route,
        financial_statement_changed=validity.financial_statement_changed,
        capital_structure_changed=validity.capital_structure_changed))
    consumed_hashes = {source["sha256"] for source in analysis["source_bindings"]}
    fact_source_ids = {anchor["source_id"] for anchor in analysis.get("official_fact_anchors", [])}
    matched, unresolved = [], []
    reviewed_announcements = {}
    for scan in scans:
        for item in scan.announcements:
            row = dict(announcement_id=item.announcement_id, title=item.title,
                published_at=item.published_at.isoformat(), source_url=item.source_url,
                evidence_refs=list(item.evidence_refs))
            # Overlapping verified windows may retain identical bytes at different paths.
            fingerprint = (row["published_at"], row["title"], row["source_url"],
                frozenset((ref["id"], ref["sha256"], ref["source_url"])
                          for ref in row["evidence_refs"]))
            identity = row["announcement_id"]
            if identity in reviewed_announcements:
                if reviewed_announcements[identity] != fingerprint:
                    raise ValueError("CONFLICTING_FINANCIAL_EVENT_IDENTITY")
                continue
            reviewed_announcements[identity] = fingerprint
            if item.evidence_refs and all(source["sha256"] in consumed_hashes
                    and source.get("id") in fact_source_ids for source in item.evidence_refs):
                matched.append(dict(row, status="EXACT_FACT_SOURCE_ALREADY_CONSUMED_NOT_EVENT_APPROVAL",
                    consumed_fact_fields=[anchor["field"] for anchor in analysis.get("official_fact_anchors", [])
                        if anchor["source_id"] in {source.get("id") for source in item.evidence_refs}]))
            else:
                unresolved.append(dict(row, status="NOT_BOUND_TO_CURRENT_CANDIDATE_REVIEW",
                    original_bytes_in_source_closure=all(source["sha256"] in consumed_hashes for source in item.evidence_refs)))
    checks[3]["details"].update(matched_input_sources=matched, unresolved_sources=unresolved)
    checks.append(_check("financial_updates", "PASS" if event_pass else "BLOCKED",
        [] if event_pass else ["FINANCIAL_UPDATES_NOT_RECONCILED_TO_EXACT_CANDIDATE"],
        "财报、会计政策及其他新披露须复核是否改变精确候选输入；不能仅凭文件已下载或标题分类认定已消费。",
        refs, financial_statement_changed=validity.financial_statement_changed,
        input_descriptor_sha256=analysis["input_descriptor_sha256"],
        matched_input_sources=matched, unresolved_sources=unresolved))
    all_reasons = list(dict.fromkeys(code for item in checks for code in item["reason_codes"]))
    usable = all(item["status"] == "PASS" for item in checks)
    # C0 can return READY with supplied blockers; the adapter must additionally
    # require every gate and never expose its arithmetic as current while blocked.
    bridge_validity = validity if usable or validity.status != "VALID" else replace(
        validity, status="UNKNOWN", material_event_found=None, blockers=all_reasons)
    bridge = bridge_with_quote(valuation, bridge_validity, quote, blockers=all_reasons)
    ready = usable and bridge.bridge_status == "READY" and not bridge.blockers
    return checks, validity, bridge, ready


def candidate_alignment_config_path(root, digest):
    if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise ValueError("EXACT_CANDIDATE_HASH_REQUIRED")
    return root / CONFIG_DIRECTORY / (digest + ".json")


def load_pending_candidate_alignment(*, root, analysis, now):
    """No discovery by recency, no registration, no approval and no writes."""
    return _load_bound_alignment(root=root, analysis=analysis, now=now,
                                 input_schema=INPUT_SCHEMA)


def _load_bound_alignment(*, root, analysis, now, input_schema):
    """Shared checks for a source-replayed research identity, never a promotion.

    Versioned adapters must cold-replay their own input before calling this
    function. Each registration has an explicit schema and exact artifact hash;
    a direct cash receipt cannot consume a historical pending candidate's entry.
    """
    from .value_research_analysis import _bound
    result = _initial(analysis, now)
    verified = {}
    event_pages = _event_pages_for_read.get()
    if event_pages is None:
        event_pages = {}

    def read(ref):
        path = _bound(root, ref)
        prior = verified.get(ref["path"])
        if prior is not None and prior != ref["sha256"]:
            raise ValueError("CONFLICTING_ALIGNMENT_SOURCE_HASH")
        verified[ref["path"]] = ref["sha256"]
        return path

    try:
        if not isinstance(now, datetime) or now.utcoffset() is None:
            raise ValueError("AWARE_ALIGNMENT_CLOCK_REQUIRED")
        digest = result["candidate_binding"]["sha256"]
        if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
            raise ValueError("EXACT_CANDIDATE_HASH_REQUIRED")
        if (analysis["status"] != "CONDITIONAL_ANALYSIS_VERIFIED" or analysis["action"] != "no_order"
                or analysis["arithmetic_complete"] is not True):
            raise ValueError("SOURCE_RECOMPUTED_ANALYSIS_REQUIRED")
        config_path = candidate_alignment_config_path(root, digest)
        if not config_path.is_file():
            result["reason_codes"] = ["EXACT_CANDIDATE_ALIGNMENT_BINDING_MISSING"]
            return result
        config_ref = dict(path=config_path.relative_to(root).as_posix(), sha256=sha256_file(config_path))
        config = load_json_object(read(config_ref), "candidate alignment inputs")
        if (config["schema_version"] != input_schema or config["candidate_binding"] != result["candidate_binding"]
                or config["input_descriptor_sha256"] != analysis["input_descriptor_sha256"]):
            raise ValueError("ALIGNMENT_CANDIDATE_OR_DESCRIPTOR_MISMATCH")
        read(result["candidate_binding"])
        for ref in analysis["source_bindings"]:
            read(ref)
        valuation = ValuationResultCodec().from_payload(analysis["valuation"])
        if valuation.symbol != analysis["symbol"] or valuation.valuation_date.isoformat() != analysis["valuation_date"]:
            raise ValueError("ALIGNMENT_VALUATION_IDENTITY_MISMATCH")
        quote = QuoteSnapshot(valuation.symbol, None, None, QUOTE_STATUS_PENDING_EXTERNAL_DATA, [])
        if config.get("quote_bundle_binding") is not None:
            try:
                quote, result["quote"] = _qualified_quote(root, analysis, config["quote_bundle_binding"], now, read)
            except (OSError, ValueError, TypeError, KeyError, ArithmeticError) as error:
                result["quote"].update(status="BLOCKED", reason_codes=["QUOTE_REPLAY_FAILED: " + str(error)])
        result["quote_date"] = result["quote"]["quote_date"]
        closing_export = None
        if config.get("szse_capital_export_binding") is not None and quote.quote_date is not None:
            from ...infrastructure.filings.szse_capital_export import replay_szse_capital_export

            closing_export = replay_szse_capital_export(binding=config["szse_capital_export_binding"],
                symbol=analysis["symbol"], comparison_date=quote.quote_date, now=now, read=read)
        windows, scans, source_windows = [], [], []
        event_error = None
        try:
            windows, scans = _event_windows(root, analysis, config.get("event_observation_bindings", []), now, read)
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
            event_error = "EVENT_SOURCE_REPLAY_FAILED: " + str(error)
        # Supplemental acquisition proves original identity only. Its earlier
        # dates/announcements cannot change the model validity/review window.
        source_windows, _ = _event_windows(root, analysis,
            config.get("source_observation_bindings", []), now, read)
        reconciliation, reconciliation_error = None, None
        reconciliation_pages = {}
        if config.get("reconciliation_binding") is not None:
            try:
                reconciliation = _reconcile(root, analysis, config["reconciliation_binding"],
                    quote.quote_date, windows, now, read, source_windows, closing_export=closing_export,
                    verified_pdf_pages=reconciliation_pages)
            except (OSError, ValueError, TypeError, KeyError, AttributeError, ArithmeticError) as error:
                reconciliation_error = "RECONCILIATION_REPLAY_FAILED: " + str(error)
        materiality, materiality_route = None, None
        try:
            materiality, materiality_route = _materiality(root, analysis,
                config.get("materiality_review_binding"), windows, scans, now, read)
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
            materiality_route = dict(status="EXISTING_MATERIALITY_REPLAY_REJECTED",
                review_binding=deepcopy(config.get("materiality_review_binding")), reason=str(error))
        checks, validity, bridge, ready = _assess(analysis, valuation, quote, result["quote"], windows, scans,
            reconciliation, materiality, materiality_route)
        if closing_export is not None:
            closing = (reconciliation or {}).get("calculated_closing_shares")
            if closing is not None and _number(closing) != _number(closing_export["ordinary_a_shares"]):
                raise ValueError("SZSE_CAPITAL_EXPORT_ROLLFORWARD_DISAGREEMENT")
            checks[1]["details"]["szse_capital_export"] = closing_export
        if reconciliation_error:
            for index in (1, 2):
                checks[index]["reason_codes"].append(reconciliation_error)
            ready = False
        if event_error:
            checks[3]["reason_codes"].append(event_error)
            ready = False
        # Official event terms are a separate research result. A parser success
        # neither changes frozen assumptions nor signs the materiality review.
        operating_events = _operating_events(analysis, windows, now, read, page_cache=event_pages)
        checks[3]["details"]["operating_event_research"] = operating_events
        financial_events = []
        for event in operating_events:
            facts = [fact for fact in event["facts"]
                     if fact["terms"].get("event_type") == "REPORTED_QUARTERLY_FINANCIAL_UPDATE"]
            if facts:
                financial_events.append({**event, "facts": facts})
        checks[4]["details"]["financial_update_research"] = financial_events
        financial_closure = _financial_update_closure_status(
            analysis, financial_events, operating_events=operating_events,
        )
        if financial_closure is not None:
            checks[4]["status"] = financial_closure["status"]
            checks[4]["reason_codes"] = financial_closure["reason_codes"]
            checks[4]["explanation"] = (
                "财务更新只有在精确原件、期间、候选、描述符及冷重算前驱全部一致时才通过；"
                "来源存在本身不证明已消费。"
            )
            checks[4]["details"]["recomputation_closure"] = financial_closure
            if len(financial_closure["consumed_closure"]) == 1:
                from .parent_financing_schedule_v1 import project_parent_financing_schedule

                consumed = financial_closure["consumed_closure"][0]
                observed = consumed.get("financing_comparison", {}).get("reported_ytd")
                if observed is not None:
                    try:
                        checks[4]["details"]["parent_financing_schedule"] = (
                            project_parent_financing_schedule(
                                period_end=consumed["period_end"], reported_ytd=observed,
                                issuance_events=financial_closure.get("subsequent_financing_issuance", []),
                            )
                        )
                    except (KeyError, ValueError, TypeError, ArithmeticError) as error:
                        checks[4]["details"]["parent_financing_schedule_error"] = str(error)
            all_reasons = list(dict.fromkeys(
                code for item in checks for code in item["reason_codes"]
            ))
            bridge_validity = validity
            if validity.status == "VALID" and all_reasons:
                bridge_validity = replace(
                    validity, status="UNKNOWN", material_event_found=None,
                    blockers=all_reasons,
                )
            bridge = bridge_with_quote(
                valuation, bridge_validity, quote, blockers=all_reasons,
            )
            validity = bridge_validity
            ready = (all(item["status"] == "PASS" for item in checks)
                     and bridge.bridge_status == "READY" and not bridge.blockers)
        from .candidate_event_impact import build_candidate_event_impact
        checks[3]["details"]["candidate_event_impact"] = build_candidate_event_impact(analysis, operating_events)
        from ...infrastructure.filings.opening_action_terms import parse_opening_action_terms
        # A covered scan can start before the valuation date. Reuse the verified
        # distribution originals for opening research without treating the rest
        # of the scan as a certified opening-action inventory.
        from ...quote_sessions import CHINA

        opening_cutoff = _day(analysis["valuation_date"])
        distribution_cutoff = quote.quote_date or opening_cutoff
        opening_windows = [*source_windows, *(
            dict(window, announcements=[
                event for event in window["announcements"]
                if (datetime.fromisoformat(event["published_at"]).astimezone(CHINA).date() <= distribution_cutoff
                    and event["title"].endswith((
                        "年度股东会决议公告", "年度股东大会决议公告", "权益分派实施公告",
                    )))
                or (datetime.fromisoformat(event["published_at"]).astimezone(CHINA).date() <= opening_cutoff
                    and re.search(r"(?:关于股份回购实施结果暨股份变动的公告|"
                                  r"关于调整20[0-9]{2}年年度利润分配方案每股分红金额的公告)$",
                                  event["title"]))
            ]) for window in windows
        )]
        opening_actions = _operating_events(analysis, opening_windows, now, read,
            parser=parse_opening_action_terms, page_cache=event_pages)
        opening_chain = _opening_chain_research(analysis, opening_actions, reconciliation)
        annual_implementation_events = [
            dict(facts=[fact for fact in event["facts"]
                        if fact["terms"].get("event_type") == "REPORTED_ANNUAL_DIVIDEND_IMPLEMENTATION_SCHEDULE"])
            for event in operating_events
        ]
        opening_chain["in_period_annual_approval_schedule_links"] = _annual_approval_schedule_links(
            [*opening_actions, *annual_implementation_events], end=distribution_cutoff, after=opening_cutoff)
        if analysis.get("opening_capital_original") is not None:
            try:
                cancellation = _first_input_opening_cancellation(
                    analysis, source_windows, now, read, event_pages)
                if cancellation is not None:
                    opening_chain["completed_cancellation_in_opening_basis"] = cancellation
            except (OSError, ValueError, TypeError, KeyError, ArithmeticError) as error:
                opening_chain["completed_cancellation_replay_error"] = str(error)
        basis_followup = _basis_followup(analysis, reconciliation, opening_chain, windows,
            quote.quote_date, operating_events)
        for index in (1, 2):
            checks[index]["details"]["opening_action_research"] = opening_actions
            checks[index]["details"]["opening_action_chain"] = opening_chain
            checks[index]["details"]["basis_followup"] = basis_followup
            if opening_chain["outstanding_authorizations"]:
                checks[index]["reason_codes"].append("INTERIM_DISTRIBUTION_AUTHORIZATION_FOLLOWUP_NOT_RECONCILED")
                checks[index]["status"] = "BLOCKED"
                ready = False
        if opening_chain["outstanding_authorizations"]:
            followup_blockers = list(dict.fromkeys([*validity.blockers,
                "INTERIM_DISTRIBUTION_AUTHORIZATION_FOLLOWUP_NOT_RECONCILED"]))
            validity = replace(validity, status="UNKNOWN" if validity.status == "VALID" else validity.status,
                blockers=followup_blockers)
            bridge = bridge_with_quote(valuation, validity, quote, blockers=followup_blockers)
        result.update(checks=checks, model_validity=json.loads(validity.to_json()),
            price_bridge=json.loads(bridge.to_json()), currentpricecomparison=ready,
            status="ALIGNED_FOR_RESEARCH_COMPARISON" if ready else "BLOCKED",
            reason_codes=list(dict.fromkeys(code for item in checks for code in item["reason_codes"])))
        # Replay native verification again, including raw HTTP/PDF/calendar inputs.
        if result["quote"]["status"] == "QUALIFIED":
            _, again = _qualified_quote(root, analysis, config["quote_bundle_binding"], now, read)
            if again != result["quote"]:
                raise ValueError("QUOTE_CHANGED_DURING_ALIGNMENT")
        if opening_actions != _operating_events(analysis, opening_windows, now, read,
                parser=parse_opening_action_terms, page_cache=event_pages):
            raise ValueError("OPENING_ACTION_TERMS_CHANGED_DURING_READ")
        if operating_events != _operating_events(analysis, windows, now, read, page_cache=event_pages):
            raise ValueError("OPERATING_EVENT_TERMS_CHANGED_DURING_READ")
        if scans:
            again, _ = _event_windows(root, analysis, config["event_observation_bindings"], now, read)
            if again != windows:
                raise ValueError("EVENTS_CHANGED_DURING_ALIGNMENT")
        if reconciliation is not None:
            again = _reconcile(root, analysis, config["reconciliation_binding"], quote.quote_date, windows, now, read, source_windows, closing_export=closing_export,
                    verified_pdf_pages=reconciliation_pages)
            if again != reconciliation:
                raise ValueError("RECONCILIATION_CHANGED_DURING_ALIGNMENT")
        if source_windows:
            again, _ = _event_windows(root, analysis, config["source_observation_bindings"], now, read)
            if again != source_windows:
                raise ValueError("SUPPLEMENTAL_SOURCES_CHANGED_DURING_ALIGNMENT")
        if materiality is not None:
            again, route_again = _materiality(root, analysis, config["materiality_review_binding"], windows, scans, now, read)
            if again != materiality or route_again != materiality_route:
                raise ValueError("MATERIALITY_CHANGED_DURING_ALIGNMENT")
        for path, sha in list(verified.items()):
            _bound(root, dict(path=path, sha256=sha))
        _attach_confirmed_unlock_facts(
            reconciliation, windows, basis_followup["capital_event_classifications"],
        )
        result["evidence_bindings"] = [dict(path=path, sha256=sha) for path, sha in verified.items()]
        return result
    except (OSError, ValueError, KeyError, TypeError, AttributeError, ArithmeticError) as error:
        failed = _initial(analysis, now)
        failed["reason_codes"] = ["ALIGNMENT_SOURCE_OR_CONTRACT_REJECTED: " + str(error)]
        return failed


def attach_pending_candidate_alignment(*, root, analysis, now):
    result = load_pending_candidate_alignment(root=root, analysis=analysis, now=now)
    analysis["current_alignment"] = result
    joint = analysis.get("joint_capital_review")
    if joint and joint.get("conditional_price"):
        price = joint["conditional_price"]
        price["alignment"] = deepcopy(result)
        # Legacy price_comparison/currentpricecomparison describe the dated draft
        # and stay unchanged. New research alignment has its own scoped result.
    return analysis
