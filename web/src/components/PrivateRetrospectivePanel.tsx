import { useCallback, useState } from "react";
import { Alert, Select } from "antd";
import { api } from "../services/api";
import type { PrivateRetrospective } from "../services/api";
import { useApi } from "../hooks/useApi";
import { RemoteState } from "./RemoteState";
import type { PortfolioTrade, RecordingTimeRiskEvidence } from "../types/api";
import { describeCode } from "../utils/codes";

function recordingRiskStatus(value?: string | null) {
  const text = describeCode(value);
  return value && text === value ? "状态未识别" : text;
}

const gapLabels: Record<string, string> = {
  TRADE_TIME_PLAN_AND_DATA_AVAILABILITY_NOT_PROVEN:
    "尚不能证明实际成交前已知该计划与数据",
  PERSONAL_RISK_AT_TRADE_NOT_PROVEN: "成交时的个人风险未追溯核验",
  RECORDING_TIME_PERSONAL_RISK_MISSING: "未保留可核验的录入时个人风险",
  RECORDING_TIME_PERSONAL_RISK_INVALID: "录入时个人风险留存校验未通过",
  DEVIATION_REASON_NOT_RECORDED: "未记录偏离计划的原因",
  SUBSEQUENT_RISK_NOT_EVALUATED_NO_LATER_EVIDENCE: "缺少后续风险证据",
  SAVED_JUDGMENT_MISSING: "没有录入时判断快照",
  SAVED_JUDGMENT_INVALID_OR_MISMATCHED: "原判断快照校验未通过",
  UNLINKED_FILL_NO_RESEARCH_APPROVAL_INFERRED:
    "成交未关联研究，不推断其已获批准",
};

function Review({ day }: { day: string }) {
  const load = useCallback(
    (signal: AbortSignal) => api.privateRetrospective(day, signal),
    [day],
  );
  const { data, loading, error, retry } = useApi(load);
  const items: (PrivateRetrospective["items"][number] &
    RecordingTimeRiskEvidence)[] = data?.items ?? [];
  if (!loading && !error && data?.status === "BLOCKED_PRIVATE_INPUT") {
    return (
      <Alert
        type="warning"
        message="私人台账尚不可用，无法复盘"
        description="没有读取到已确认台账，不能据此判断当天是否成交。"
      />
    );
  }
  return (
    <RemoteState loading={loading} error={error} retry={retry}>
      <Alert
        type="info"
        message="Mock 复盘草稿，非模型实测结论"
        description={
          data?.ledger_source === "TEST_ONLY"
            ? "TEST_ONLY 隔离台账。参考价差不代表收益优势或交易违规。"
            : "依据本人确认的台账，未经券商核实；参考价差不证明交易违规。"
        }
      />
      {items.map((item) => (
        <section key={item.manual_fill.transaction_id}>
          <h4>
            {item.manual_fill.symbol} ·{" "}
            {item.manual_fill.side === "BUY" ? "买入" : "卖出"}{" "}
            {item.manual_fill.quantity} 股 · {item.manual_fill.price_cny} 元
          </h4>
          <p>
            录入时风险：
            {item.recording_time_risk_status ===
              "AVAILABLE_RECORDING_TIME_ONLY" &&
            item.recording_time_personal_risk?.status ===
              "SERVER_VERIFIED_RECORDING_TIME_RISK" ? (
              <>
                已保留；原风险状态：
                {recordingRiskStatus(
                  item.recording_time_personal_risk.risk_status,
                )}
                ；当时复核股数：
                {item.recording_time_personal_risk.review_quantity ?? "未提供"}
              </>
            ) : (
              "未保留可核验结果"
            )}
            。仅为录入时留存，不能证明成交前已核验。
          </p>
          {item.differences.map((difference) => (
            <p key={difference.field}>
              {(
                {
                  entry_trigger_price: "入场参考",
                  invalidation_price: "失效参考",
                  stop_price: "保护参考",
                  exit_trigger_price: "退出参考",
                  profit_review_price: "止盈复核参考",
                } as Record<string, string>
              )[difference.field] || "原计划参考"}{" "}
              {difference.saved_reference_cny} 元；成交价差{" "}
              {difference.fill_minus_reference_cny} 元
            </p>
          ))}
          <ul>
            {item.evidence_gaps.map((gap) => (
              <li key={gap}>{gapLabels[gap] || "保存的参考价需要重新核验"}</li>
            ))}
          </ul>
        </section>
      ))}
      {data?.status === "NO_CONFIRMED_FILLS" && (
        <p>该日没有已确认成交可供复盘。</p>
      )}
      {!!data?.unprocessed_trade_count && (
        <p>还有 {data.unprocessed_trade_count} 笔未纳入本次有界复盘。</p>
      )}
    </RemoteState>
  );
}

export function PrivateRetrospectivePanel({
  trades,
}: {
  trades: PortfolioTrade[];
}) {
  const days = [...new Set(trades.map((trade) => trade.trade_date))]
    .sort()
    .reverse();
  const [selected, setSelected] = useState<string>();
  const day = selected && days.includes(selected) ? selected : days[0];
  if (!day) return null;
  return (
    <details style={{ marginTop: 16 }}>
      <summary>成交复盘草稿</summary>
      <Select
        aria-label="复盘成交日"
        value={day}
        onChange={setSelected}
        options={days.map((value) => ({ value, label: value }))}
        style={{ width: 160, marginBlock: 12 }}
      />
      <Review key={`${day}:${trades.length}`} day={day} />
    </details>
  );
}
