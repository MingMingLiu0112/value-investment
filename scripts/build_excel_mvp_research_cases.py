"""Build the Stage-A research cases from pinned, retained evidence only."""
from __future__ import annotations

from datetime import date, datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path

from value_investment_agent.research_case import ResearchCase
from value_investment_agent.research_gate import evaluate

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runtime" / "excel-mvp-research-cases"
POINTER = ROOT / "runtime" / "excel-mvp-research-cases-latest.json"
DISTRIBUTION_POINTER = ROOT / "runtime/company-research/600519-distribution-capacity-evidence-latest.json"
FRANCHISE_POINTER = ROOT / "runtime/company-research/600519-franchise-duration-evidence-latest.json"
MOUTAI_CARD_POINTER = ROOT / "runtime/company-research/600519-research-card-evidence-latest.json"
MIDEA_SHARE_BASIS_POINTER = ROOT / "runtime/company-research/midea-2025-share-basis-latest.json"
MIDEA_EQUITY_SCOPE_POINTER = ROOT / "runtime/company-research/midea-consolidated-equity-scope-latest.json"
MIDEA_EQUITY_RETURN_POINTER = ROOT / "runtime/company-research/midea-2014-2024-equity-return-candidate-latest.json"
MIDEA_FINANCE_CO_POINTER = ROOT / "runtime/company-research/midea-finance-co-2025-size-observation-latest.json"
MIDEA_HKEX_SHARE_POINTER = ROOT / "runtime/company-research/midea-20260330-hkex-share-basis-latest.json"
SHENHUA_CANDIDATE_POINTER = ROOT / "runtime/company-research/shenhua-cyclical-candidate-inputs-latest.json"
SHENHUA_SUBSIDIARY_POINTER = ROOT / "runtime/company-research/shenhua-2025-subsidiary-allocation-evidence-latest.json"
SHENHUA_IFRS_TAX_POINTER = ROOT / "runtime/company-research/shenhua-2025-ifrs-subsidiary-tax-review-latest.json"
SHENHUA_OPERATING_CYCLE_POINTER = ROOT / "runtime/company-research/shenhua-2014-2025-operational-cycle-series-latest.json"
SHENHUA_OPERATING_CYCLE_AUDIT_POINTER = ROOT / "runtime/company-research/shenhua-2014-2025-operational-cycle-audit-latest.json"
SHENHUA_ATTRIBUTABLE_PROFIT_SERIES_POINTER = ROOT / "runtime/company-research/shenhua-2014-2025-attributable-profit-series-latest.json"
SHENHUA_PRICE_COST_BRIDGE_POINTER = ROOT / "runtime/company-research/shenhua-2014-2025-price-cost-transport-bridge-latest.json"
SHENHUA_EXTERNAL_INDEX_POINTER = ROOT / "runtime/company-research/shenhua-external-index-provenance-latest.json"
SHENHUA_PUBLIC_INDEX_HISTORY_POINTER = ROOT / "runtime/company-research/shenhua-public-index-history-latest.json"
SHENHUA_BSPI_RECONCILIATION_POINTER = ROOT / "runtime/company-research/shenhua-bspi-annual-report-reconciliation-latest.json"
SHENHUA_BSPI_POINT_IN_TIME_POINTER = ROOT / "runtime/company-research/shenhua-bspi-point-in-time-publications-latest.json"
SHENHUA_INTERNAL_COAL_POWER_POINTER = ROOT / "runtime/company-research/shenhua-2025-internal-coal-power-reconciliation-latest.json"
SHENHUA_ROUTE_DELIVERED_COST_POINTER = ROOT / "runtime/company-research/shenhua-2014-2025-route-delivered-cost-audit-latest.json"
TZ = timezone(timedelta(hours=8))


def reference(ref_id: str, path: str, *, description: str) -> dict[str, str]:
    target = ROOT / path
    return {"id": ref_id, "path": path, "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            "description": description}


def pointer_reference(ref_id: str, pointer: Path, *, description: str) -> dict[str, str]:
    pin = json.loads(pointer.read_text(encoding="utf-8"))
    path = ROOT / pin["path"] / "evidence.json"
    if not path.is_relative_to(ROOT.resolve()):
        raise ValueError("Pointer escapes project root")
    if hashlib.sha256(path.read_bytes()).hexdigest() != pin["sha256"].lower():
        raise ValueError("Pinned evidence changed: " + str(pointer))
    return {"id": ref_id, "path": str(path.relative_to(ROOT)), "sha256": pin["sha256"].lower(),
            "description": description}


def cases() -> list[ResearchCase]:
    midea_path = "runtime/company-research/midea-admission-audit-20260912T060015556280Z/evidence.json"
    midea_financial = "runtime/company-research/midea-financial-scope-audit-20260912T054916602476Z/evidence.json"
    midea_business = "runtime/company-research/midea-business-evidence-20260921/evidence.json"
    midea_fcff_facts = "runtime/company-research/midea-fcff-facts-20260922/evidence.json"
    shenhua_business = "runtime/company-research/shenhua-2025-business-evidence-20260921/evidence.json"
    shenhua_execution = "runtime/strategy-validation/shenhua-real-execution-contract-20260912T060850Z/summary.json"
    shenhua_readiness = "docs/historical-financial-readiness.md"
    generated = datetime(2026, 9, 22, 0, 0, tzinfo=TZ)
    return [
        ResearchCase(
            symbol="600519", name="贵州茅台", as_of=date(2026, 9, 21), run_id="excel-mvp-20260921",
            generated_at=generated, research_version="excel-mvp-v1", industry="高端白酒",
            investment_path="成熟优质复利 + 现金回报", thesis="品牌、渠道与产品结构是否能支撑长期盈利与每股现金回报，仍须以量价和现金归属持续检验。",
            return_driver="盈利持续性、现金分配及资本配置；估值重评不预设。", mispricing_hypothesis="尚未证明市场低估；逆向检验存在多解，不能反推唯一市场预期。",
            financial_summary={"period_end": "2026-06-30", "parent_equity_cny": "251253594419.50", "ttm_ex_nonrecurring_parent_profit_cny": "81367067677.44", "liquor_revenue_growth_pct": "-1.08", "liquor_sales_volume_growth_pct": "2.13", "registered_payout_ratio": "0.75", "fy2025_parent_cash_coverage_of_distribution": "1.224135"},
            positives=[
                {"kind":"fact", "text":"已归档2026年中报归母权益与扣非 TTM 利润锚，且2026年上半年归母利润为445.17亿元。", "evidence_refs":["moutai_card"]},
                {"kind":"fact", "text":"2024年回购计划已于2025年完成：回购并注销3,927,585股，金额约60亿元，资本回报与股本减少是可观察事实。", "evidence_refs":["moutai_card"]},
                {"kind":"interpretation", "text":"高端白酒的销量、实现价格和产品结构共同决定商业质量，不能用品牌标签或产能代替这些验证线。", "evidence_refs":["moutai_card"]},
                {"kind":"fact", "text":"2025年报披露最近三个会计年度累计现金分红1,900.09亿元，对应年均利润840.56亿元，约75.35%；当前75%研究派息率处于该历史证据和已登记50%-85%压力区间内。", "evidence_refs":["moutai_distribution"]},
                {"kind":"fact", "text":"优势持续期已独立审计：五年为有界条件性中央假设，立即衰减与十年衰减是压力边界，终值不保留永久超额回报；该审计不证明未来竞争优势实际持续时长。", "evidence_refs":["moutai_franchise"]},
            ],
            counter_evidence=[
                {"kind":"fact", "text":"FY2025白酒收入同比-1.08%，销量同比+2.13%，收入/吨近似指标下降；不能仅凭销量确认价格或结构恢复。", "evidence_refs":["moutai_card"]},
                {"kind":"fact", "text":"FY2025母公司经营现金流326.18亿元、子公司投资收益回款496.53亿元、资本开支31.04亿元，合计覆盖646.72亿元分红及利息约122.4%；但2026上半年子公司投资收益回款仅1.01亿元，覆盖约41.4%，子公司回款高度季节性，全年2026分配能力仍待披露。", "evidence_refs":["moutai_distribution"]},
                {"kind":"fact", "text":"2026年日常关联交易预计上限92.06亿元；已披露程序不证明实际定价公允或治理质量优秀，仍须复核实际发生额和现金影响。", "evidence_refs":["moutai_card"]},
                {"kind":"interpretation", "text":"优势持续期审计确认模型假设有界且可复核，但没有经验计量未来竞争优势时长，不能据此提高估值置信度。", "evidence_refs":["moutai_franchise"]},
            ],
            thesis_breakers=[
                {"kind":"hypothesis", "text":"若后续披露继续显示销量增长而收入/吨或产品结构走弱，应重审盈利恢复与优势期限。", "evidence_refs":["moutai_card"]},
                {"kind":"hypothesis", "text":"若全年经营现金流、必要投入和现金归属无法支持分配能力，应重审现金回报论点。", "evidence_refs":["moutai_card"]},
                {"kind":"hypothesis", "text":"若关联交易实际发生额、定价样本或独立审计信息与已披露原则不一致，应重审治理与资本配置论点。", "evidence_refs":["moutai_card"]},
            ],
            next_events=[{"kind":"fact", "text":"下一份定期报告及重大资本动作披露是预先登记的复核事件。", "evidence_refs":["moutai_card"]}],
            evidence_status="verified", valuation_status="not_ready", research_status="financial_scope_approved", blockers=["优势持续期仅审计为有界假设，未来实际持续时长尚未证实", "全年2026母公司可分配现金与子公司回款尚未披露", "正式估值未获批准"],
            evidence_refs=[pointer_reference("moutai_card", MOUTAI_CARD_POINTER, description="茅台研究卡及其指向的公告、Hash和反证材料"), pointer_reference("moutai_distribution", DISTRIBUTION_POINTER, description="茅台历史派息率与母公司全年/半年现金覆盖证据包"), pointer_reference("moutai_franchise", FRANCHISE_POINTER, description="茅台优势持续期有界政策与压力边界独立审计")], quote_date=None, financial_period=date(2026,6,30), missing_date_reasons={"quote_date":"本阶段未引入可用于结论的同日行情；不以旧报价产生买卖判断。"}),
        ResearchCase(
            symbol="000333", name="美的集团", as_of=date(2026, 9, 22), run_id="excel-mvp-20260921",
            generated_at=generated, research_version="excel-mvp-v1", industry="家电与智能制造", investment_path="成长价值 / 成熟经营", thesis="规模、产品结构、海外与再投资回报需要由完整财务口径和商业证据共同验证。",
            return_driver="经营效率、再投资和每股价值增长；暂不把利润规模转换为每股价值。", mispricing_hypothesis="尚未建立；会计每股收益口径已披露，但仍不能直接推导当前估值每股价值、合理价或安全边际。",
            financial_summary={"period_end":"2025-12-31", "operating_revenue_cny":"456451731000", "operating_cash_flow_cny":"53345930000", "attributable_ordinary_equity_cny":"223221305000", "minority_equity_cny":"13202918000", "attributable_ordinary_net_profit_cny":"43945411000", "year_end_issued_total_shares":7597145346, "reported_fy2025_weighted_shares_thousand":7559265, "reported_fy2025_basic_eps_cny":"5.80", "scope":"会计每股收益口径已披露；不批准为当前估值分母，也不是 FCFF 估值输入。"},
            positives=[
                {"kind":"fact", "text":"2025年营业收入4,564.52亿元，同比增长12.11%；家电业务收入2,999.27亿元，同比增长11.28%。", "evidence_refs":["midea_business"]},
                {"kind":"fact", "text":"商用及工业解决方案收入1,227.53亿元，同比增长17.47%，增速高于家电业务。", "evidence_refs":["midea_business"]},
                {"kind":"fact", "text":"经营活动现金流533.46亿元，资本开支现金流出111.42亿元；仅作为现金创造与再投资的待核验线索。", "evidence_refs":["midea_fcff_facts"]},
                {"kind":"fact", "text":"2025年报已披露期末A/H总股本7,597,145,346股，会计加权普通股7,559,265千股、稀释后7,608,132千股；这是会计EPS范围，不代表当前估值分母。", "evidence_refs":["midea_share_basis"]},
                {"kind":"fact", "text":"2025年末归母普通股权益223,221,305千元、少数股东权益13,202,918千元，归母普通股净利43,945,411千元；金融业务在合并报表可见但无独立财务口径，剩余收益/权益价值路线仅登记为候选，未注册模型。", "evidence_refs":["midea_equity_scope"]},
                {"kind":"fact", "text":"2014-2024年归母普通股权益、归母净利、现金分红和回购式现金回报已按各年原始年报页码建立候选序列；其中2024年现金分红267.12亿元，序列只证明历史现金回报，不构成未来ROE、派息或每股价值承诺。", "evidence_refs":["midea_equity_return_history"]},
                {"kind":"fact", "text":"美的财务公司2025年经审计总资产444.64亿元、净资产78.59亿元、净利润4.11亿元，分别约为美的合并归母普通股权益3.52%和归母普通股净利润0.93%；只证明金融公司在合并规模中不占数量主导，不是估值模型输入。", "evidence_refs":["midea_finance_co"]},
                {"kind":"fact", "text":"HKEX 2026-03-30全年业绩公告披露公告日A股库存股80,412,541股，并以总股本7,603,276,186股剔除该库存股后的7,522,863,645股作为末期股息基数；这是公告日时点事实，不是2025年末库存股或当前估值日普通股分母。", "evidence_refs":["midea_hkex_share_basis"]},
            ],
            counter_evidence=[
                {"kind":"fact", "text":"家电业务毛利率29.90%，同比下降0.08个百分点；商用及工业解决方案毛利率20.81%，同比下降0.58个百分点。", "evidence_refs":["midea_business"]},
                {"kind":"fact", "text":"洗衣机销量同比下降6.17%，不能用整体收入增长替代全部品类的需求验证。", "evidence_refs":["midea_business"]},
                {"kind":"fact", "text":"2025年报年末库存股只有账面金额8,151,117千元，没有披露年末股数；HKEX公告虽披露了2026-03-30公告日股数80,412,541股，但两者都不是2026-09-22估值日范围，会计加权普通股的逐日权重也未披露。", "evidence_refs":["midea_share_basis", "midea_hkex_share_basis", "midea_financial"]},
                {"kind":"fact", "text":"合并归母权益和归母净利虽然已披露，但金融业务没有独立利润表和资产负债表，不能直接从合并权益/利润推导普通股权益价值或剩余收益。", "evidence_refs":["midea_equity_scope"]},
                {"kind":"fact", "text":"2014-2024历史权益、利润与现金回报序列虽已逐页定位，但历史序列没有注册前瞻ROE、带日期的权益成本、当前派息政策和当前普通股分母，也没有完成干净盈余权益滚动对账，因此仍是候选证据。", "evidence_refs":["midea_equity_return_history"]},
                {"kind":"fact", "text":"财务公司关联公告虽称2025年数据已经审计，但没有提供独立利润表、资产负债表、税费/债务/现金/营运资本拆分；不能从中构造工业EBIT或企业价值桥接。", "evidence_refs":["midea_finance_co"]},
            ],
            thesis_breakers=[
                {"kind":"hypothesis", "text":"若后续报告显示核心家电或商用工业业务收入增速显著放缓且毛利率继续承压，应重审规模增长能否转化为每股回报。", "evidence_refs":["midea_business"]},
                {"kind":"hypothesis", "text":"若空调和制冷以外品类的销量下滑扩散，需重审需求韧性与产品结构判断。", "evidence_refs":["midea_business"]},
                {"kind":"hypothesis", "text":"若现金创造、资本开支或营运资本的合并口径在后续核对中无法转化为适用的 FCFF 范围，成长价值模型不得进入正式估值。", "evidence_refs":["midea_fcff_facts"]},
                {"kind":"hypothesis", "text":"若后续估值日无法把会计加权分母、库存股与公司行动日期映射到同一时点普通股范围，成长价值模型不得生成每股价值。", "evidence_refs":["midea_share_basis"]},
            ],
            next_events=[
                {"kind":"fact", "text":"下一份定期报告将复核分部收入增速、分部毛利率及主要品类销量。", "evidence_refs":["midea_business"]},
                {"kind":"fact", "text":"后续公告或定期报告若披露当前库存股股数、公司行动日期权重及估值日A/H范围，再评估是否注册每股分母。", "evidence_refs":["midea_share_basis"]},
                {"kind":"fact", "text":"后续若取得金融业务独立财务口径、带日期的权益成本、ROE/派息假设和当前普通股分母，再评估是否把剩余收益/权益价值路线从候选升级为注册模型。", "evidence_refs":["midea_equity_scope"]},
                {"kind":"fact", "text":"后续定期报告、分红预案、回购进展与公司行动公告将用于继续更新2014年以来的权益、利润和现金回报候选序列，但单靠新增历史年份仍不能注册前瞻权益价值模型。", "evidence_refs":["midea_equity_return_history"]},
                {"kind":"fact", "text":"后续若取得财务公司或金融业务完整独立报表、经审计税费及资产分配，再评估是否解除工业FCFF口径阻断；此前不把财务公司规模观察写入任何模型输入。", "evidence_refs":["midea_finance_co"]},
                {"kind":"fact", "text":"后续若需使用HKEX公告披露的2026-03-30股本与库存股范围，必须同时登记同日的全部估值输入并注明估值日，不能把公告日股本直接套到以后日期。", "evidence_refs":["midea_hkex_share_basis"]},
            ],
            evidence_status="partial", valuation_status="not_ready", research_status="financial_scope_partial", blockers=["会计加权普通股已披露，但当前估值日普通股分母仍未注册", "年末库存股股数与逐日加权权重未披露", "财务来源独立性未验证", "合并归母权益/利润已披露，但金融业务无独立报表；剩余收益/权益价值路线未注册，前瞻ROE、股权成本、派息政策和当前普通股分母尚未证明", "2014-2024权益回报历史序列仅登记为候选，未完成干净盈余权益滚动对账，不能升级为模型输入", "财务公司规模观察仅登记为非模型输入，未提供金融业务独立报表或工业税费/债务/现金/营运资本分配", "正式估值不存在"],
            evidence_refs=[reference("midea_admission",midea_path,description="美的准入审计"), reference("midea_financial",midea_financial,description="美的财务口径审计"), reference("midea_business",midea_business,description="美的2025年报的收入、分部利润率、销量与研发披露"), reference("midea_fcff_facts",midea_fcff_facts,description="美的2025年报合并现金流与 FCFF 口径限制"), pointer_reference("midea_share_basis", MIDEA_SHARE_BASIS_POINTER, description="美的2025年报会计每股收益、期末A/H股本和库存股范围证据包（未批准为估值分母）"), pointer_reference("midea_hkex_share_basis", MIDEA_HKEX_SHARE_POINTER, description="美的HKEX 2026-03-30业绩公告的公告日库存股与末期股息基数（点时事实、未注册为当前估值分母）"), pointer_reference("midea_equity_scope", MIDEA_EQUITY_SCOPE_POINTER, description="美的2025年报合并归母/少数股东权益与利润、可见金融业务口径及未注册权益估值路线"), pointer_reference("midea_equity_return_history", MIDEA_EQUITY_RETURN_POINTER, description="美的2014-2024归母权益、归母利润与现金回报候选序列（逐页来源、未注册模型输入）"), pointer_reference("midea_finance_co", MIDEA_FINANCE_CO_POINTER, description="美的财务公司2025年经审计/未审计规模观察（非模型输入）")], quote_date=None, financial_period=date(2025,12,31), missing_date_reasons={"quote_date":"本阶段不使用行情生成结论。"}),
        ResearchCase(
            symbol="601088", name="中国神华", as_of=date(2026, 9, 21), run_id="excel-mvp-20260922",
            generated_at=generated, research_version="excel-mvp-v1", industry="煤炭与综合能源", investment_path="周期正常化", thesis="煤炭、发电、运输及煤化工一体化能否在周期回落时保持可分配现金，需由中周期价格、销量、成本、资源寿命和资本开支共同验证。",
            return_driver="若后续研究成立，回报来自穿越周期的现金流和资本配置，而不是高点 PE 的机械外推。", mispricing_hypothesis="未建立；尚未知道当前市场价格对煤价、销量、资本开支和分配能力的隐含假设。",
            financial_summary={"period_end":"2025-12-31", "operating_revenue_cny":"294916000000", "parent_attributable_net_profit_cny":"52849000000", "operating_cash_flow_cny":"75059000000", "profitability_status":"弱：营业利润同比-13.3%，归母净利同比-5.3%", "cash_status":"正常但下降：经营现金流同比-17.6%", "balance_sheet_status":"数据不足：本轮未完成债务到期、资源寿命和压力流动性审查", "growth_status":"弱：煤炭销量、发电量和售价均下降", "capital_allocation_status":"数据不足：已记录2025年资本开支446.86亿元，尚未完成中周期回报和分配能力审查"},
            positives=[
                {"kind":"fact", "text":"2025年经营活动现金流750.59亿元，虽同比下降17.6%，仍是周期性现金创造的可追溯起点。", "evidence_refs":["shenhua_business"]},
                {"kind":"fact", "text":"公司拥有煤炭、发电、铁路、港口、航运与煤化工一体化网络；这是一手披露的经营结构事实，竞争优势仍需独立验证。", "evidence_refs":["shenhua_business"]},
                {"kind":"fact", "text":"2025年铁路运输周转量同比增长0.3%，黄骅港及天津煤码头装船量分别增长1.2%和1.4%，运输环节并非全部同步下行。", "evidence_refs":["shenhua_business"]},
                {"kind":"fact", "text":"周期输入候选包已建立：现金税率、维护资本开支候选区间、营运资本、资源寿命与净现金表面候选均标记未审核，不进入估值模型。", "evidence_refs":["shenhua_candidates"]},
                {"kind":"fact", "text":"母公司法人利润与七家重要非全资子公司边界已审计：母公司投资收益446.07亿元，七家少数股东损益88.32亿元对合并93.34亿元、少数股东权益457.23亿元对合并723.44亿元；披露仍无逐户税前、税费与少数股东分配。", "evidence_refs":["shenhua_ownership"]},
                {"kind":"fact", "text":"HKEX 英文/IFRS 年报已复核：Note 44 只列内部抵销前的 Revenue、Expenses 与 Profit and total comprehensive income，仍无子公司逐户税前利润和所得税；Note 10 列示不同分/子公司税率影响-42.28亿元，因此不能按持股或归母净利比例分配税费。", "evidence_refs":["shenhua_ifrs_tax"]},
                {"kind":"fact", "text":"2014-2025 运营周期证据包已逐页锁定：煤炭总销量与混煤均价、自产煤销量与均价、自产煤单位成本、售电量与电价，并分别保留 2024 原报与 2025 追溯口径；当前状态仅为证据收集，未批准为正常化模型输入。", "evidence_refs":["shenhua_operating_cycle"]},
                {"kind":"fact", "text":"运营序列审查已完成：七类字段均仅批准为可追溯时期事实；混煤均价不得与自产煤单位成本相减，2019/2020 电价不可比，2014/2015/2017/2019 自产煤销量来自后续年报对比表，均未写入周期模型输入。", "evidence_refs":["shenhua_operating_cycle_audit"]},
                 {"kind":"fact", "text":"2014-2025 归母经营利润与税负候选序列已建立：每年锁定合并营业利润、税前利润、所得税、归母/少数股东利润及现金流量表税费；统一持股比例推导和无税负假设区间均只作研究候选，未批准为模型输入。", "evidence_refs":["shenhua_attributable_profit_series"]},
                 {"kind":"fact", "text":"2014-2025 外部煤价与 2025 内部成本/运输桥接已建立：环渤海指数与 NCEI 分年点值、秦皇岛现货价，以及公司自产/长协/内部转移价、铁路/港口/航运单位成本均逐页锁定；指标断点、2018 缺失、2019 区间和内部煤电价量差异仍未完成对账，全部不进入模型。", "evidence_refs":["shenhua_price_cost_transport_bridge"]},
                 {"kind":"fact", "text":"NCEI/BSPI/CCTD 运营方、监管首发公告及编制方案已建立一手溯源包：NCEI 首发日、运营方独立性、BSPI 周度发布规则、CCTD 三类价格与发布频率均已哈希归档；当前平台历史指数表受缴费会员限制，归档即读数和 704/758 两个日期观察均不进入模型。", "evidence_refs":["shenhua_external_index_provenance"]},
                 {"kind":"fact", "text":"CCTD 公开指数中心的五个历史图表端点已逐字节归档：BSPI 802 个唯一日期（2010-2026）、太原 130、陕西 501、鄂尔多斯 525、长江口 379；全部值均为研究观察，不进入周期模型。", "evidence_refs":["shenhua_public_index_history"]},
                 {"kind":"fact", "text":"BSPI 公开端点逐年均值已与神华 2014/2015/2016/2017/2020/2021/2022 年报年度均价对账，七年最大偏差 0.49 元/吨，其中五个年末值与年报完全一致；仅证明序列口径吻合，不证明历史时点未修订。", "evidence_refs":["shenhua_bspi_reconciliation"]},
                 {"kind":"fact", "text":"BSPI 点时发布包已建立：秦皇岛煤炭网 2017/2021/2022 的 577/737/734 一手文章页与 API 响应、2014/2015/2016 CCTD 转载页、2017/2020/2021/2022 明确转载页均已 Hash 归档；2018/2019 各保留多处次级佐证，2020 期末 585 另有中国能源网、易航网、CWESTC、国际煤炭网四处明确转载及 CEI 仅标题/日期/文章路径的登录受限列表，但仍缺 2018/2019/2020 运营方原文且不插值。全部发布值不进入周期模型。", "evidence_refs":["shenhua_bspi_point_in_time"]},
                 {"kind":"fact", "text":"2025 内部煤电 73.2 / 77.7 百万吨差异已交叉核验中英文年报：前者是销售量、后者是发电耗用量，报告未披露吨数桥接；47,702 百万元燃料动力成本不得除以 77.7 当作内部转移价。", "evidence_refs":["shenhua_internal_coal_power"]},
                 {"kind":"fact", "text":"2014-2025 分线路到港/到厂全成本披露审计已完成：13 份中英文年报共 3,609 页未发现分线路周转量、分线路成本或路线分配矩阵；171.6 元/吨只是生产口径，铁路、港口、航运总成本不得简单相除或加总为交付成本。", "evidence_refs":["shenhua_route_delivered_cost"]},
            ],
            counter_evidence=[
                {"kind":"fact", "text":"2025年营收同比下降13.2%，营业利润同比下降13.3%，归母净利同比下降5.3%。", "evidence_refs":["shenhua_business"]},
                {"kind":"fact", "text":"煤炭销量同比下降6.4%、平均售价下降12.1%；售电量下降3.9%、平均电价下降4.0%。", "evidence_refs":["shenhua_business"]},
                {"kind":"fact", "text":"2025年火电设备平均利用小时下降，非化石能源装机与发电量增长；这构成煤电利用与价格的外部反证背景。", "evidence_refs":["shenhua_business"]},
            ],
            thesis_breakers=[
                {"kind":"hypothesis", "text":"若后续煤炭售价、销量和单位成本的组合继续恶化，且经营现金流不能覆盖必要资本开支与分配需求，应重审周期现金回报论点。", "evidence_refs":["shenhua_business"]},
                {"kind":"hypothesis", "text":"若火电利用小时和售电价格继续受新能源替代与电力市场变化挤压，应重审煤电协同能否稳定穿越周期。", "evidence_refs":["shenhua_business"]},
                {"kind":"hypothesis", "text":"若资源寿命、债务到期、矿业权投入或大型项目资本开支的审查显示现金流压力高于年报当前摘要所能解释的程度，周期正常化估值不得成立。", "evidence_refs":["shenhua_business"]},
            ],
            next_events=[
                {"kind":"fact", "text":"下一份定期报告将复核煤炭销量与价格、售电量与电价、经营现金流及资本开支。", "evidence_refs":["shenhua_business"]},
                {"kind":"fact", "text":"候选包显示，仍须独立审核归母税前营业利润、资产负债表日后新增股份后的普通股分母，以及归母净现金与受限现金分配。", "evidence_refs":["shenhua_candidates"]},
                {"kind":"fact", "text":"下一关键事实是取得可审计的子公司逐户税前利润、所得税与少数股东分配；此前不得用母公司法人利润或合并比例重构归母税前营业利润。", "evidence_refs":["shenhua_ownership"]},
                {"kind":"fact", "text":"运营序列已审计为时期证据；下一步建立独立商品价格区间、全口径成本曲线和可复算的归母经营利润桥接，此前不向周期模型写入任何 operating_inputs。", "evidence_refs":["shenhua_operating_cycle_audit"]},
                 {"kind":"fact", "text":"下一步以十二年期利润与税负候选序列为事实边界，结合外部煤价、电力和运输基准评审中周期情景；未完成前所有 bear/base/bull 输入保持 null。", "evidence_refs":["shenhua_attributable_profit_series"]},
                 {"kind":"fact", "text":"外部煤价包络已归档，但存在指标断点与披露缺口；下一步补指数运营方原始日频档案并完成煤电路径对账，在此之前不推导中周期利润。", "evidence_refs":["shenhua_price_cost_transport_bridge"]},
                 {"kind":"fact", "text":"BSPI 点时发布包已归档秦皇岛煤炭网 2017/2021/2022 一手文章页、2014/2015/2016 CCTD 转载页，以及 2018/2019 多处次级佐证、2020 中国能源网/易航网/CWESTC/国际煤炭网转载和 CEI 标题/日期/文章路径列表。下一步补 2018/2019/2020 运营方原文及 2023 后 NCEI 原始发布与修订档案；缺失年份不得插值或升级。", "evidence_refs":["shenhua_bspi_point_in_time"]},
                 {"kind":"fact", "text":"补神华矿坑→铁路→港口/航运→客户的路线级周转量、装船量与吨海里成本，或取得单独披露的路线分配矩阵；未取得前不构造到港/到厂全成本。", "evidence_refs":["shenhua_route_delivered_cost"]},
              ],
               evidence_status="verified", valuation_status="not_ready", research_status="financial_scope_partial", blockers=["重要非全资子公司逐户税前、税费与少数股东分配未披露", "普通股分母已批准但尚未与估值日期和其余输入一并注册", "归母净现金与受限现金未分配", "运营、利润与现金税候选序列仅作研究边界，未批准为模型输入", "外部煤价与成本运输桥接存在指标断点；2025 内部煤电销售 73.2 Mt 与发电耗用 77.7 Mt 是销售/耗用两套口径且年报未给桥接，未批准为模型输入", "BSPI 2018/2019/2020 仍缺运营方原文；2020 已有中国能源网、易航网、CWESTC、国际煤炭网四处明确转载加 CEI 标题/日期/文章路径列表，2014 的 525 非年末发布、2017 的 577 与年报 578 尚未对账，2023 年后 NCEI 断点及神华内部价格路径未对账，未批准为模型输入", "2014-2025 年报未披露分线路运输周转量、分线路成本或路线分配矩阵；171.6 元/吨仅为生产口径，不能与运输总成本相加形成到港/到厂全成本，未批准为模型输入", "正式周期估值不存在"], evidence_refs=[reference("shenhua_business",shenhua_business,description="神华2025年报经营、现金流、资本开支及周期反证"), reference("shenhua_execution",shenhua_execution,description="神华历史执行输入合同"), reference("shenhua_readiness",shenhua_readiness,description="历史财务口径准备度记录"), pointer_reference("shenhua_candidates", SHENHUA_CANDIDATE_POINTER, description="神华周期输入候选包（未审核）"), pointer_reference("shenhua_ownership", SHENHUA_SUBSIDIARY_POINTER, description="神华母公司法人利润与重要非全资子公司边界审计"), pointer_reference("shenhua_ifrs_tax", SHENHUA_IFRS_TAX_POINTER, description="神华 HKEX 英文/IFRS 年报子公司税务披露复核"), pointer_reference("shenhua_operating_cycle", SHENHUA_OPERATING_CYCLE_POINTER, description="神华 2014-2025 运营周期证据包（仅研究证据）"), pointer_reference("shenhua_operating_cycle_audit", SHENHUA_OPERATING_CYCLE_AUDIT_POINTER, description="神华 2014-2025 运营周期独立审查（仅时期事实）"), pointer_reference("shenhua_attributable_profit_series", SHENHUA_ATTRIBUTABLE_PROFIT_SERIES_POINTER, description="神华 2014-2025 归母经营利润与税负候选序列（未批准）"), pointer_reference("shenhua_price_cost_transport_bridge", SHENHUA_PRICE_COST_BRIDGE_POINTER, description="神华 2014-2025 外部煤价与 2025 成本/运输桥接（未对账候选）"), pointer_reference("shenhua_external_index_provenance", SHENHUA_EXTERNAL_INDEX_POINTER, description="神华 NCEI/BSPI/CCTD 运营方一手溯源包（历史档案受会员权限限制）"), pointer_reference("shenhua_public_index_history", SHENHUA_PUBLIC_INDEX_HISTORY_POINTER, description="神华 CCTD 五个公开历史指数端点（已归档，未对账）"), pointer_reference("shenhua_bspi_reconciliation", SHENHUA_BSPI_RECONCILIATION_POINTER, description="神华 BSPI 公开端点与七份年报年度均价对账（研究观察，未批准）"), pointer_reference("shenhua_bspi_point_in_time", SHENHUA_BSPI_POINT_IN_TIME_POINTER, description="神华 BSPI 点时发布页与转载页证据包（无模型输入）"), pointer_reference("shenhua_internal_coal_power", SHENHUA_INTERNAL_COAL_POWER_POINTER, description="神华 2025 内部煤电销售/耗用口径与燃料成本边界复核（未批准）"), pointer_reference("shenhua_route_delivered_cost", SHENHUA_ROUTE_DELIVERED_COST_POINTER, description="神华 2014-2025 分线路到港/到厂全成本披露审计（未批准）")], quote_date=None, financial_period=date(2025,12,31), missing_date_reasons={"quote_date":"本阶段不使用行情生成结论；行情缺失仅阻断价格桥接。"}),
    ]


def build() -> dict:
    records=[]
    for case in cases():
        gate=evaluate(case)
        records.append({"case": json.loads(case.to_json()), "gate": {"results": gate.results, "blockers": gate.blockers, "conclusion": gate.conclusion}})
    payload={"version":"excel-mvp-research-cases-v1", "generated_at":"2026-09-22T00:00:00+08:00", "records":records, "formal_trade_instructions":False}
    OUT.mkdir(parents=True, exist_ok=True)
    target=OUT/"evidence.json"; target.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    digest=hashlib.sha256(target.read_bytes()).hexdigest()
    POINTER.write_text(json.dumps({"path":str(target.parent.relative_to(ROOT)),"sha256":digest},ensure_ascii=False,indent=2),encoding="utf-8")
    return payload

if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, indent=2))
