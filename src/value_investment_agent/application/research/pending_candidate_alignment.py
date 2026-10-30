"""Read-only evidence alignment for a recomputed, unapproved research candidate.

Reuse native quote/coverage/validity/bridge contracts. Publication coverage is
not effective corporate-action coverage. No date rolling or price adjustment.
"""
from copy import deepcopy
from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal, localcontext
import json
import re
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
    if (len(text) > 120000 or f"证券代码:{symbol}" not in compact(pages[0])
            or "权益分派实施公告" not in compact(pages[0]) or "差异化分红送转:否" not in text
            or any(word in text for word in ("更正", "修订", "取消", "作废", "撤销", "送红股", "转增股本", "配股", "拆股", "合股", "股份转换"))):
        raise ValueError("UNSUPPORTED_CASH_IMPLEMENTATION_LAYOUT")
    schemes = [(i, m[1]) for i, p in enumerate(pages, 1)
               if (m := re.search(r"\(三\)分配方案:(.*?)三、相关日期", compact(p)))]
    number = r"((?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)(?:\.[0-9]+)?)"
    terms = re.fullmatch(r"本次利润分配以方案实施前的公司总股本扣除回购专用账户内的股份"
        + number + r"股为基数,每股派发现金红利" + number
        + r"元\(含税\),共计派发现金红利" + number + r"元。", schemes[0][1]) if len(schemes) == 1 else None
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
    return dict(parser_version="sse-repurchase-excluded-gross-cash-scheme-v1", symbol=symbol,
        cash_per_share=str(cash), eligible_distribution_shares=str(shares), total_gross_cash=str(total),
        published_date=published, **dates, currency="CNY", body_terms_reconciled=True,
        term_pages=dict(scheme=[schemes[0][0]], chronology=sorted({r["page"] for r in candidates})),
        amendment_chain_verified=False, cash_payment_status="DECLARED_SCHEDULE_NOT_PROOF_OF_RECEIPT",
        action="no_order")



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
        closing_capital=dict(status="EXACT_CLOSING_REPORT_ANCHOR_MISSING", as_of=end.isoformat(),
            ordinary_shares=None),
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
            terms = parse_interim_capital_distribution(cache[sha], symbol=analysis["symbol"])
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
            if report_end == end:
                result["closing_capital"].update(status="EXACT_REPORT_DATE_SHARES_VERIFIED",
                    ordinary_shares=terms["ordinary_shares"], evidence_binding=binding,
                    continuity_to_opening_verified=False)
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
    if result["distribution_inclusion"]["comparisons"]:
        result["distribution_inclusion"]["status"] = "SOURCE_AMOUNTS_COMPARED_INCLUSION_UNVERIFIED"
    return result


def _reconcile(root, analysis, ref, end, windows, now, read, source_windows=()):
    """Replay source-anchored public research arithmetic, never approve materiality.

    Unknown opening pending state/closing shares remain explicit gaps. Every
    original excerpt is re-extracted; listed cash paid before valuation is retained
    but never deducted again. Effective share changes/cash inside the interval
    require a separately recomputed valuation, not a mechanical price adjustment.
    """
    from ...corporate_actions import validate_cash_distribution
    from ...infrastructure.filings.pdf_text import extract_pages
    from ...infrastructure.filings.official_pdf import validate_pdf_original

    ledger = load_json_object(read(ref), "candidate public basis reconciliation")
    start = _day(analysis["valuation_date"])
    if (ledger["schema_version"] != "pending-candidate-basis-reconciliation-v1"
            or ledger["candidate_binding"] != analysis["review_binding"]["candidate_binding"]
            or ledger["input_descriptor_sha256"] != analysis["input_descriptor_sha256"]
            or _day(ledger["valuation_date"]) != start
            or end is None or _day(ledger["comparison_date"]) != end or end < start
            or ledger["currency"] != "CNY" or ledger["share_basis"] != "ordinary_share_unadjusted"):
        raise ValueError("RECONCILIATION_EXACT_BASIS_MISMATCH")
    cache, evidence = {}, []
    native_sources = {}
    for source in analysis.get("source_catalog", []):
        if (source.get("kind") == "official_issuer_filing"
                and (source.get("issuer_identity") or {}).get("security_code") == analysis["symbol"]):
            key = (source["local_path"], source["sha256"], source["location"])
            native_sources[key] = source["source_available_at"]
    for window in [*windows, *source_windows]:
        for announcement in window["announcements"]:
            for source in announcement["evidence_refs"]:
                key = (source["path"], source["sha256"], source["source_url"])
                native_sources[key] = window["acquired_at"]

    def anchors(rows, *, numbers=(), dates=()):
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
                    or _day(url.path.split("/")[2]) > stamp.date()):
                raise ValueError("OFFICIAL_RECONCILIATION_SOURCE_UNAVAILABLE")
            if binding["sha256"] not in cache:
                validate_pdf_original(path)
                cache[binding["sha256"]] = extract_pages(path)
            pages = cache[binding["sha256"]]
            page, excerpt = item["physical_page"], item["excerpt"]
            if (type(page) is not int or not 1 <= page <= len(pages)
                    or not isinstance(excerpt, str) or not excerpt.strip()
                    or "".join(excerpt.split()) not in "".join(pages[page - 1].split())
                    or not re.search(r"(?:证券|公司|股票)代码[:：]?" + analysis["symbol"],
                                     "".join(pages[0].split()))):
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
    anchors(opening["evidence"], numbers=[opening_value], dates=[start])
    original_hashes = {s["sha256"] for s in analysis["source_bindings"]}
    capital_source_ids = {a["source_id"] for a in analysis.get("official_fact_anchors", [])
                          if a["field"] == "ordinary_shares"}
    # A separately retained copy is the same consumed original only when both
    # its bytes and official document identity match the consumed capital anchor.
    if any(e["binding"]["sha256"] not in original_hashes or
            "cninfo:" + urlparse(e["source_url"]).path.rsplit("/", 1)[1].split(".")[0] not in capital_source_ids
            for e in opening["evidence"]):
        raise ValueError("OPENING_CAPITAL_SOURCE_NOT_CONSUMED")
    native_opening = any(a.get("field") == "ordinary_shares"
        and a.get("source_id") in capital_source_ids
        and a.get("source_value") == opening["value"]
        and a.get("unit") == "shares" and a.get("period_end") == start.isoformat()
        for a in analysis.get("official_fact_anchors", []))
    actions, cash = ledger["share_actions"], ledger["distributions"]
    if not isinstance(actions, list) or not isinstance(cash, list):
        raise ValueError("RECONCILIATION_ACTION_ARRAYS_REQUIRED")
    ids, total, action_rows = set(), opening_value, []
    for row in actions:
        if not isinstance(row["id"], str) or not row["id"] or row["id"] in ids:
            raise ValueError("UNIQUE_ACTION_ID_REQUIRED")
        ids.add(row["id"])
        effective, shares = _day(row["effective_date"]), _number(row["shares"])
        if not start < effective <= end or row["kind"] not in {"INCREASE", "DECREASE"} or shares <= 0 or shares != shares.to_integral_value():
            raise ValueError("UNSUPPORTED_EFFECTIVE_SHARE_ACTION")
        anchors(row["evidence"], numbers=[shares], dates=[effective])
        with localcontext() as context:
            context.prec = 80
            total += shares if row["kind"] == "INCREASE" else -shares
        action_rows.append(deepcopy(row))
    if total <= 0:
        raise ValueError("NONPOSITIVE_RECONCILED_SHARE_COUNT")
    closing, closing_value = ledger.get("closing_shares"), None
    gaps = []
    if closing is None:
        gaps.append("CLOSING_SHARE_COUNT_UNVERIFIED")
    else:
        closing_value = _number(closing["value"])
        closing_date = _day(closing["as_of"])
        if closing_date != end or closing_value != total:
            raise ValueError("SHARE_ROLLFORWARD_DOES_NOT_RECONCILE")
        anchors(closing["evidence"], numbers=[closing_value], dates=[closing_date])
    period_cash, cash_rows = Decimal(0), []
    for row in cash:
        if not isinstance(row["id"], str) or not row["id"] or row["id"] in ids:
            raise ValueError("UNIQUE_ACTION_ID_REQUIRED")
        ids.add(row["id"])
        amount = validate_cash_distribution(row)
        ex, payment, record = (_day(row[key]) for key in ("ex_date", "cash_payment_date", "record_date"))
        anchors(row["evidence"], numbers=[_number(row["cash_amount"])], dates=[record, ex, payment])
        parsed, parse_error = None, None
        hashes = {e["binding"]["sha256"] for e in row["evidence"]}
        if len(hashes) == 1:
            try:
                parsed = _cash_terms(cache[next(iter(hashes))], analysis["symbol"])
            except ValueError as error:
                parse_error = str(error)
        if parsed is not None:
            if (Decimal(parsed["cash_per_share"]) != amount
                    or any(parsed[k] != row[k] for k in ("record_date", "ex_date", "cash_payment_date"))
                    or any('/finalpage/' + parsed["published_date"] + '/' not in e["source_url"] for e in row["evidence"])):
                raise ValueError("CASH_LEDGER_DIFFERS_FROM_NATIVE_IMPLEMENTATION_FIELDS")
        if payment > end:
            treatment = "PENDING_PAYMENT_REQUIRES_REVIEW"
            gaps.append("PENDING_DISTRIBUTION_PAYMENT")
        elif ex <= start and payment <= start:
            treatment = "BEFORE_VALUATION_DATE_ALREADY_OUTSIDE_INTERVAL"
        elif start < ex <= end:
            treatment = "IN_PERIOD_MODEL_INCLUSION_REQUIRES_RECOMPUTATION"
            with localcontext() as context:
                context.prec = 80
                period_cash += amount
        else:
            treatment = "OPENING_EX_ENTITLEMENT_PAID_IN_PERIOD_REQUIRES_REVIEW"
            gaps.append("OPENING_DISTRIBUTION_ENTITLEMENT_UNRECONCILED")
        cash_rows.append(dict(**deepcopy(row), period_treatment=treatment,
            arithmetic_cash_per_share=str(amount), verified_cash_per_share=str(amount) if parsed else None,
            field_semantics_status="NATIVE_IMPLEMENTATION_FIELDS_VERIFIED" if parsed else "PUBLIC_RESEARCH_ARITHMETIC_NOT_NATIVE_FIELD_VERIFIED",
            native_terms=parsed, field_semantics_reason=parse_error,
            price_deduction_applied="0", model_inclusion=treatment if parsed and ex <= start and payment <= start else "NOT_NATIVE_VERIFIED"))
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
    announced = {row["announcement_id"]: row for window in windows for row in window["announcements"]}
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
        if item["disposition"] in {"SHARE_ACTION", "CASH_DISTRIBUTION"} and not any(
                e["binding"]["sha256"] in announced_hashes for row in [*actions, *cash] for e in row["evidence"]):
            gaps.append("REVIEWED_ACTION_MISSING_LEDGER_ROW: " + identity)
    if reviewed != set(announced):
        gaps.append("PUBLIC_ACTION_REVIEW_DOES_NOT_COVER_ALL_ANNOUNCEMENTS")
    if not windows or not any(_day(w["scan_from"]) <= start and _day(w["scan_to"]) >= end for w in windows):
        gaps.append("ACTION_PUBLICATION_WINDOW_MISSING")
    if any(not w["full_calendar_window_elapsed"] for w in windows):
        gaps.append("ACTION_COVERAGE_IS_RETRIEVAL_SNAPSHOT_ONLY")
    arithmetic_complete = closing_value is not None
    # Exact excerpts/number/date co-occurrence and researcher classifications
    # are not a sealed semantic consumer. No caller-provided review/NO_EFFECT or
    # empty pending list may establish effective-action coverage or price basis.
    native_fields = _native_basis_fields(analysis, start, end, now, native_sources, read, cache, cash_rows)
    for report in native_fields["reports"]:
        if report["binding"] not in evidence:
            evidence.append(deepcopy(report["binding"]))
    closing_status = native_fields["closing_capital"]["status"]
    if closing_status == "EXACT_CLOSING_REPORT_ANCHOR_MISSING":
        gaps.append("EXACT_COMPARISON_DATE_NATIVE_CAPITAL_ANCHOR_MISSING")
    else:
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
    compatible = same_basis
    if same_basis:
        closing_value = opening_value
        gaps = []
    if actions:
        gaps.append("EFFECTIVE_SHARE_ACTION_REQUIRES_CANDIDATE_RECOMPUTATION")
    if period_cash:
        gaps.append("IN_PERIOD_CASH_FLOW_INCLUSION_REQUIRES_CANDIDATE_RECOMPUTATION")
    return dict(status="RECONCILED" if same_basis else "PARTIAL", arithmetic_status="RECONCILED" if arithmetic_complete else "PARTIAL",
        scope="SOURCE_BOUND_PUBLIC_RESEARCH_ARITHMETIC_NOT_FIELD_OR_MATERIALITY_APPROVAL", action="no_order",
        opening_shares=str(opening_value), calculated_closing_shares=str(total),
        opening_shares_semantics="NATIVE_CONSUMED_FACT_MATCHED" if native_opening else "NOT_VERIFIED",
        closing_shares=str(closing_value) if closing_value is not None else None,
        share_actions=action_rows, distributions=cash_rows, period_cash_per_share=str(period_cash),
        period_cash_coverage_complete=same_basis,
        native_basis_semantics_verified=same_basis,
        native_source_consumption=native_fields,
        engineering_gap=None if same_basis else (
            "已接入正式中报股本、回购注销及分配字段；尚缺其他公告类型的有效行动语义消费者。"
            if native_fields["reports"] else "绑定原件尚未匹配已支持的正式中报股本及分配字段。"),
        current_price_basis_compatible=compatible, formal_eligibility=False,
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
        proof = verifier(root, observation, symbol=analysis["symbol"],
            required_from=start, required_to=end, now=now)
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
    package_ref = analysis["review_binding"]["package_binding"]
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
            scan_path=read(scan_ref), scan_sha256=scan_ref["sha256"])
    except (ValueError, KeyError, TypeError, AttributeError, OSError) as error:
        unsupported = str(error) == "Exact annual-retention-v2 scenario required; no scalar retention"
        route.update(status="NATIVE_MATERIALITY_CANDIDATE_ADAPTER_UNSUPPORTED" if unsupported else "NATIVE_MATERIALITY_HANDOFF_REJECTED",
            reason=str(error), engineering_gap="既有材料性消费者不支持此候选模型格式；需接通现有适配器。" if unsupported else None)
        return None, route
    route["model_context"] = handoff["model_context"]
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
    covering = [(w, s) for w, s in zip(windows, scans)
                if end is not None and s.scan_from <= start and s.scan_to >= end]
    if not covering:
        reasons.append("EVENT_WINDOW_DOES_NOT_COVER_VALUATION_TO_QUOTE")
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
    checks.append(_check("distributions", "PASS" if basis_pass else "BLOCKED",
        [] if basis_pass else list(dict.fromkeys(["PERIOD_DISTRIBUTIONS_AND_MODEL_INCLUSION_NOT_RECONCILED", *basis_reasons])),
        "估值已包含条件分配路径；须核验期间实际除息、支付及其是否已内含，不能把预测分红再加回，也不能仅凭本期无公告认定无分配。",
        analysis["source_bindings"], period_from=start.isoformat(), period_to=end.isoformat() if end else None,
        actual_cash_per_share=reconciliation["period_cash_per_share"]
            if reconciliation and reconciliation["period_cash_coverage_complete"] else None,
        known_listed_period_cash_per_share=reconciliation["period_cash_per_share"] if reconciliation else None,
        inclusion_status="SOURCE_RECONCILED_NO_UNCONSUMED_PERIOD_CASH" if basis_pass else "NOT_RECONCILED",
        adjustment_applied=False, reconciliation=reconciliation))
    checks.append(_check("material_events", "PASS" if event_pass else "BLOCKED",
        list(dict.fromkeys([*reasons, *validity.blockers])),
        "原生扫描重放只确认原件与检索范围；当日快照和待材料性复核公告不能授予模型VALID。",
        refs, windows=windows, materiality_review_route=materiality_route,
        financial_statement_changed=validity.financial_statement_changed,
        capital_structure_changed=validity.capital_structure_changed))
    consumed_hashes = {source["sha256"] for source in analysis["source_bindings"]}
    fact_source_ids = {anchor["source_id"] for anchor in analysis.get("official_fact_anchors", [])}
    matched, unresolved = [], []
    for scan in scans:
        for item in scan.announcements:
            row = dict(announcement_id=item.announcement_id, title=item.title,
                published_at=item.published_at.isoformat(), source_url=item.source_url,
                evidence_refs=list(item.evidence_refs))
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


def load_pending_candidate_alignment(*, root, analysis, now):
    """No discovery by recency, no registration, no approval and no writes."""
    from .value_research_analysis import _bound
    result = _initial(analysis, now)
    verified = {}

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
        config_path = root / CONFIG_DIRECTORY / (digest + ".json")
        if not config_path.is_file():
            result["reason_codes"] = ["EXACT_CANDIDATE_ALIGNMENT_BINDING_MISSING"]
            return result
        config_ref = dict(path=config_path.relative_to(root).as_posix(), sha256=sha256_file(config_path))
        config = load_json_object(read(config_ref), "candidate alignment inputs")
        if (config["schema_version"] != INPUT_SCHEMA or config["candidate_binding"] != result["candidate_binding"]
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
        if config.get("reconciliation_binding") is not None:
            try:
                reconciliation = _reconcile(root, analysis, config["reconciliation_binding"],
                    quote.quote_date, windows, now, read, source_windows)
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
        if reconciliation_error:
            for index in (1, 2):
                checks[index]["reason_codes"].append(reconciliation_error)
            ready = False
        if event_error:
            checks[3]["reason_codes"].append(event_error)
            ready = False
        result.update(checks=checks, model_validity=json.loads(validity.to_json()),
            price_bridge=json.loads(bridge.to_json()), currentpricecomparison=ready,
            status="ALIGNED_FOR_RESEARCH_COMPARISON" if ready else "BLOCKED",
            reason_codes=list(dict.fromkeys(code for item in checks for code in item["reason_codes"])))
        # Replay native verification again, including raw HTTP/PDF/calendar inputs.
        if result["quote"]["status"] == "QUALIFIED":
            _, again = _qualified_quote(root, analysis, config["quote_bundle_binding"], now, read)
            if again != result["quote"]:
                raise ValueError("QUOTE_CHANGED_DURING_ALIGNMENT")
        if scans:
            again, _ = _event_windows(root, analysis, config["event_observation_bindings"], now, read)
            if again != windows:
                raise ValueError("EVENTS_CHANGED_DURING_ALIGNMENT")
        if reconciliation is not None:
            again = _reconcile(root, analysis, config["reconciliation_binding"], quote.quote_date, windows, now, read, source_windows)
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
