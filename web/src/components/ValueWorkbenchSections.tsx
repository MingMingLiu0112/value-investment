import { Alert, Card } from "antd";
import type {
  ValueWorkbenchResponse,
  ValueWorkbenchSection,
  OperatingAssumptionDraftResponse,
  FirstResearchInputResponse,
  OperatingDriverBridge,
} from "../services/api";
import type { CompanyProfile } from "./CompanyProfilePanel";
import { CompanyProfileView } from "./CompanyProfilePanel";
import { OperatingAssumptionDraftView } from "./OperatingAssumptionDraftPanel";
import { FirstResearchInputView } from "./FirstResearchInputPanel";
import { MainValuationRevalidationPanel } from "./MainValuationRevalidationPanel";
import {
  OperatingDriverBridgeView,
  OperatingCashConsumptionView,
  Readable,
} from "./LiveOperatingResearchPanel";
import { ValueResearchAnalysis } from "./ValueResearchAnalysis";
import type {
  DecisionItem,
  ValueResearchAnalysis as NativeAnalysis,
} from "../types/api";

const STATUS: Record<string, string> = {
  SOURCE_BOUND_RESULTS: "有来源绑定结果（不等于批准）",
  PARTIAL: "部分结果，缺口保留",
  NOT_STARTED: "尚未开始或没有登记结果",
  UNASSESSABLE: "来源或当前结果不可核验",
  PRIVATE_CONTEXT_REQUIRED: "需要另行提供个人上下文",
  BOUND_SOURCES: "已有核验来源",
  NO_VERIFIED_BINDINGS: "尚无可核验来源",
};
const obj = (value: unknown): Record<string, any> =>
  value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, any>)
    : {};
function blockers(value: unknown): string {
  if (typeof value === "string") return value;
  const item = obj(value);
  return (
    [
      item.source,
      typeof item.reason === "string" ? item.reason : undefined,
      item.error_type,
    ]
      .filter(Boolean)
      .join(" · ") || "有未解释的缺口，暂不据此作判断"
  );
}
const usable = (value: Record<string, any>) =>
  Object.keys(value).length > 0 &&
  !["UNASSESSABLE", "NOT_STARTED", "MISSING_SOURCE", "UNAVAILABLE"].includes(
    value.status,
  );
function Content({
  section,
  symbol,
}: {
  section: ValueWorkbenchSection;
  symbol: string;
}) {
  const native = obj(section.data?.native_results),
    live = obj(native.live),
    first = obj(native.first_input),
    main = obj(native.main_revalidation),
    legacy = obj(native.existing_analysis);
  if (section.id === "profile" && usable(obj(native.profile)))
    return (
      <CompanyProfileView
        data={native.profile as CompanyProfile}
        symbol={symbol}
      />
    );
  if (section.id === "selection") {
    const selected = obj(native.selection);
    return (
      <>
        <p>
          观察范围：
          {selected.observed_scope_status === "IN_OBSERVED_SCOPE"
            ? "本公司在已观察范围内"
            : "未证明本公司在本次已观察范围内，不代表全市场不合格"}
        </p>
        {(Array.isArray(selected.items) ? selected.items : []).map(
          (row: any, i: number) => (
            <section key={i}>
              <h3>{row.company_name || row.name || row.symbol}</h3>
              <ul>
                {(row.reasons || []).map((reason: any, j: number) => (
                  <li key={j}>{blockers(reason)}</li>
                ))}
              </ul>
              <details>
                <summary>各通道筛选依据及排除条件</summary>
                <Readable
                  value={
                    row.channel_evaluations || row.conditions || row.blockers
                  }
                />
              </details>
            </section>
          ),
        )}
        <details>
          <summary>筛选期间、覆盖及刷新限制</summary>
          <Readable value={selected.context} />
        </details>
      </>
    );
  }
  if (section.id === "research")
    return (
      <>
        <p>
          执行成功不等于独立经济审查通过；下列为来源绑定研究草案，不当作新事实。缺失角色不会由旧结果补齐。
        </p>
        {(["FUNDAMENTAL", "COUNTER_EVIDENCE", "EVENT"] as const).map(
          (role, i) => {
            const result = obj(obj(live.research_draft)[role]);
            return (
              <section key={role}>
                <h3>
                  {
                    [
                      "经营基本面与量价成本",
                      "反证、未知与失效条件",
                      "已见事件与未覆盖范围",
                    ][i]
                  }
                </h3>
                {result.draft ? (
                  <Readable value={result.draft} />
                ) : (
                  <p>本次没有可读取的该角色研究。</p>
                )}
              </section>
            );
          },
        )}
      </>
    );
  if (section.id === "assumptions")
    return (
      <>
        <p>
          参数只读：值与区间是研究假设，非历史事实；比率0.10表示10%。主体、期间、原始金额单位及理由按下方来源合同展示，未提供的信息不补零。
        </p>
        {live.operating_driver_bridge && (
          <OperatingDriverBridgeView
            bridge={live.operating_driver_bridge as OperatingDriverBridge}
          />
        )}
        {usable(obj(native.existing_draft)) && (
          <details>
            <summary>既有研究包的假设与反证</summary>
            <OperatingAssumptionDraftView
              data={native.existing_draft as OperatingAssumptionDraftResponse}
              symbol={symbol}
            />
          </details>
        )}
        {!live.operating_driver_bridge &&
          !usable(obj(native.existing_draft)) && (
            <p>尚无可核验参数，不允许据此填入预测。</p>
          )}
      </>
    );
  if (section.id === "cash")
    return (
      <>
        <p>
          计算链：经营收入与营业成本 → 税前利润 → 所得税与少数股东归属 →
          股东可达盈利 → 维护/资本需求、资金准备与旧义务清偿 →
          条件年度股东现金。页面仅展示后端计算，不另建公式。
        </p>
        {usable(obj(native.operating_cash)) ? (
          <OperatingCashConsumptionView value={native.operating_cash} />
        ) : (
          <p>
            本次未获得独立经营现金消费者结果；如已有条件估值，其年度现金账见下一节，不能把缺失义务当0。
          </p>
        )}
        <p>偿还旧股利或债务不是本期新分红，不与年度分配相加作股东回报。</p>
      </>
    );
  if (section.id === "valuation")
    return (
      <>
        <p>
          三情景是不同条件的压力研究，不是概率或已采纳主区间。折现和终值由既有模型完成；可展开年度现金账核对，不把数学一致当经济假设已证。
        </p>
        {usable(main) ? (
          <MainValuationRevalidationPanel value={main} symbol={symbol} />
        ) : null}
        {usable(first) && (
          <details open={!usable(main)}>
            <summary>首次编译的独立版本（三情景与年度现金账）</summary>
            <FirstResearchInputView
              data={first as FirstResearchInputResponse}
              symbol={symbol}
            />
          </details>
        )}
        {usable(legacy) && (
          <details open={!usable(main) && !usable(first)}>
            <summary>既有研究版本与现金/估值</summary>
            <ValueResearchAnalysis
              decision={
                {
                  id: symbol,
                  symbol,
                  strategy: "CORE_VALUE",
                  action: "no_order",
                  research_analysis: legacy as NativeAnalysis,
                } as DecisionItem
              }
            />
          </details>
        )}
        {!usable(main) && !usable(first) && !usable(legacy) && (
          <p>没有可核验估值，不能显示空值为零或回退旧成功。</p>
        )}
      </>
    );
  if (section.id === "price")
    return (
      <>
        <Alert
          type="warning"
          message="当前价格不可比：尚未取得经济采用与当前资本、分配、事件、财务及合格报价的同版本对齐。条件研究值不是当前买价。"
        />
        {Object.entries(native).map(([name, value]) => {
          const row = obj(value),
            alignment = obj(row.current_alignment);
          return (
            <div key={name}>
              <h3>
                {name === "main_revalidation" ? "本次条件研究" : "既有研究"}
              </h3>
              <p>
                财务基准：
                {row.financial_basis || row.valuation_date || "未提供"}
                ；最新实际期间：{row.latest_actual_period || "未提供"}；主区间：
                {row.main_range_adopted === true ? "须另核批准" : "未采用"}
                ；当前可比：
                {row.current_comparable === true ? "须另核资格" : "未证明"}。
              </p>
              <ul>
                {[
                  row.reason,
                  ...(Array.isArray(alignment.blockers)
                    ? alignment.blockers
                    : []),
                ]
                  .filter(Boolean)
                  .map((reason: any, i: number) => (
                    <li key={i}>{blockers(reason)}</li>
                  ))}
              </ul>
              <p>
                {obj(row.price_policy).status === "NOT_PREPARED"
                  ? "尚未选择有效数值规则，无当前买价；不从估值复制价格阈值。"
                  : "价格草案须有日期、理由与未批准边界，不能当作当前可执行买价。"}
              </p>
              <details>
                <summary>日期、规则与未批准条件说明</summary>
                <Readable
                  value={{
                    price_policy: row.price_policy,
                    dated_research_review_thresholds:
                      row.dated_research_review_thresholds,
                    current_alignment: row.current_alignment,
                  }}
                />
              </details>
            </div>
          );
        })}
      </>
    );
  if (section.id === "decision")
    return (
      <Alert
        type="warning"
        message="目前仅可人工复核研究；未批准主区间、条件价格或交易。个人数量为空，不下单。"
      />
    );
  if (section.id === "continuity")
    return (
      <p>
        此公开工作台不读取账户、持仓或成交。没有个人上下文，不展示个人买卖数量或虚构持有结论。
      </p>
    );
  if (section.id === "evidence")
    return (
      <>
        <p>
          事实、代码推导、未来假设与未知分别看待；来源绑定不自动证明历史可得或未来经营参数。
        </p>
        <details>
          <summary>展开原件绑定与证据类型</summary>
          <Readable value={section.data} />
        </details>
      </>
    );
  return <p>当前缺少可核验内容，请查看本节缺口；不以源码位置充当投资解释。</p>;
}
export function ValueWorkbenchSections({
  value,
  symbol,
}: {
  value: ValueWorkbenchResponse;
  symbol: string;
}) {
  if (
    value.schema_version !== "value-transparent-workbench-v1" ||
    value.symbol !== symbol ||
    value.action !== "no_order" ||
    value.formal_eligibility !== false ||
    value.quantity !== null ||
    !Array.isArray(value.sections)
  )
    return (
      <Alert
        type="error"
        message="工作台身份或资格边界不符，停止展示，不回退旧成功。"
      />
    );
  return (
    <>
      <Alert
        type="warning"
        message="条件研究，不是投资批准：主区间及当前价格资格须另验；个人数量为空，不下单。"
      />
      <section aria-label="核验来源下载">
        <details>
          <summary>
            原件下载（{value.evidence_downloads?.length || 0} 项，点击展开）
          </summary>
          <p>
            仅下载本次聚合允许的原件；服务端会再次核对绑定。原件存在不等于预测或投资获准。
          </p>
          {(value.evidence_downloads || [])
            .filter(
              (item) =>
                /^[a-zA-Z0-9_-]{1,128}$/.test(item.id) &&
                /^[a-f0-9]{64}$/.test(item.binding.sha256),
            )
            .map((item) => (
              <p key={item.id}>
                <a
                  download
                  href={
                    "/api/v1/value-workbench/evidence/" +
                    encodeURIComponent(item.id) +
                    "?symbol=" +
                    encodeURIComponent(symbol)
                  }
                >
                  下载已核验原件 · {item.binding.path.split("/").pop()}
                </a>
              </p>
            ))}
          {!value.evidence_downloads?.length && (
            <p>
              原件下载不可用：本次聚合未提供已核验的下载条目，不生成任意路径链接。
            </p>
          )}
        </details>
      </section>
      <nav aria-label="研究链各环节">
        {value.sections.map((section) => (
          <a
            key={section.id}
            href={"#value-" + section.id}
            style={{ marginRight: 14 }}
          >
            {section.title}
          </a>
        ))}
      </nav>
      {value.sections.map((section) => (
        <section id={"value-" + section.id} key={section.id}>
          <Card title={section.title} style={{ marginBlock: 16 }}>
            <p>
              {STATUS[section.status] || "状态需核对"}
              {!STATUS[section.status] && <code> · {section.status}</code>}
            </p>
            <p>{section.summary}</p>
            {section.blockers.length > 0 && (
              <Alert
                type="warning"
                message="本节尚未闭合"
                description={
                  <ul>
                    {section.blockers.map((item, i) => (
                      <li key={i}>{blockers(item)}</li>
                    ))}
                  </ul>
                }
              />
            )}
            {section.status === "UNASSESSABLE" ? (
              <p>
                本节结果不可核验，停止显示受影响数据；其他独立环节仍可阅读。
              </p>
            ) : (
              <Content section={section} symbol={symbol} />
            )}
          </Card>
        </section>
      ))}
    </>
  );
}
