"""Read-only, source-bound financing observations; never exhaustive debt admission."""
from datetime import datetime, date, timezone
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re

from ..filings.pdf_text import extract_pages
from ..filings.official_pdf import validate_pdf_original
from ..filings.financial_funding_scope import extract_financial_funding_observations
from .value_evidence_enrichment_v1 import extract_financing_note_candidates, _issuer_legal_owner, extract_debt_balance_candidates

from .value_evidence_enrichment_v1 import (
    extract_debt_balance_candidates, _statement_unit, _consolidated_currency_context,
)
from ...filing_extract import extract_candidates_from_pages
from ...disclosures import collect_latest_reports

VERSION = "official-funding-details-v1"
FINANCIAL_FIELDS = ("cash", "group_net_profit", "operating_cash_flow",
                    "total_assets", "total_liabilities")
MAX_AUTOMATIC_SOURCES = 5


def _financial_rows(pages, source):
    # Reuse retained-annual primitives without its on-disk cache writes.
    period = source["period"]
    rows = extract_debt_balance_candidates(pages, period, balance_totals=True, include_equity=True)
    rows = [r for r in rows if r["field_name"] in {"total_assets", "total_liabilities"}]
    candidates = extract_candidates_from_pages(pages)
    currency = _consolidated_currency_context(pages)
    titles = re.compile(r"^(?:[0-9一二三四五六七八九十]+[、.．]\s*)?((?:合并|母公司|公司)?(?:资产负债表|利润表|现金流量表))$")
    active, multiplier, evidence, header = None, None, {}, None
    number = r"-?(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)\.[0-9]{2}"
    label_patterns = {
        "cash": r"货\s*币\s*资\s*金",
        "operating_cash_flow": r"经\s*营\s*活\s*动\s*产\s*生\s*的\s*现\s*金\s*流\s*量\s*净\s*额",
        "group_net_profit": r"[一二三四五六七八九十]+、\s*净利润[（(]净亏损以[^）)]+[）)]",
    }
    expected = {"cash": "合并资产负债表", "group_net_profit": "合并利润表",
                "operating_cash_flow": "合并现金流量表"}
    segments = []
    for page_no, page in enumerate(pages, 1):
        lines = page.splitlines()
        cuts = [i for i, line in enumerate(lines) if titles.fullmatch(line.strip())]
        starts = sorted(set([0] + cuts))
        segments.extend((page_no, "\n".join(lines[start:end]))
                        for start, end in zip(starts, starts[1:]+[len(lines)]))
    for page_no, page in segments:
        found = [(i, titles.fullmatch(line.strip())) for i, line in enumerate(page.splitlines())
                 if titles.fullmatch(line.strip())]
        if len(found) > 1:
            active = None
            continue
        if found:
            active = found[0][1][1]
            if not active.startswith("合并"):
                active = None
                continue
            scan = "\n".join(page.splitlines()[found[0][0]+1:])
            # Header ends before the first financial row; no amounts supply dates.
            header_text = scan.split("流动资产", 1)[0] if active == "合并资产负债表" else scan.split("一、", 1)[0]
            compact = "".join(header_text.split())
            if active == "合并资产负债表":
                dates = re.findall(r"[0-9]{4}年[0-9]{1,2}月[0-9]{1,2}日", compact.split("项目", 1)[-1])
                valid = dates == [period[:4]+"年12月31日", str(int(period[:4])-1)+"年12月31日"]
            else:
                years = re.findall(r"[0-9]{4}年度", compact.split("项目", 1)[-1])
                valid = years == [period[:4]+"年度", str(int(period[:4])-1)+"年度"]
            multiplier, evidence = _statement_unit(header_text, page_no, currency)
            header = dict(table_header_page=page_no, table_header_excerpt=header_text)
            if not valid or multiplier is None:
                active = None
        if not active:
            continue
        if not found and re.search(r"(?:单位|币种)\s*[：:]", page):
            repeated_multiplier, _ = _statement_unit(page, page_no, currency)
            if repeated_multiplier != multiplier or re.search(r"币种\s*[：:]\s*(?!人民币)\S+", page):
                active = None
                continue
        if any(word in page for word in ("调整前", "调整后", "重述")):
            active = None
            continue
        for field, pattern in label_patterns.items():
            if expected[field] != active:
                continue
            # Exactly two printed cells; a note index is allowed only for cash.
            note = r"(?:[0-9]+|[一二三四五六七八九十]+[（(][0-9]+[）)])\s+" if field == "cash" else ""
            regex = r"(?m)^[ \t]*" + pattern + r"\s+" + ("(?:"+note+")?" if note else "") + "("+number+r")\s+("+number+r")[ \t]*$"
            for match in re.finditer(regex, page):
                value = str(Decimal(match[1].replace(",", ""))*multiplier)
                existing = [c for c in candidates
                            if c["field_name"] == field and c["page"] == page_no]
                if existing and any(c["unit"] != "CNY" or Decimal(c["value"]) != Decimal(value)
                                    for c in existing):
                    continue
                rows.append(dict(field_name=field, value=value,
                    prior_value=str(Decimal(match[2].replace(",", ""))*multiplier),
                    page=page_no, excerpt=match[0], period_label=period,
                    prior_period_label=str(int(period[:4])-1)+"-12-31",
                    unit="CNY", currency="CNY", statement_scope="consolidated",
                    column_status="ORDERED_TWO_COLUMNS", **header, **evidence))
    # Multiple occurrences are not a license to pick the matching amount.
    return [dict(r, symbol=source["symbol"], source_binding=dict(source),
                 sha256=source["sha256"], financial_fact_admitted=False, action="no_order")
            for r in rows if sum(x["field_name"] == r["field_name"] for x in rows) == 1]



def _time(value):
    result = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("AWARE_TIME_REQUIRED")
    return result


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def collect_annual_sources(root, output_dir, *, symbols, period, allow_network):
    """Archive a bounded set of exact-period statutory annual reports.

    This is an evidence acquisition adapter, not a financial admission decision:
    only the existing ``load`` parser can decide which printed cells are usable.
    The bounded list is supplied by the current research queue, never inferred
    from a company name or hard-coded security list.
    """
    if allow_network is not True:
        raise ValueError("EXPLICIT_PUBLIC_NETWORK_AUTHORIZATION_REQUIRED")
    if (not isinstance(period, str) or not re.fullmatch(r"[0-9]{4}-12-31", period)
            or not isinstance(symbols, list) or not 1 <= len(symbols) <= MAX_AUTOMATIC_SOURCES
            or any(not isinstance(symbol, str) or not re.fullmatch(r"[0-9]{6}", symbol) for symbol in symbols)
            or len(set(symbols)) != len(symbols)):
        raise ValueError("INVALID_BOUNDED_ANNUAL_SOURCE_REQUEST")
    root = Path(root).resolve()
    output = (Path(output_dir) if Path(output_dir).is_absolute() else root / output_dir).resolve()
    if not output.is_relative_to(root) or output.exists():
        raise ValueError("NEW_PROJECT_RELATIVE_OUTPUT_REQUIRED")
    output.mkdir(parents=True)
    reports = collect_latest_reports(symbols, output / "originals")
    sources, failures = [], []
    for symbol in symbols:
        annual = [row for row in reports if row["symbol"] == symbol and row["report_kind"] == "annual"
                  and row["report_period"] == period]
        if len(annual) != 1:
            failures.append(dict(symbol=symbol, reason="EXACT_PERIOD_ANNUAL_REPORT_NOT_AVAILABLE",
                                 found_periods=sorted({row["report_period"] for row in reports
                                                       if row["symbol"] == symbol and row["report_kind"] == "annual"})))
            continue
        row = annual[0]
        file_path = Path(row["local_path"]).resolve()
        if not file_path.is_relative_to(root):
            raise ValueError("ARCHIVED_ANNUAL_OUTSIDE_PROJECT")
        sources.append(dict(symbol=symbol, period=period,
                            path=file_path.relative_to(root).as_posix(), sha256=_sha(file_path),
                            source_url=row["source_url"], available_at=row["fetched_at"].astimezone(timezone.utc).isoformat()))
    manifest = dict(schema_version=VERSION, action="no_order", sources=sources,
                    collection=dict(requested_symbols=symbols, period=period,
                                    status="COMPLETE" if len(sources) == len(symbols) else "PARTIAL",
                                    failures=failures,
                                    collected_at=datetime.now(timezone.utc).isoformat()))
    manifest_path = output / "manifest.json"
    manifest_path.write_bytes(json.dumps(manifest, ensure_ascii=False, sort_keys=True,
                                         separators=(",", ":")).encode("utf-8"))
    return dict(path=manifest_path.relative_to(root).as_posix(), sha256=_sha(manifest_path))


def merge_annual_source_manifests(root, output_dir, *, existing_binding, new_binding):
    """Append a new bounded collection without rewriting old source bindings.

    The archive itself is the continuation cursor: already archived symbols are
    excluded by the caller on the next run.  This function only merges two
    hash-bound manifests and never downloads or reparses a filing.
    """
    root = Path(root).resolve()
    output = (Path(output_dir) if Path(output_dir).is_absolute() else root / output_dir).resolve()
    if not output.is_relative_to(root) or output.exists():
        raise ValueError("NEW_PROJECT_RELATIVE_OUTPUT_REQUIRED")
    _, old_raw = _bound(root, existing_binding)
    _, new_raw = _bound(root, new_binding)
    old, new = json.loads(old_raw), json.loads(new_raw)
    for payload in (old, new):
        if (not isinstance(payload, dict) or payload.get("schema_version") != VERSION
                or payload.get("action", "no_order") != "no_order"
                or not isinstance(payload.get("sources"), list)):
            raise ValueError("INVALID_ANNUAL_SOURCE_MANIFEST")
    sources = {item.get("symbol"): item for item in old["sources"]}
    for item in new["sources"]:
        symbol = item.get("symbol")
        if not isinstance(symbol, str) or not re.fullmatch(r"[0-9]{6}", symbol):
            raise ValueError("INVALID_ANNUAL_SOURCE_SYMBOL")
        prior = sources.get(symbol)
        if prior is not None and prior != item:
            raise ValueError("ARCHIVED_SYMBOL_SOURCE_CONFLICT:" + symbol)
        sources[symbol] = item
    failures_by_symbol = {}
    for payload in (old, new):
        for failure in (payload.get("collection") or {}).get("failures") or []:
            symbol = failure.get("symbol") if isinstance(failure, dict) else None
            if not isinstance(symbol, str) or not re.fullmatch(r"[0-9]{6}", symbol):
                raise ValueError("INVALID_ANNUAL_COLLECTION_FAILURE")
            prior = failures_by_symbol.get(symbol)
            if prior is not None and prior != failure:
                raise ValueError("ANNUAL_COLLECTION_FAILURE_CONFLICT:" + symbol)
            failures_by_symbol[symbol] = failure
    requested = []
    for payload in (old, new):
        requested.extend((payload.get("collection") or {}).get("requested_symbols") or [])
    merged = dict(
        schema_version=VERSION, action="no_order",
        sources=[sources[key] for key in sorted(sources)],
        collection=dict(
            requested_symbols=list(dict.fromkeys(requested)),
            period=((new.get("collection") or {}).get("period") or
                    (old.get("collection") or {}).get("period")),
            status="PARTIAL" if failures_by_symbol else "COMPLETE",
            failures=[failures_by_symbol[key] for key in sorted(failures_by_symbol)],
            merged_at=datetime.now(timezone.utc).isoformat(),
            prior_manifests=[existing_binding, new_binding],
        ),
    )
    output.mkdir(parents=True)
    manifest_path = output / "manifest.json"
    manifest_path.write_bytes(json.dumps(merged, ensure_ascii=False, sort_keys=True,
                                         separators=(",", ":")).encode("utf-8"))
    return dict(path=manifest_path.relative_to(root).as_posix(), sha256=_sha(manifest_path))


def manifest_sources(root, binding):
    """Return the pinned source rows only; no parsing or network access."""
    _, raw = _bound(root, binding)
    manifest = json.loads(raw)
    if (not isinstance(manifest, dict) or manifest.get("schema_version") != VERSION
            or manifest.get("action", "no_order") != "no_order"
            or not isinstance(manifest.get("sources"), list)):
        raise ValueError("INVALID_ANNUAL_SOURCE_MANIFEST")
    return deepcopy(manifest["sources"])


def manifest_failed_symbols(root, binding):
    """Return pinned failed lookup symbols; these are continuation evidence too."""
    _, raw = _bound(root, binding)
    manifest = json.loads(raw)
    if (not isinstance(manifest, dict) or manifest.get("schema_version") != VERSION
            or manifest.get("action", "no_order") != "no_order"):
        raise ValueError("INVALID_ANNUAL_SOURCE_MANIFEST")
    failures = (manifest.get("collection") or {}).get("failures") or []
    symbols = set()
    for row in failures:
        symbol = row.get("symbol") if isinstance(row, dict) else None
        if not isinstance(symbol, str) or not re.fullmatch(r"[0-9]{6}", symbol):
            raise ValueError("INVALID_ANNUAL_COLLECTION_FAILURE")
        symbols.add(symbol)
    return symbols


def _bound(root, binding):
    if not isinstance(binding, dict) or set(binding) != {"path", "sha256"}:
        raise ValueError("INVALID_BINDING")
    if not isinstance(binding["path"], str) or not re.fullmatch(r"[0-9a-f]{64}", binding["sha256"]):
        raise ValueError("INVALID_BINDING")
    target = (Path(root) / binding["path"]).resolve()
    if not target.is_relative_to(Path(root).resolve()):
        raise ValueError("PATH_OUTSIDE_ROOT")
    raw = target.read_bytes()
    if hashlib.sha256(raw).hexdigest() != binding["sha256"]:
        raise ValueError("HASH_MISMATCH")
    return target, raw


def _normalize(line):
    compact = "".join(line.split())
    # Only printed equivalent labels/headers, never inferred cells or dates.
    if compact in {"项目期末数期初数", "种类期末数期初数"}:
        return compact.replace("期末数", "期末余额").replace("期初数", "期初余额")
    if re.match(r"^(?:[0-9]+、)?1年内到期的", compact):
        return re.sub(r"1\s*年内到期的", "一年内到期的", line)
    return line


def _field(row):
    label = "".join(row["source_label"].split())
    note = row["note"]
    if note == "其他应付款" and label == "财务公司吸收成员单位存款":
        return "financial_member_deposits"
    if note == "一年内到期的非流动负债":
        return {"一年内到期的租赁负债": "lease_liabilities_current",
                "一年内到期的长期借款": "long_term_borrowings_current",
                "一年内到期的应付债券": "bonds_payable_current",
                "一年内到期的长期应付款": "long_term_payables_current"}.get(label)
    if note == "其他流动负债" and label == "短期应付债券":
        return "short_term_bonds"
    if label == "合计":
        return {"短期借款": "short_term_borrowings", "长期借款": "long_term_borrowings_noncurrent",
                "租赁负债": "lease_liabilities_noncurrent",
                "长期应付款": "long_term_payables_noncurrent"}.get(note)
    return None


def _extract(pages, source):
    owner = _issuer_legal_owner(pages)
    if not owner or owner["security_code"] != source["symbol"]:
        raise ValueError("ISSUER_IDENTITY_MISMATCH")
    normalized = ["\n".join(_normalize(line) for line in page.splitlines()) for page in pages]
    packet = extract_financing_note_candidates(normalized, source["period"])
    result = []
    for row in packet["rows"]:
        field = _field(row)
        if not field:
            continue
        item = dict(row, field_name=field)
        # Every excerpt points back to unchanged original text, not normalized text.
        for key, page_key in (("excerpt", "page"), ("table_header_excerpt", "table_header_page")):
            original = [line.strip() for line in pages[item[page_key]-1].splitlines()
                        if _normalize(line.strip()) == item[key]]
            if len(set(original)) != 1:
                raise ValueError("AMBIGUOUS_ORIGINAL_EXCERPT")
            item[key] = original[0]
        result.append(item)
    # This primitive requires a dated, ordered consolidated balance header.
    for row in extract_financial_funding_observations(pages, source["period"]):
        result.append(dict(row, owner_evidence=owner,
                           table_header_page=row["unit_evidence_page"],
                           table_header_excerpt=pages[row["unit_evidence_page"]-1],
                           column_status=("ORDERED_TWO_COLUMNS" if row["value"] is not None
                                          else "UNKNOWN_SINGLE_COLUMN")))
    for row in result:
        row.update(symbol=source["symbol"], source_binding=dict(source),
                   sha256=source["sha256"], action="no_order",
                   financial_fact_admitted=False, complete_debt_verified=False)
    return result


def load(root, binding, evaluation_at):
    """Load an explicitly pinned manifest; no network, cache or publication writes.

    Manifest: {schema_version: VERSION, sources: [{symbol, period, path,
    sha256, source_url, available_at}]}. Optional action must be no_order.
    Invalid sources raise ValueError; no empty-success fallback.
    """
    now = _time(evaluation_at)
    _, raw = _bound(root, binding)
    manifest = json.loads(raw)
    collection = manifest.get("collection") if isinstance(manifest, dict) else None
    retained_failures = collection.get("failures") if isinstance(collection, dict) else None
    if (not isinstance(manifest, dict)
            or set(manifest) - {"schema_version", "sources", "action", "collection"}
            or manifest.get("schema_version") != VERSION
            or manifest.get("action", "no_order") != "no_order"
            or not isinstance(manifest.get("sources"), list)
            or (not manifest["sources"] and not isinstance(retained_failures, list))):
        raise ValueError("INVALID_MANIFEST")
    observations, financial_observations, seen, errors = [], [], set(), []
    balance_packets=[]
    for source in manifest["sources"]:
        if not isinstance(source, dict) or set(source) != {
                "symbol", "period", "path", "sha256", "source_url", "available_at"}:
            raise ValueError("INVALID_SOURCE")
        if not re.fullmatch(r"[0-9]{6}", source["symbol"]):
            raise ValueError("INVALID_SYMBOL")
        if not re.fullmatch(r"[0-9]{4}-12-31", source["period"]):
            raise ValueError("ONLY_EXPLICIT_FY_SUPPORTED")
        period = date.fromisoformat(source["period"])
        url = re.fullmatch(r"https://static\.cninfo\.com\.cn/finalpage/([0-9]{4}-[0-9]{2}-[0-9]{2})/[0-9]+\.PDF", source["source_url"])
        if not url:
            raise ValueError("INVALID_OFFICIAL_URL")
        available = _time(source["available_at"])
        if not period <= date.fromisoformat(url[1]) <= available.date() or available > now:
            raise ValueError("SOURCE_TIME_CONFLICT")
        key = (source["symbol"], source["period"])
        if key in seen or source["sha256"] in seen:
            raise ValueError("DUPLICATE_SOURCE")
        seen.update((key, source["sha256"]))
        pin = {k: source[k] for k in ("path", "sha256")}
        # Bind and hash-check the source before isolating parser failures.  A
        # corrupted path/hash is an invalid manifest, not a recoverable PDF
        # layout problem.
        path, _ = _bound(root, pin)
        try:
            validate_pdf_original(path)
            pages = extract_pages(path)
            rows = _extract(pages, source)
            financial = _financial_rows(pages, source)
            balance_packets.append(dict(source=source,packet=dict(
                balance_reconciliation_candidates=extract_debt_balance_candidates(pages,source['period'],balance_totals=True,include_equity=True),
                identity=dict(implementation_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()))))
            _bound(root, pin)
            if not rows and not financial:
                raise ValueError("NO_VERIFIABLE_FINANCIAL_OR_FUNDING_ROWS")
            observations.extend(rows)
            financial_observations.extend(financial)
        except (OSError, ValueError, KeyError, TypeError) as error:
            # A PDF layout or issuer-identity failure belongs to this source.
            # It must remain visible and block this issuer only, not discard
            # separately pinned originals that can still be replayed.
            errors.append(dict(symbol=source["symbol"], period=source["period"],
                               error_type=type(error).__name__, message=str(error)[:300],
                               source_url=source["source_url"], sha256=source["sha256"]))
    _bound(root, binding)
    return dict(schema_version=VERSION,
                status="PARTIAL" if (observations or financial_observations) else "UNAVAILABLE",
                financial_fact_admitted=False, complete_debt_verified=False,
                interest_bearing_debt=None, observations=observations,
                financial_observations=financial_observations,balance_packets=balance_packets,
                source_count=len(manifest["sources"]),
                parsed_source_count=len(balance_packets),
                collection_failures=list((manifest.get("collection") or {}).get("failures") or []),
                manifest_binding=dict(binding), evaluation_at=now.isoformat(),
                errors=errors,
                unknowns=["EXHAUSTIVE_FINANCING_SCOPE_NOT_PROVEN",
                          "COMPLEX_MOVEMENT_TABLES_NOT_SUPPORTED",
                          "BLANK_OR_SINGLE_COLUMN_IS_NOT_ZERO"])
