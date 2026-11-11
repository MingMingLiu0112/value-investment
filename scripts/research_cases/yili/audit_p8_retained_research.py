"""P8 bounded original/replay audit. Writes only its research artifact directory."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal as D, localcontext
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
from value_investment_agent.infrastructure.filings.pdf_text import extract_pages
from value_investment_agent.m1_valuation_package_builder import build_descriptor
from value_investment_agent.research_artifact_codecs import artifact_payload
from value_investment_agent.valuation_models.residual_income import (
    ResidualIncomeEquityValuationModel, scenario_value,
)

OUTPUT = ROOT / "artifacts/current/tl11-p8-20261016/research"
P7 = "artifacts/current/tl11-p7-20261015/"
YILI_PACKAGE = "runtime/daily-trade-assistant/20261011-s5-pending-candidate-v5/pending-candidate/package.json"
MOUTAI_PACKAGE = "runtime/daily-trade-assistant/20261011-s1-pending-candidate-v5/pending-candidate/package.json"
YILI_EXPLANATION = "runtime/daily-trade-assistant/fm3-v3-publish-20261012-v2/600887-value-decision-explanation.json"
MOUTAI_EXPLANATION = "runtime/daily-trade-assistant/fm3-v3-publish-20261012-v2/600519-value-decision-explanation.json"


def read(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def binding(name, expected=None):
    path = (ROOT / name).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError("Audit source must stay inside repository")
    digest = sha(path)
    if expected is not None and digest != expected:
        raise ValueError("Source hash mismatch: " + str(name))
    return dict(path=path.relative_to(ROOT).as_posix(), sha256=digest)


def compact(text):
    return re.sub(r"\s+", "", text)


def require_row(text, label, values):
    """Require consecutive ordered numeric columns after a unique row label."""
    text = compact(text)
    matches = []
    for found in re.finditer(re.escape(compact(label)), text):
        tail = text[found.end():found.end() + 450]
        numbers = re.findall(r"-?\d{1,3}(?:,\d{3})+\.\d{2}", tail)[:len(values)]
        if [value.replace(",", "") for value in numbers] == values:
            matches.append(text[found.start():found.end() + 220])
    if len(matches) != 1:
        raise ValueError("Original row/column mismatch: " + label)
    return matches[0]


def original_pages(source, numbers):
    checked = binding(source["path"], source["sha256"])
    pages = extract_pages(ROOT / source["path"])
    return [dict(source_binding=checked, physical_page=n, text=pages[n - 1]) for n in numbers]


def replay(name, explanation_name):
    package = read(name)
    descriptor = build_descriptor(package, root=ROOT)
    result = ResidualIncomeEquityValuationModel().value(descriptor.facts, descriptor.research_case)
    result_payload = artifact_payload(result)[1]
    expected = read(explanation_name)["valuation"]
    for key in ("symbol", "model_type", "model_version", "valuation_date", "status",
                "bear_value", "base_value", "bull_value"):
        if result_payload[key] != expected[key]:
            raise ValueError("Published valuation replay mismatch: " + key)
    originals = []
    for source in package["sources"]:
        if source["kind"] == "official_issuer_filing":
            name = source.get("local_path") or source["location"]
            originals.append({**binding(name, source["sha256"]), "id": source["id"],
                              "url": source["location"]})
    facts = descriptor.facts
    annuals = {}
    with localcontext() as ctx:
        ctx.prec = 48
        for label, scenario in facts.scenario_inputs.items():
            calculation = scenario_value(facts.operating_inputs["start_book_equity"],
                facts.operating_inputs["ordinary_shares"], scenario.cost_of_equity,
                dict(forecast_roe=scenario.forecast_roes, retention=scenario.retention,
                     terminal_roe=scenario.terminal_roe, terminal_growth=scenario.terminal_growth))
            rows = calculation["forecast_years"]
            annuals[label] = dict(basis_date_calculation=calculation,
                last_vs_first_forecast_profit_change=str(
                    D(rows[-1]["net_income_assumption_cny"]) / D(rows[0]["net_income_assumption_cny"]) - 1),
                first_forecast_dps=str(D(rows[0]["dividend_assumption_cny"]) /
                    facts.operating_inputs["ordinary_shares"]),
                last_forecast_dps=str(D(rows[-1]["dividend_assumption_cny"]) /
                    facts.operating_inputs["ordinary_shares"]))
        book = facts.operating_inputs["start_book_equity"]
        shares = facts.operating_inputs["ordinary_shares"]
        base = annuals["base"]["basis_date_calculation"]
        transport = D(next(s for s in result_payload["sensitivities"]
                           if s["scenario"] == "base")["basis_to_valuation_factor"])
        decomposition = dict(book_equity_per_disclosed_share=str(book / shares),
            transported_book_component_per_share=str(book / shares * transport),
            transported_explicit_residual_component_per_share=str(
                D(base["present_value_explicit_residual_income_cny"]) / shares * transport),
            transported_terminal_residual_component_per_share=str(
                D(base["present_value_terminal_residual_income_cny"]) / shares * transport),
            scope="Existing shared-model components, not current balance-sheet equity or distributable cash.")
    return dict(package=binding(name), explanation=binding(explanation_name),
        scope="EXISTING_TYPED_INPUT_ARITHMETIC_REPLAY_NOT_APPROVAL_OR_FULL_ADMISSION",
        financial_balance_date=package["point_in_time"]["report_period"],
        valuation=result_payload, operating_inputs=package["facts"]["operating_inputs"],
        consumed_scenario_inputs=package["facts"]["scenario_inputs"],
        valuation_timing=package["facts"]["valuation_timing"],
        originals=originals, annual_arithmetic=annuals, base_value_decomposition=decomposition)


def build():
    spec = importlib.util.spec_from_file_location("yili_fact_audit", Path(__file__).with_name("build_yili_current_fact_review.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    financial = module.build()
    yili = replay(YILI_PACKAGE, YILI_EXPLANATION)
    moutai = replay(MOUTAI_PACKAGE, MOUTAI_EXPLANATION)
    fy_source = dict(path=module.FY, sha256=module.SOURCES["fy"][3])
    h1_source = dict(path=module.H1, sha256=module.SOURCES["h1"][3])
    yili_pages = original_pages(fy_source, [7, 49]) + original_pages(h1_source,
        [6, 49, 58, 59, 66, 143, 144, 148, 167, 173, 174])
    for text, tokens in [(compact(yili_pages[0]["text"]),
            ["加权平均净资产收益率（%）20.8715.81", "19.9711.24"]),
            (compact(yili_pages[2]["text"]), ["加权平均净资产收益率（%）10.0912.60", "9.8012.28"])]:
        if any(token not in text for token in tokens):
            raise ValueError("Yili weighted ROE row mismatch")
    index = read(P7 + "public-incremental-evidence-index.json")
    for item in index["items"]:
        binding(item["archive_path"], item["sha256"])
    observation = read(P7 + "public-incremental-evidence/77927d6c76a9ab4f4e4467c8e07eb018840d6b99f9dcdbd703eaa9bd7641edcf.json")
    pdfs = [item for item in index["items"] if item["archive_path"].endswith(".pdf")]
    if observation["announcement_count"] != 2 or len(pdfs) != 2:
        raise ValueError("Expected exactly the two retained incremental originals")
    pages = []
    for item in pdfs:
        p = dict(path=item["archive_path"], sha256=item["sha256"])
        texts = extract_pages(ROOT / p["path"])
        pages.extend(original_pages(p, range(1, len(texts) + 1)))
    by_hash = {}
    for page in pages:
        by_hash.setdefault(page["source_binding"]["sha256"], []).append(page)
    issued = by_hash["bb98b2d13f492eed41c090e96156af41c41bdb1ef2a4d4d5a07ae197d5281d19"]
    guarantee = by_hash["1ba54ca786f66efbaebe67f6e6c17cb50f52284251bd46c3b7ae7f226be6a3e2"]
    tranche_facts = []
    for number, page_no, amount, term, maturity in [
        (15, 1, "105", 79, "2026-12-30"), (16, 2, "85", 79, "2026-12-30"),
        (17, 2, "75", 78, "2026-12-29"), (18, 2, "75", 78, "2026-12-29"),
        (19, 3, "75", 78, "2026-12-29"),
    ]:
        text = compact(issued[page_no - 1]["text"])
        section = text.split(f"SCP{number:03}", 1)[1].split("主承销商", 1)[0]
        for token in [f"实际发行总额{amount}亿元", "1.29%", f"{term}天",
                      "2026年10月12日", maturity.replace("-", "年", 1).replace("-", "月") + "日"]:
            if token not in section:
                raise ValueError("Issuance table mismatch: " + token)
        tranche_facts.append(dict(issue=f"SCP{number:03}", principal_cny=str(D(amount) * 100000000),
            annual_coupon="0.0129", days=term, interest_start="2026-10-12", maturity=maturity,
            physical_page=page_no, source_binding=issued[0]["source_binding"]))
    gtext = compact(guarantee[0]["text"])
    for token in ["321,199.87万元", "45,895.16万元", "275,304.71万元", "205,784.67万元",
                  "53,050.14万元", "152,734.53万元", "1,283户", "45户", "1,238户"]:
        if token not in gtext:
            raise ValueError("Guarantee fact missing: " + token)
    if D("53050.14") + D("152734.53") != D("205784.67"):
        raise ValueError("Guarantee segment reconciliation failed")
    for page, token in [(1, "4,501.17"), (1, "4,168.47"), (1, "3,464.30"),
                        (2, "3,009.16"), (2, "3,000.00")]:
        text = compact(guarantee[page - 1]["text"])
        if token not in text or "良好是" not in text:
            raise ValueError("Guarantee top-five table mismatch")
    events = dict(observation=binding(P7 + "public-incremental-evidence/77927d6c76a9ab4f4e4467c8e07eb018840d6b99f9dcdbd703eaa9bd7641edcf.json"),
        source_urls=[s for s in observation["source_bindings"] if s["id"].startswith("cninfo:")],
        scan_from=observation["scan_from"], scan_to=observation["scan_to"],
        acquired_at=observation["acquired_at"], full_calendar_window_elapsed=False,
        coverage="TWO_ARCHIVED_ANNOUNCEMENTS_NOT_NEW_SCAN_OR_OCT16_FULL_COVERAGE",
        financing=dict(tranches=tranche_facts,
            principal_total_cny=str(sum(D(x["principal_cny"]) for x in tranche_facts)),
            gross_principal_not_net_cash=True,
            preliminary_impact="POTENTIALLY_MATERIAL_FINANCING_AND_MATURITY_REVIEW",
            thesis_effect="Actual short-term funding obtained; concentrated December maturities persist. Not proof of September repayment funding or post-issuance unrestricted cash.",
            unknown=["net proceeds/fees", "use of proceeds", "overlap with existing borrowings", "cash and debt after issuance", "repayment/refinancing capacity in December"]),
        guarantee=dict(balance_as_of="2026-09-30", physical_pages=[1, 2], source_binding=guarantee[0]["source_binding"],
            annual_cumulative_guarantee_cny="3211998700", outstanding_responsibility_cny="2057846700",
            annual_upstream_cny="458951600", annual_downstream_cny="2753047100",
            upstream_outstanding_cny="530501400", downstream_outstanding_cny="1527345300",
            clients_total=1283, upstream_clients=45, downstream_clients=1238,
            preliminary_impact="POTENTIALLY_MATERIAL_CHANNEL_CREDIT_AND_CONTINGENT_LIQUIDITY_REVIEW",
            thesis_effect="Channel/producer financing exposure remains. Cumulative issuance is not outstanding risk; guarantees are not realized losses or automatically additional consolidated debt.",
            top_five=dict(responsibility_wan_cny=["4501.17", "4168.47", "3464.30", "3009.16", "3000.00"],
                counter_guarantee="YES_FOR_LISTED_TOP_FIVE_NOT_ALL_CLIENTS", issuer_credit_description="GOOD_NOT_INDEPENDENT_RATING"),
            unknown=["all-client collateral and recovery", "calls/defaults/provisions", "cash timing", "overlap with prior overdue guarantees and consolidated liabilities"]),
        materiality_approved=False, model_revalidated=False, research_date_advanced=False,
        review_handoff=dict(required_actor="AUTHORIZED_EXTERNAL_RESEARCH_MATERIALITY_REVIEWER",
            bind_to=["exact current candidate/model/assumptions hashes", "full prior plus incremental scan hashes", "both original PDF hashes and extracted physical pages"],
            allowed_outcomes=["VERIFIED", "REJECTED", "INSUFFICIENT"],
            next="Use existing materiality handoff/sign/import/recalculate services; this audit is unsigned evidence only."))
    # Actual secondary financial table checks, not a count of historical drafts.
    moutai_fy, moutai_h1 = moutai["originals"][:2]
    m_pages = original_pages(moutai_fy, [6, 9, 10]) + original_pages(moutai_h1, [5, 7, 28, 36, 37])
    fy6, h15 = m_pages[0]["text"], m_pages[3]["text"]
    m_facts = []
    for text, source, page, label, values, periods in [
        (fy6, moutai_fy, 6, "营业收入", ["168838102514.79", "170899152276.34"], ["FY2025", "FY2024"]),
        (fy6, moutai_fy, 6, "归属于上市公司股东的扣除非经常性损益的净利润", ["82293107655.25", "86240905977.42"], ["FY2025", "FY2024"]),
        (h15, moutai_h1, 5, "营业收入", ["90703260964.48", "89389354416.84"], ["H12026", "H12025"]),
        (h15, moutai_h1, 5, "归属于上市公司股东的扣除非经常性损益的净利润", ["44464207646.01", "45390247623.82"], ["H12026", "H12025"]),
        (h15, moutai_h1, 5, "归属于上市公司股东的净资产", ["251253594419.50", "244637811032.18"], ["2026-06-30", "2025-12-31"]),
        (h15, moutai_h1, 5, "期末总股本", ["1250081601.00", "1252270215.00"], ["2026-06-30", "2025-12-31"]),
    ]:
        m_facts.append(dict(label=label, values=values, periods=periods, physical_page=page,
            source_binding=source, evidence_excerpt=require_row(text, label, values)))
    if D("82293107655.25") + D("44464207646.01") - D("45390247623.82") != D("81367067677.44"):
        raise ValueError("Moutai TTM reconciliation failed")
    selection = []
    for symbol, name, package in [("000651", "Gree", "config/m1-valuation-packages-v1/000651-fcff.json"),
                                   ("600741", "Huayu", "config/m1-valuation-packages-v1/600741-fcff.json")]:
        data = read(package)
        originals = [binding(s["location"], s["sha256"]) for s in data["sources"] if s["kind"] == "official_issuer_filing"]
        selection.append(dict(symbol=symbol, name=name, package=binding(package), verified_originals=originals,
            reason_not_selected="FY/H1 originals exist, but industrial FCFF needs finance/non-operating scope, minority/JV equity and sustainable reinvestment bridges; no comparable admitted forward-input chain shown by this package."))
    midea = "runtime/company-research/midea-valuation-applicability-20261013-v5/evidence.json"
    shenhua = "docs/current/tl8-c-601088-cycle-model-boundary-receipt-20261013.json"
    md = read(midea)
    md_originals = [binding(s["path"], s["sha256"]) for s in md["evidence_refs"] if s.get("path", "").lower().endswith(".pdf")]
    sd = read(shenhua)
    sd_evidence = sd["artifact"]
    binding(sd_evidence["path"], sd_evidence["sha256"])
    sd_data = read(sd_evidence["path"])
    sd_sources = [binding(s["path"], s["sha256"]) for s in sd_data["evidence_refs"]]
    selection.extend([dict(symbol="000333", evidence=binding(midea), verified_originals=md_originals,
        reason_not_selected="Current denominator reconciled, RI profile route supported, but six scenario-range inputs unregistered; industrial FCFF not applicable to disclosed scope."),
        dict(symbol="601088", evidence=binding(shenhua), checked_source_bindings=sd_sources,
        reason_not_selected="Cyclical route supported, zero of 13 required cyclical inputs admitted; current-perimeter parent earnings bridge remains incomplete."),
        dict(symbol="600519", evidence=binding(MOUTAI_PACKAGE), verified_originals=moutai["originals"], selected=True,
        reason="Direct FY/H1 original rows, attributable equity/shares, core product/channel and legal-parent cash evidence plus executable existing typed scenarios; selected by traceability, not draft count or favorable valuation.")])
    return dict(schema_version="p8-retained-real-company-research-audit-v1", action="no_order",
        audited_at=datetime.now(timezone.utc).isoformat(),
        scope="B1_B2_B3_B6_PUBLIC_RESEARCH_ONLY_NO_APPROVAL_NO_NEW_MARKET_COLLECTION",
        code_bindings=[binding(Path(__file__)), binding("src/value_investment_agent/valuation_models/residual_income.py"),
            binding("scripts/research_cases/yili/build_yili_current_fact_review.py")],
        yili_financial_audit=financial, yili_existing_replay=yili, yili_incremental_events=events,
        second_company_selection=selection, second_company_existing_replay=moutai,
        second_company_direct_financial_rows=m_facts,
        second_company_ttm_ex_parent_profit_cny="81367067677.44",
        extracted_original_pages=pages + yili_pages + m_pages,
        research_judgments_binding=binding(OUTPUT / "judgments.json"),
        research_judgments=read(OUTPUT / "judgments.json"),
        retained_price_policy_packet=binding(P7 + "published-packet.json"),
        conclusions=dict(yili="CURRENT_RELIABLE_FAIR_VALUE_NOT_ESTABLISHED", moutai="CONDITIONAL_RESEARCH_ONLY_NOT_RELIABLE_CURRENT_FAIR_VALUE",
            normalized_parent_profit_cny={"600887": None, "600519": None},
            sustainable_dividend_capacity_cny={"600887": None, "600519": None},
            roic_and_incremental_return={"600887": None, "600519": None},
            price_admitted=False, materiality_approved=False, g3_approved=False,
            personal_quantity=None, canonical_written=False))


def self_test():
    require_row("Revenue 1,234.00 2,345.00", "Revenue", ["1234.00", "2345.00"])
    for bad in (["2345.00", "1234.00"], ["1234.00", "0"]):
        try:
            require_row("Revenue 1,234.00 2,345.00", "Revenue", bad)
        except ValueError:
            pass
        else:
            raise AssertionError("Wrong columns accepted")
    try:
        binding(YILI_PACKAGE, "0" * 64)
    except ValueError:
        pass
    else:
        raise AssertionError("Wrong hash accepted")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--render", action="store_true", help="Render the audited source pages as a contact sheet.")
    args = parser.parse_args()
    self_test()
    audit = build()
    if not args.check_only:
        OUTPUT.mkdir(parents=True, exist_ok=True)
        target = OUTPUT / "audit.json"
        if target.exists():
            raise ValueError("Refusing to overwrite retained P8 audit")
        target.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.render:
        if args.check_only:
            raise ValueError("Rendering is not read-only")
        import pypdfium2 as pdfium
        from PIL import Image, ImageDraw

        chosen = audit["extracted_original_pages"][:5]
        chosen += [audit["extracted_original_pages"][7], audit["extracted_original_pages"][-5]]
        sheet = Image.new("RGB", (1400, 4 * 1030), "#dddddd")
        draw = ImageDraw.Draw(sheet)
        for index, item in enumerate(chosen):
            with pdfium.PdfDocument(ROOT / item["source_binding"]["path"]) as doc:
                page = doc[item["physical_page"] - 1]
                bitmap = page.render(scale=1.3)
                image = bitmap.to_pil().convert("RGB")
                image.thumbnail((690, 990))
                x, y = (index % 2) * 700, (index // 2) * 1030
                sheet.paste(image, (x, y + 30))
                draw.text((x + 4, y + 4), f"{item['source_binding']['sha256'][:12]} physical page {item['physical_page']}", fill="black")
                bitmap.close()
                page.close()
        sheet.save(OUTPUT / "source-page-contact-sheet.png")
    print(json.dumps(dict(status="VERIFIED_EXISTING_ORIGINALS_AND_ARITHMETIC_NOT_APPROVED",
        yili_rows=len(audit["yili_financial_audit"]["facts"]),
        yili_calculations=len(audit["yili_financial_audit"]["calculations"]),
        incremental_announcements=2, second_company="600519",
        second_company_direct_rows=len(audit["second_company_direct_financial_rows"]),
        self_tests="ORDERED_COLUMNS_AND_HASH_NEGATIVES_PASS", action="no_order"), ensure_ascii=False))


if __name__ == "__main__":
    main()
