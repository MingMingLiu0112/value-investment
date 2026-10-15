import { Link } from "@umijs/max";
import type { DecisionItem } from "../types/api";
import { useCallback } from "react";
import { useApi } from "../hooks/useApi";

function PolicyReadiness({ symbol }: { symbol: string }) {
  const load = useCallback(
    async (signal: AbortSignal) => {
      const response = await fetch(
        `/api/v1/value-policy-review/${encodeURIComponent(symbol)}`,
        { signal },
      );
      const body = await response.json();
      if (!response.ok || body.action !== "no_order")
        throw new Error("复核材料暂不可读取");
      return body as {
        draft?: { rationale?: string; source_bindings?: unknown[] };
        preparation?: {
          status?: string;
          existing_research_blockers?: string[];
        };
      };
    },
    [symbol],
  );
  const review = useApi(load);
  if (review.loading) return <p>正在核验当前审阅材料…</p>;
  if (review.error || !review.data)
    return (
      <p>
        准备状态：材料暂不可读取，请进入详情重试；不会将读取失败视为已批准。
      </p>
    );
  const blockers = review.data.preparation?.existing_research_blockers ?? [];
  return (
    <div>
      <p>
        材料准备：已读取绑定的政策草案与{" "}
        {review.data.draft?.source_bindings?.length ?? 0}{" "}
        项来源；动作规则是否齐全以政策预览为准。
      </p>
      <p>草案说明：{review.data.draft?.rationale ?? "说明尚未提供"}</p>
      <p>
        研究批准：
        {blockers.some((code) =>
          /G3|valuation_not_approved|human_research_approval/.test(code),
        )
          ? "尚缺有权估值审查批准"
          : "此材料不单独证明批准，请核对详情"}
        。事件审查：
        {blockers.some((code) => /event_materiality/.test(code))
          ? "材料性判断尚未完成"
          : "以详情当前事件证据为准"}
        。
      </p>
    </div>
  );
}

export function ConfirmationTasks({
  decisions,
  connected,
}: {
  decisions: DecisionItem[];
  connected: boolean;
}) {
  const companies = decisions.filter(
    (item) =>
      item.price_action_plan?.conditional_valuation_range ||
      item.price_action_plan?.base != null,
  );
  return (
    <section
      id="confirmations"
      aria-label="需要我确认"
      style={{ marginTop: 20, scrollMarginTop: 20 }}
    >
      <h2>需要我确认</h2>
      <p>确认投资条件与核验事实分开处理；完成一项不会自动通过其他资格。</p>
      <details>
        <summary>账户：投资政策、真实持仓和对账</summary>
        <p>
          当前：
          {connected
            ? "账户已连接，具体确认状态以持仓页为准"
            : "尚未连接，无法核验本人资金和风险"}
          。
        </p>
        <p>
          为什么需要：个人风险必须基于真实资金、仓位和本人选择。证据：已有账户台账及投资政策；尚未读取不代表没有风险。
        </p>
        <p>
          谁可确认：账户本人。进入持仓页核对现金和股票，填写投资政策、保存草稿并逐项确认；对账后才可使用对应风险事实。新增成交或账户变化需要重新核对。
        </p>
        <Link to="/portfolio">填写投资政策、核对持仓与对账</Link>
      </details>
      {companies.map((item) => (
        <details key={item.id}>
          <summary>
            {item.name ?? item.symbol}：价格政策、估值审查与事件
          </summary>
          <p>
            当前证据：研究截至{" "}
            {item.as_of ?? item.price_action_plan?.valuation_date ?? "未提供"}
            ；估值情景和原件见股票详情。
          </p>
          {item.symbol && <PolicyReadiness symbol={item.symbol} />}
          <p>
            价格政策：须由本机授权用户明确选择动作条件，预览、二次确认后登记。登记仅保存本人政策，不批准估值，也不产生交易许可。准备状态由详情实时核验，失效日期及研究版本必须匹配。
          </p>
          <p>
            估值审查：由有权研究审核人阅读模型、假设及反证后按现有签署流程批准。材料能否通过不能由页面有估值数值推断；证据不足时先补证，不提供一键代签。
          </p>
          <p>
            重大事件：由有权审核人阅读详情中的公告与材料性问题；如有未决问题，明确签署前保持未准入。新公告、研究变更或政策到期均可能要求重审。
          </p>
          <p>
            操作后影响：只改变相应的政策或审核记录；当前正式资格仍由独立研究、行情与风险条件决定。
          </p>
          <Link to={`/decisions/${encodeURIComponent(item.id)}`}>
            查看材料与价格政策确认入口
          </Link>
        </details>
      ))}
      <details>
        <summary>生产授权与最终使用验收</summary>
        <p>
          本机研究和隔离测试不要求生产授权。部署或调度变更须由系统所有人明确授权；最终产品签收须由你实际使用后确认。当前页面不代签，也不把工程测试当作本人验收。
        </p>
        <p>
          证据：数据状态页与交付验收记录。准备状态：工程检查与本人实际体验独立；版本或使用范围变化时重新确认。此处仅说明边界，不执行生产操作。
        </p>
        <Link to="/system">查看数据与系统状态</Link>
      </details>
    </section>
  );
}
