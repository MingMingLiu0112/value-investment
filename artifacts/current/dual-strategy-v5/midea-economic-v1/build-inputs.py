"""One-off unregistered Midea research inputs; existing models and verifiers only."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import sys
import traceback
from zoneinfo import ZoneInfo

ROOT = next(parent for parent in Path(__file__).resolve().parents
    if (parent / "src/value_investment_agent").is_dir())
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.application.product.common import (
    load_json_object, require_inside, sha256_file, write_new_bytes, write_new_json,
)
from value_investment_agent.application.product.source_bound_inputs import (
    source_catalog_sha256, verify_package_local_sources,
)
from value_investment_agent.application.product.research_case import build_research_case_for_symbol
from value_investment_agent.application.product.research_draft import _validate_draft, _verify_bound_draft
from value_investment_agent.application.product.workbench import build_current_workbench_for_symbol
from value_investment_agent.application.product.research_review_packet import (
    build_research_review_packet, project_research_review_packet,
)
from value_investment_agent.application.product.research_reviews import (
    build_research_review_model_context, prepare_pending_review_intake,
)
from value_investment_agent.application.product.pending_research_candidate import verify_pending_research_candidate
from value_investment_agent.application.product.bound_draft_review import verify_bound_draft_review_candidate
from value_investment_agent.application.product.decision_surface import verify_current_decision_workbench
from value_investment_agent.application.product.research_review_wizard import preview_pending_review_response
from value_investment_agent.m1_valuation_package_builder import build_descriptor, build_research_case
from value_investment_agent.research_input import build_research_run_spec
from value_investment_agent.research_artifact_codecs import artifact_payload
from value_investment_agent.valuation_models.residual_income import ResidualIncomeEquityValuationModel
from value_investment_agent.domain.research.evidence_stop import (
    evaluate_research_schedule, evidence_stops_from_payload, schedule_request_from_payload,
)
from value_investment_agent.infrastructure.evidence.evidence_stop_schedule import resolved_evidence_stop_ids

OUT = ROOT / "artifacts/current/dual-strategy-v5/midea-economic-v1"
OLD = ROOT / "artifacts/current/web-first-acceptance/s2/midea-consumed-v3-dated/package.json"
OLD_DRAFT = OLD.parent / "public-draft-v4.json"
EVIDENCE = {
    "accounting": ("artifacts/current/dual-strategy-v5/midea-earnings-interpretation-correction.json",
        "f074c7f7ecd9d7072dc5061c792284985a3abbe713de2a0d505bfac91f4a7462"),
    "stress": ("artifacts/current/dual-strategy-v5/midea-existing-model-sensitivity.json",
        "dfdbf4047fc86d0c2248cddd0394ede91f529af25f51baec59d4a8b66a78cef8"),
    "business": ("runtime/company-research/midea-business-evidence-20260921/evidence.json",
        "de60b009c83770834c033b06b71a093bacfd739be6b2bf4fa4cb1a029b6f4cc8"),
    "distribution": ("runtime/company-research/midea-2014-2024-equity-return-candidate-20260922/evidence.json",
        "6726e821972d0490753a6cc718f6f54515ccbfbb53341f081900af208eab7ea1"),
}
WATCH_CONFIGS = [
    "config/current-research-drafts.json", "config/user-research-workflow-v1.json",
    "config/current-company-research-registry.json", "config/research-evidence-stop-ledger-v1.json",
    "config/current-pending-candidate-replays-v1.json", "config/current-daily-public-snapshot.json",
]
IMPLEMENTATIONS = [
    "src/value_investment_agent/application/product/source_bound_inputs.py",
    "src/value_investment_agent/application/product/research_case.py",
    "src/value_investment_agent/application/product/research_draft.py",
    "src/value_investment_agent/application/product/bound_draft_review.py",
    "src/value_investment_agent/application/product/pending_research_candidate.py",
    "src/value_investment_agent/application/product/research_review_packet.py",
    "src/value_investment_agent/application/product/research_reviews.py",
    "src/value_investment_agent/application/product/workbench.py",
    "src/value_investment_agent/application/product/company_research.py",
    "src/value_investment_agent/m1_valuation_package_builder.py",
    "src/value_investment_agent/research_input.py",
    "src/value_investment_agent/research_application.py",
    "src/value_investment_agent/valuation_models/residual_income.py",
    "src/value_investment_agent/domain/research/research_run_contract.py",
    "artifacts/current/dual-strategy-v5/midea-economic-v1/build-inputs.py",
]


def binding(path: Path) -> dict:
    path = require_inside(ROOT, path, "research binding")
    return dict(path=path.relative_to(ROOT).as_posix(), sha256=sha256_file(path))


def check_source(path: Path, expected: str) -> None:
    if sha256_file(require_inside(ROOT, path, "retained source")) != expected:
        raise ValueError("retained source hash mismatch: " + str(path))


def build() -> dict:
    # Both directories are exclusively new. No existing output or pointer is replaced.
    resume = sys.argv[1:] == ["--resume-after-case-export-error"]
    if sys.argv[1:] and not resume:
        raise ValueError("unsupported argument")
    if resume:
        previous_error = load_json_object(OUT / "build-error.json", "retained initial error")
        if (previous_error["error"] != "expected exactly one research case for symbol 000333, found 2"
                or (OUT / "verification.json").exists()):
            raise ValueError("resume is limited to this script's recorded case-export error")
        runtime = require_inside(ROOT / "runtime", ROOT / previous_error["runtime_directory"], "resume runtime")
    else:
        OUT.mkdir(parents=True, exist_ok=False)
        started = datetime.now(timezone.utc)
        runtime = ROOT / "runtime" / ("midea-economic-v1-" + started.strftime("%Y%m%dT%H%M%S%fZ"))
        runtime.mkdir(parents=True, exist_ok=False)
        write_new_json(OUT / "build-start.json", dict(action="no_order", generated_at=started.isoformat(),
            runtime_directory=runtime.relative_to(ROOT).as_posix(), registration_requested=False))
    try:
        return build_inputs(runtime, resume=resume)
    except Exception as error:
        error_name = ("build-error-resume-" + datetime.now(timezone.utc).strftime("%H%M%S%f") + ".json"
            if resume else "build-error.json")
        write_new_json(OUT / error_name, dict(action="no_order", status="BLOCKED",
            generated_at=datetime.now(timezone.utc).isoformat(), exception_type=type(error).__name__,
            error=str(error), traceback=traceback.format_exc(), historical_timestamps_modified=False,
            registration_changed=False, runtime_directory=runtime.relative_to(ROOT).as_posix()))
        raise


def build_inputs(runtime: Path, *, resume: bool = False) -> dict:
    script_copy = OUT / "build-inputs.py"
    if not script_copy.exists():
        write_new_bytes(script_copy, Path(__file__).read_bytes())
    elif script_copy.read_bytes() != Path(__file__).read_bytes():
        raise ValueError("published builder differs from executing builder")
    old = load_json_object(OLD, "retained package")
    check_source(OLD, "61525b2918dc33f9f3cc761649b89dc1ba9c13443e4dcfb80381b8be9702facf")
    check_source(OLD_DRAFT, "c2c7de481405146ee3fc27d364e698baf7435768fe020f30e2a9b4de68c93f23")
    before = {p: sha256_file(ROOT / p) for p in WATCH_CONFIGS + IMPLEMENTATIONS if (ROOT / p).is_file()}
    before.update({OLD.relative_to(ROOT).as_posix(): sha256_file(OLD),
        OLD_DRAFT.relative_to(ROOT).as_posix(): sha256_file(OLD_DRAFT)})
    for path, digest in verify_package_local_sources(ROOT, old):
        before[path.relative_to(ROOT).as_posix()] = digest
    materials = {}
    for key, (name, digest) in EVIDENCE.items():
        check_source(ROOT / name, digest)
        materials[key] = load_json_object(ROOT / name, key)
        before[name] = digest
    for name, row in materials["stress"]["bindings"].items():
        check_source(ROOT / name, row["sha256"])
        before[name] = row["sha256"]
    historical = materials["distribution"]
    for ref in historical["evidence_refs"]:
        check_source(ROOT / ref["path"], ref["sha256"])
        before[Path(ref["path"]).as_posix()] = ref["sha256"]
    for ref in materials["business"]["evidence_refs"]:
        check_source(ROOT / ref["path"], ref["sha256"])
    now = datetime.now(timezone.utc)
    if resume:
        # Continue the already-created input version; retain its real original timestamp.
        existing_package = load_json_object(OUT / "package.json", "own partially built package")
        now = datetime.fromisoformat(existing_package["point_in_time"]["computed_at"])
    stamp = now.isoformat()
    day = now.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()
    if datetime.fromisoformat(materials["stress"]["generated_at"]) > now:
        raise ValueError("sensitivity attachment is not yet available; do not backdate")
    version = "midea-economic-v1-" + now.strftime("%Y%m%dT%H%M%S%fZ")
    groups = [
        dict(id="ACCOUNTING_COMPARABILITY", question="同比ROE及汇兑/衍生品分类是否解释准确？",
            support="H1加权ROE11.33%对11.29%，同比+0.04个百分点；归母利润、扣非及非经常损益桥已勾稽。",
            countercase="混合工具收益并非全部套保，工具范围差、OCI包含关系及项目税后归母未知。",
            impact="纠正旧半年/全年误比，不将扣非降幅认定为主业等幅下降，不机械加回。",
            field_paths=["research_case.financial_summary", "research_case.counter_evidence"]),
        dict(id="ROE_PATH", question="五期15/18/20.5%起点及衰减路径是否有经济支持？",
            support="FY2025加权ROE19.70%为历史参照；家用与商用工业收入增长、研发投入支持研究持续经营能力。",
            countercase="半年加权ROE不能乘二，也不等于模型期初权益ROE；毛利率下行与洗衣机销量下降反对机械外推。",
            impact="保留全部旧数值但仅作低置信待审条件；未来同口径收益/现金转换不支持时重开，不按估值结果选路径。",
            field_paths=["facts.scenario_inputs", "assumptions", "research_case.financial_summary"]),
        dict(id="EQUITY_COST", question="9%权益成本及实验proxy如何分别解释？",
            support="9%是原候选门槛；12格记录2026-09-08无风险proxy1.6813%与2026-01-05中国ERP5.14%，beta=1是假设。",
            countercase="6.8213%不是下界、不是美的当前实测权益成本，也未证明9%适当。",
            impact="不改9%输入，不借用其他公司beta；公司专属风险与币种/日期适用性仍需独立经济判断。",
            field_paths=["facts.scenario_inputs", "assumptions", "research_case.financial_summary"]),
        dict(id="DISTRIBUTION", question="留存40/35/30%是否可作为研究条件？",
            support="2022/2023/2024拟现金分红/归母利润约58.16/61.57/69.31%，可与模型60/65/70%派付条件对照。",
            countercase="拟分红不等于实付或未来现金能力；回购用途、母公司可分配利润、集团融资和OCI/资本变化不能忽略。",
            impact="只支持区间讨论，不证明可持续派息；不能把全部回购直接算作分红或认定留存=1-全部现金回报。",
            field_paths=["facts.scenario_inputs", "source_contract.distribution_input_status", "research_case.financial_summary"]),
        dict(id="TERMINAL_AND_CAPITAL", question="终端ROE9.5/11/13%、g1.5/2/2.5%与资本桥是否成立？",
            support="共享剩余收益模型和压力附件揭示尾部敏感性；资本212861055000元及扣库存普通股7464347335沿用原锚点。",
            countercase="收入增长不证明永久超额回报；终端ROE/成本压力仅数学对照，干净盈余/未来OCI/资本变动及再投资约束未获经济验证。",
            impact="不改终端参数，不将代数股利一致性当现金能力；终值依赖高或资本变动时须重审。",
            field_paths=["facts.operating_inputs", "facts.valuation_timing", "facts.scenario_inputs", "assumptions"]),
        dict(id="EVENTS_AND_AUTHORITY", question="研究更新是否足以解除公告、有效性及G3阻断？",
            support="只复用已保留官方原件与旧INCOMPLETE扫描，新研究说明按实际现在可得。",
            countercase="旧窗口不完整，四公告待材料性审查；旧G3、后来观察或补证文件均不能自动建立新上下文批准。",
            impact="继续UNKNOWN、G1/G3未通过、无价格准入；等待Root和独立审核，不申请或创建签署。",
            field_paths=["model_validity_input", "research_case.blockers", "source_contract"]),
    ]
    notes = {
        "cost_of_equity": ("9% retained candidate hurdle; dated proxy is only a stress comparator.", groups[2]),
        "retention": ("Retained 40/35/30%; historical proposed dividends only bound discussion, not capacity.", groups[3]),
        "terminal_roe": ("Retained 9.5/11/13%; excess-return persistence remains an unverified hypothesis.", groups[4]),
        "terminal_growth": ("Retained 1.5/2/2.5%; g below cost is mathematical admissibility, not economic proof.", groups[4]),
    }
    proposal = dict(action="no_order", symbol="000333", generated_at=stamp,
        scope="SOURCE_BOUND_ECONOMIC_RESEARCH_WITH_UNCHANGED_MODEL_PARAMETERS_NOT_APPROVAL",
        source_package=binding(OLD), original_point_in_time=old["point_in_time"],
        research_as_of=day, valuation_basis_retained=old["facts"]["valuation_timing"],
        human_review_groups=groups, economics_validated=False, g3_approved=False,
        scenario_inputs_unchanged=True, best_cell_selected=False, normalized_parent_profit_cny=None,
        rationale_bindings=[dict(role=k, path=v[0], sha256=v[1]) for k, v in EVIDENCE.items()],
        source_classification={"accounting": "EX_POST_OFFICIAL_FACT_INTERPRETATION_NOT_NORMALIZED_PROFIT",
            "business": "OFFICIAL_REPORTED_OPERATING_FACTS_NOT_MOAT_PROOF",
            "distribution": "HISTORICAL_PROPOSED_CASH_RETURN_CANDIDATE_NOT_PAID_OR_SUSTAINABLE",
            "stress": "RESEARCH_EXPERIMENT_NOT_REGISTERED_VALUATION_RESULT"},
        reported_business_facts=materials["business"]["facts"],
        historical_proposed_payout_ratios={str(row["year"]): row["derived_candidates"]["cash_dividend_to_parent_net_profit"]
            for row in historical["series"][-3:]},
        cost_proxy=materials["stress"]["cost_proxy"],
        assumption_review=[dict(name=row["name"], values={s: row[s] for s in ("bear", "base", "bull")},
            interpretation=(notes[row["name"]][0] if row["name"] in notes else
                "Retained model-year path; historical field names are not calendar-year forecasts."),
            support=(notes[row["name"]][1] if row["name"] in notes else groups[1])["support"],
            countercase=(notes[row["name"]][1] if row["name"] in notes else groups[1])["countercase"],
            invalidation=(notes[row["name"]][1] if row["name"] in notes else groups[1])["impact"],
            confidence="low", parameter_validated=False) for row in old["assumptions"]["assumptions"]],
        unknowns=materials["accounting"]["unresolved"] + [
            "逐主体税费及工具税后归母未知保留，不要求未公开内部拆分才能提出有界假设。",
            "经营增长/毛利率/销量不证明持续ROE；披露加权ROE和模型期初权益收益率定义不同。",
            "分配、未来OCI及资本变动未建立；代数股利核对不证明上市母公司现金能力。",
            "旧公告窗口未补齐；新研究时点不代表事实、报价或事件数据更新至现在。"],
        stop_collecting_when="无法改变盈利解释、假设边界、置信度或反证时停止采集；不强求未公开税额/内部归属。",
        reopen_triggers=["新同口径定期披露改变利润/毛利率/现金转换或资本回报判断。",
            "已披露资本、库存股、回购注销、分配或重大公告改变输入。",
            "可核验新工具范围、税后归属或OCI桥足以改变正常化解释。",
            "独立审核否定持续期、权益成本、分配或终端经济依据。"],
        event_coverage="INCOMPLETE", price_admitted=False, research_admitted=False,
        date_semantics="Actual current research on retained historical capital/valuation basis; not historical contemporaneous PIT or current fair value.")
    proposal_path = OUT / "economic-research.json"
    if not resume:
        write_new_json(proposal_path, proposal)
    elif load_json_object(proposal_path, "own proposal") != proposal:
        raise ValueError("resume proposal differs from retained original bytes")
    report = ["# 美的经济研究新版本 v1：未批准、未注册", "",
        "本次纠正研究解释并约束假设论据，全部原情景参数保持不变。12格仅是压力附件，不选最优格。",
        "研究时点：" + stamp + "；保留旧资本及估值基准；不代表当前正式估值。", ""]
    for group in groups:
        report.extend(["## " + group["id"], "", group["question"], "",
            "依据：" + group["support"], "", "反例／未知：" + group["countercase"], "",
            "失效及处理：" + group["impact"], ""])
    report.extend(["## 停止采集与重开", "", proposal["stop_collecting_when"], "",
        *["- " + x for x in proposal["reopen_triggers"]], "", "## 保留未知", "",
        *["- " + x for x in proposal["unknowns"]], "", "## 精确材料", "",
        *["- " + v[0] + " SHA256=" + v[1] for v in EVIDENCE.values()], "",
        "action=no_order；没有经济参数验证、G3批准、签署、注册或公开估值更新。", ""])
    if not resume:
        write_new_bytes(OUT / "economic-research.md", "\n".join(report).encode("utf-8"))
    package = deepcopy(old)
    package.update(package_version=version, descriptor_version=version, run_id=version,
        supersedes=dict(**binding(OLD), reason="new unapproved economic interpretation; all numeric scenario inputs retained"))
    package["point_in_time"].update(research_as_of=day, available_at=stamp, computed_at=stamp)
    package["source_contract"]["cutoff_at"] = stamp
    refs = []
    for key, (name, digest) in EVIDENCE.items():
        refs.append(dict(id="midea-economic-v1-" + key, path=name, sha256=digest))
    refs.append(dict(id="midea-economic-v1-proposal", **binding(proposal_path)))
    for ref in refs:
        package["sources"].append(dict(id=ref["id"], kind="research_artifact", location=ref["path"],
            local_path=ref["path"], sha256=ref["sha256"], retrieved_at=stamp,
            source_available_at=stamp, availability_basis="ACTUAL_CURRENT_READ_NOT_HISTORICAL_AVAILABILITY",
            parser_version="midea-economic-v1-case-input"))
    # Bind historical original PDFs directly as well as the derived distribution receipt.
    for index, ref in enumerate(historical["evidence_refs"]):
        package["sources"].append(dict(id="midea-economic-history-" + str(index), kind="official_issuer_filing",
            location=ref["url"], local_path=Path(ref["path"]).as_posix(), sha256=ref["sha256"],
            retrieved_at=stamp, source_available_at=stamp,
            availability_basis="ACTUAL_CURRENT_READ_OF_RETAINED_ORIGINAL_NOT_HISTORICAL_PIT",
            parser_version="retained-historical-original-no-new-extraction"))
    case = package["research_case"]
    case.update(as_of=day, run_id=version, generated_at=stamp, research_version=version,
        thesis="同期H1加权ROE11.33%对11.29%，不能由半年/全年误比认定恶化。扣非下降涉及汇兑与风险管理工具分类不对称，不能等同主业等幅下降。规模、渠道、全球化及ToB增长支持研究资本回报持续性，毛利率与销量反证限制外推。全部旧ROE及终端参数仅保留为低置信待审条件。",
        mispricing_hypothesis="本版本只收口经济研究依据与反证；不比较现价，不证明低估，不选择压力实验最优格。")
    case["evidence_refs"].extend(refs)
    case["financial_summary"].update(h1_2025_weighted_roe="0.1129", h1_weighted_roe_yoy_change_pp="0.04",
        normalized_parent_profit_cny=None, economic_research_proposal_binding=binding(proposal_path),
        pressure_experiment_binding=dict(path=EVIDENCE["stress"][0], sha256=EVIDENCE["stress"][1]),
        reported_business_facts=materials["business"]["facts"],
        historical_proposed_cash_payout_ratios=proposal["historical_proposed_payout_ratios"],
        economic_parameters_validated=False,
        interpretation_scope="Reported/comparative facts and bounded hypotheses; not normalized earnings, paid dividends or verified forward inputs.")
    package["source_contract"]["fact_anchors"].append(dict(field="h1_2025_weighted_roe", source_id="midea_2026h1",
        physical_page=7, source_value="0.1129", unit="ratio", scope="weighted_average_parent_roe", period_end="2025-06-30"))
    case["counter_evidence"] = [
        dict(kind="fact", text="H1扣非归母利润195.95179亿元，同比-25.31%；该降幅是披露事实，不等于已识别的主业盈利降幅。", evidence_refs=[refs[0]["id"], "midea_2026h1"]),
        dict(kind="fact", text="H1加权ROE11.33%，上年同期11.29%，同比+0.04个百分点；不与FY2025的19.70%直接比较或乘二年化。", evidence_refs=[refs[0]["id"], "midea_2026h1"]),
        dict(kind="fact", text="FY2025家用/商用工业毛利率分别变动-0.08/-0.58个百分点，洗衣机销量-6.17%；收入增长并未消除竞争及产品结构压力。", evidence_refs=[refs[2]["id"], "midea_fy2025_annual"]),
        dict(kind="gap", text="衍生工具范围桥、OCI包含关系及项目税后归母未知，不能混合收益全额加回或构造正常化利润。", evidence_refs=[refs[0]["id"]]),
        *deepcopy(old["research_case"]["counter_evidence"][-1:]),
    ]
    case["positives"].extend([
        dict(kind="fact", text="FY2025家用收入2999.27239亿元、+11.28%；商用工业1227.52958亿元、+17.47%；研发177.87624亿元、+9.58%。", evidence_refs=[refs[2]["id"], "midea_fy2025_annual"]),
        dict(kind="interpretation", text="历史拟派现金分红比率约58%至69%，可支持讨论60%至70%派付条件，但不证明实际支付或未来可分配现金。", evidence_refs=[refs[3]["id"]]),
    ])
    case["thesis_breakers"].extend(dict(kind="hypothesis", text=x, evidence_refs=[refs[-1]["id"]]) for x in proposal["reopen_triggers"])
    case["blockers"].append("ECONOMIC_PARAMETERS_NOT_VALIDATED")
    for row in package["assumptions"]["assumptions"]:
        review = next(x for x in proposal["assumption_review"] if x["name"] == row["name"])
        row.update(basis=review["interpretation"], rationale="依据：" + review["support"] + " 反例：" + review["countercase"] + " 失效/处理：" + review["invalidation"])
        row["evidence_refs"].extend(refs)
    package["assumptions"]["evidence_refs"].extend(refs)
    for row in package["assumption_bindings"]:
        row["evidence_refs"].extend(refs)
    package["source_contract"]["scenario_memo"] = dict(id=refs[-1]["id"], sha256=refs[-1]["sha256"])
    package["source_contract"]["source_catalog_sha256"] = source_catalog_sha256(package["sources"])
    if package["facts"] != old["facts"]:
        raise AssertionError("original facts changed")
    for a, b in zip(package["sources"], old["sources"]):
        if a != b:
            raise AssertionError("historical source metadata changed")
    package_path = OUT / "package.json"
    if not resume:
        write_new_json(package_path, package)
    elif load_json_object(package_path, "own package") != package:
        raise ValueError("resume package differs from retained original bytes")
    verified_sources = verify_package_local_sources(ROOT, package)
    case_object = build_research_case(case)
    descriptor = build_descriptor(package, root=ROOT)
    case_source_path = OUT / "research-case-source.json"
    write_new_json(case_source_path, dict(research_case=case))
    case_build = build_research_case_for_symbol(root=ROOT, symbol="000333", source_path=case_source_path,
        output_path=OUT / "research-case.json")
    if json.loads(case_object.to_json()) != case_build["case"]:
        raise AssertionError("ResearchCase creation interfaces disagree")
    old_descriptor = build_descriptor(old, root=ROOT)
    model = ResidualIncomeEquityValuationModel()
    original_value = model.value(old_descriptor.facts, old_descriptor.research_case)
    value = model.value(descriptor.facts, descriptor.research_case)
    for field in ("bear_value", "base_value", "bull_value", "valuation_date", "model_type", "model_version"):
        if getattr(original_value, field) != getattr(value, field):
            raise AssertionError("unchanged model inputs produced a changed value: " + field)
    write_new_json(OUT / "shared-model-check.json", dict(action="no_order", original=binding(OLD),
        original_value=json.loads(original_value.to_json()), research_candidate_value=json.loads(value.to_json()),
        interpretation="Unregistered conditional research calculation; unchanged values, no current public valuation update."))
    request = dict(schema_version="research-schedule-request-v1", symbol="000333", source_id="LOCAL_VERIFIED_RESEARCH",
        period=old["point_in_time"]["report_period"], research_question_id="midea_economic_assumption_evidence_closure",
        blocker_id="economic_rationale_not_bound_to_research_case", reopen_condition_met=False, new_evidence_ids=[])
    ledger = load_json_object(ROOT / "config/research-evidence-stop-ledger-v1.json", "stop ledger")
    schedule = evaluate_research_schedule(symbol="000333", stops=evidence_stops_from_payload(ledger),
        request=schedule_request_from_payload(request), resolved_stop_ids=resolved_evidence_stop_ids(ROOT))
    if not schedule["allowed"] or schedule["status"] != "ALLOW_NORMAL_RESEARCH":
        raise ValueError("economic-only scope is not a non-consuming normal research run: " + str(schedule))
    runtime_package = runtime / "package.json"
    write_new_bytes(runtime_package, package_path.read_bytes())
    request_path = runtime / "schedule-request.json"
    write_new_json(request_path, request)
    work_path = runtime / "workbench.json"
    work = build_current_workbench_for_symbol(root=ROOT, symbol="000333", package_path=runtime_package,
        output_path=work_path, schedule_request=request, schedule_request_sha256=sha256_file(request_path))["result"]
    if not work.get("decision_recommendation") or work["input_descriptor_sha256"] != descriptor.input_sha256:
        raise ValueError("new research was not actually consumed: " + str(work.get("schedule_gate")))
    objects = verify_current_decision_workbench(work).dependency_objects
    if work["suggested_state"] != "NO_ACTION":
        raise AssertionError("research-only candidate emitted an unexpected decision state")
    packet_path = runtime / "consumed-review.json"
    packet = build_research_review_packet(root=ROOT, package_path=runtime_package,
        package_sha256=sha256_file(runtime_package), workbench_path=work_path, workbench_sha256=sha256_file(work_path),
        output_path=packet_path)
    draft = load_json_object(OLD_DRAFT, "old draft")
    draft.update(run_id=version, research_version=version, research_as_of=day, available_at=stamp,
        summary="同期ROE与汇兑/工具分类解释已修正；旧情景数值保留为未验证条件。经营和分配证据及12格压力仅供独立经济审核。",
        thesis=case["thesis"], mispricing_hypothesis=case["mispricing_hypothesis"], financial_facts=case["financial_summary"],
        counter_evidence=[x["text"] for x in case["counter_evidence"]],
        thesis_breakers=[x["text"] for x in case["thesis_breakers"]], reopen_triggers=proposal["reopen_triggers"],
        model_input_binding=dict(package=binding(package_path), input_sha256=descriptor.input_sha256),
        gates=artifact_payload(objects["research_gate"])[1])
    draft["valuation"]["assumptions"] = [{key: row.as_policy()[key] for key in
        ("name", "unit", "bear", "base", "bull", "basis", "rationale", "confidence")}
        for row in descriptor.assumptions.assumptions]
    draft["limitations"] = [x for x in draft["limitations"] if "2026-10-18重算" not in x] + [
        "新研究可得时间为" + stamp + "，新旧材料不倒填旧cutoff；旧官方事实日期、资本及估值基准不变。",
        "12格压力是未登记研究实验；没有选择最优格，不能据此更新正式估值或建议。",
        "新研究解释不证明旧情景参数正确；当前公共估值及注册指针均未变。",
        "旧扫描INCOMPLETE且四公告待审；没有更新到新研究日期的事件完整窗口。"]
    draft["evidence"].extend(dict(id=ref["id"], title=ref["id"], url=ref["path"],
        available_at=stamp, sha256=ref["sha256"]) for ref in refs)
    draft["version_comparison"] = dict(
        **{"from": binding(OLD_DRAFT), "to": dict(research_version=version, status="RESEARCH_DRAFT_NOT_APPROVED")},
        changed=["实际消费ResearchCase修正同期ROE及会计解释", "绑定经营、分配、会计补证及压力附件", "按实际现在研究时间生成独立待审版本"],
        unchanged=["全部FinancialFacts、情景数值及资本/估值基准", "事件/G1/G3/价格阻断", "当前配置指针及公开估值"])
    _validate_draft(draft, "000333", datetime.now(timezone.utc))
    draft_verification = _verify_bound_draft(ROOT, draft, datetime.now(timezone.utc))
    draft_path = OUT / "public-draft.json"
    write_new_json(draft_path, draft)
    scope_path = runtime / "review-scope.json"
    write_new_json(scope_path, dict(action="no_order", scope="SOURCE_BOUND_ECONOMIC_RATIONALE_REVIEW_UNAPPROVED",
        human_review_groups=groups, economic_research_binding=binding(proposal_path)))
    context = build_research_review_model_context(descriptor=descriptor, spec=build_research_run_spec(descriptor))
    inputs = dict(draft=binding(draft_path), package=binding(package_path), input_sha256=descriptor.input_sha256)
    sources = [OLD, OLD_DRAFT, package_path, draft_path, proposal_path, runtime_package,
        work_path, packet_path, request_path, scope_path, *[p for p, _ in verified_sources]]
    candidate = dict(schema_version="pending-research-candidate-v1", symbol="000333", status="PENDING_REVIEW",
        action="no_order", generated_at=datetime.now(timezone.utc).isoformat(),
        candidate_research_as_of=day, financial_period=package["point_in_time"]["report_period"],
        model_context=context, model_context_scope="ACTUALLY_CONSUMED", candidate_valuation=work["valuation"],
        execution_status=work["suggested_state"], research_blockers=work.get("research_blockers", []),
        schedule_gate=work["schedule_gate"], economic_policy_binding=binding(scope_path), review_groups=groups,
        bound_draft_inputs=inputs, preparation_mode="UNREGISTERED_SOURCE_BOUND_ECONOMIC_RESEARCH_REVIEW",
        approval_changed=False, research_admitted=False, price_admitted=False, canonical_written=False,
        registered_current_case_changed=False, position_guidance=None, strict_contemporaneous_pit="NOT_PROVEN",
        source_bindings=list({str(p.resolve()): binding(p) for p in sources}.values()),
        implementation_bindings=[binding(ROOT / p) for p in IMPLEMENTATIONS])
    candidate_path = runtime / "candidate.json"
    write_new_json(candidate_path, candidate)
    candidate_binding = binding(candidate_path)
    verify_pending_research_candidate(root=ROOT, path=candidate_path, expected_sha256=candidate_binding["sha256"])
    intake = prepare_pending_review_intake(root=ROOT, candidate_path=candidate_path,
        candidate_sha256=candidate_binding["sha256"])
    write_new_json(runtime / "review-intake.json", intake)
    preview = preview_pending_review_response(root=ROOT, candidate_path=candidate_path,
        candidate_sha256=candidate_binding["sha256"])
    write_new_json(runtime / "review-preview.json", preview)
    if project_research_review_packet(root=ROOT, package_path=runtime_package,
            package_sha256=sha256_file(runtime_package), workbench_path=work_path,
            workbench_sha256=sha256_file(work_path)) != packet:
        raise AssertionError("consumed review reprojection differs")
    expected_rejection = None
    try:
        verify_bound_draft_review_candidate(root=ROOT, symbol="000333", binding=candidate_binding)
    except ValueError as error:
        expected_rejection = str(error)
    if expected_rejection is None:
        raise AssertionError("unregistered candidate unexpectedly matched the current draft")
    for name, digest in before.items():
        check_source(ROOT / name, digest)
    if package["facts"] != old["facts"] or draft["gates"]["results"]["G3_估值门"] is not False:
        raise AssertionError("frozen facts or G3 boundary changed")
    for name, digest in EVIDENCE.values():
        if not any(x["path"] == name and x["sha256"] == digest for x in packet["source_bindings"]):
            raise AssertionError("new evidence absent from consumed review")
    proof = dict(action="no_order", status="UNREGISTERED_RESEARCH_CANDIDATE_VERIFIED_PENDING_INDEPENDENT_REVIEW",
        generated_at=datetime.now(timezone.utc).isoformat(), package_binding=binding(package_path),
        public_draft_binding=binding(draft_path), candidate_binding=candidate_binding,
        consumed_review_binding=binding(packet_path), research_case_binding=binding(OUT / "research-case.json"),
        runtime_directory=runtime.relative_to(ROOT).as_posix(), descriptor_input_sha256=descriptor.input_sha256,
        model_context=context, draft_verification=draft_verification,
        shared_model="ResidualIncomeEquityValuationModel", scenario_values_unchanged=True,
        facts_unchanged=True, original_source_metadata_unchanged=True,
        original_point_in_time=old["point_in_time"], new_point_in_time=package["point_in_time"],
        research_date_basis="Asia/Shanghai actual date; available/computed timestamps are actual UTC instants",
        source_count=len(verified_sources), unchanged_preexisting_bindings=[dict(path=k, sha256=v) for k,v in before.items()],
        checks=["local source SHA", "source-bound v3 descriptor and cutoff", "both ResearchCase constructors",
            "same shared-model numeric results", "non-consuming scoped scheduler", "actual application artifact bundle",
            "public draft independent validators", "pending candidate exact consumption verifier",
            "consumed-review independent reprojection", "review intake and read-only preview",
            "all four supplemental materials bound into consumed review", "current registration rejection",
            "historical inputs, watched config and implementation SHA unchanged"],
        current_registration_verified=False, expected_current_registration_rejection=expected_rejection,
        required_next="Root and independent review; only then consider registering new draft/candidate exact hashes. No automatic Web integration.",
        no_signing_performed=True, economic_parameters_validated=False, g3_approved=False,
        public_valuation_changed=False, config_pointers_changed=False, event_coverage="INCOMPLETE", best_cell_selected=False)
    write_new_json(OUT / "verification.json", proof)
    write_new_json(OUT / "candidate-binding.json", dict(action="no_order", candidate_binding=candidate_binding,
        public_draft_binding=binding(draft_path), registration_status="NOT_REGISTERED",
        source_scope="local runtime dependencies required; this folder alone is not a portable closure"))
    public_files = [p for p in sorted(OUT.iterdir()) if p.is_file()
        and not p.name.startswith("build-error") and p.name != "build-start.json"]
    write_new_json(OUT / "upload-allowlist.json", dict(action="no_order",
        public_files=[p.relative_to(ROOT).as_posix() for p in public_files]
            + [(OUT / name).relative_to(ROOT).as_posix() for name in ("upload-allowlist.json", "manifest.json")],
        local_only_exclusions=[p.relative_to(ROOT).as_posix() for p in OUT.iterdir()
            if p.name.startswith("build-error") or p.name == "build-start.json"],
        runtime_candidate_status="LOCAL_ONLY_PENDING_ROOT_REVIEW_NOT_PORTABLE_ARCHIVE",
        note="Exact file allowlist only; never recursively add this directory. Runtime originals and failed tracebacks are excluded."))
    public_files.append(OUT / "upload-allowlist.json")
    write_new_json(OUT / "manifest.json", dict(action="no_order", status=proof["status"],
        generated_at=datetime.now(timezone.utc).isoformat(), script=binding(script_copy),
        files=[binding(p) for p in public_files], candidate_binding=candidate_binding,
        verification_binding=binding(OUT / "verification.json")))
    return dict(status=proof["status"], action="no_order", manifest=binding(OUT / "manifest.json"),
        candidate_binding=candidate_binding, verification=binding(OUT / "verification.json"))


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, indent=2))
