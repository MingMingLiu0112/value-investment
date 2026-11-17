import type { PolicyHandoff } from "../services/valuePolicy";
import { economicMaterialsMatch } from "../services/valuePolicy";
import { AccountingBridgeReview } from "./AccountingBridgeReview";
import { JointCapitalReview } from "./JointCapitalReview";

const titles: Record<string, string> = {
  EARNINGS: "可持续盈利",
  DURATION: "竞争优势与衰减",
  DISTRIBUTION: "现金分配能力",
  COST_TERMINAL: "权益成本与终值",
  EVENT_MODEL: "事件与模型有效性",
};

function Statements({ title, values }: { title: string; values: string[] }) {
  return (
    <div>
      <h5>{title}</h5>
      {values.length ? (
        <ul>
          {values.map((text, index) => (
            <li key={index}>{text}</li>
          ))}
        </ul>
      ) : (
        <p>本版未提供，仍待补证与判断。</p>
      )}
    </div>
  );
}

export function EconomicReviewMaterials({
  handoff,
  symbol,
}: {
  handoff: PolicyHandoff;
  symbol: string;
}) {
  if (
    handoff.status !== "EXTERNAL_SIGNATURE_REQUIRED" ||
    !handoff.economic_review_materials
  )
    return null;
  if (!economicMaterialsMatch(handoff, symbol))
    return (
      <p role="alert">
        经济审核材料与当前公司、候选或模型版本不匹配，暂不展示；请重新读取。
      </p>
    );
  const material = handoff.economic_review_materials;
  return (
    <section
      aria-label="经济判断审核材料"
      style={{ minWidth: 0, maxWidth: "100%", overflowWrap: "anywhere" }}
    >
      <h4>经济判断审核材料</h4>
      <p>
        已核验的范围仅限留存来源与算术关系；下列经济假设仍待独立判断。读取、下载不改变批准状态。
      </p>
      {material.status === "STRESS_ONLY_NOT_PRIMARY" ? (
        <p role="alert">
          当前为压力情景，不能充当中性主估值，也不能据此形成买入或加仓依据。
        </p>
      ) : (
        <p>当前主估值尚不可用，竞争优势、正常化盈利与分配能力仍待审核。</p>
      )}
      <AccountingBridgeReview
        review={material.economic_assessment.accounting_bridge_review}
        symbol={symbol}
        descriptor={material.input_descriptor_sha256}
      />
      <JointCapitalReview handoff={handoff} symbol={symbol} />
      {material.groups.map((group) => (
        <details key={group.id}>
          <summary>{titles[group.id] ?? group.title}</summary>
          <Statements
            title="来源与算术核验观察（非经济批准）"
            values={group.verified_observations}
          />
          <Statements
            title="当前条件假设（未获批准）"
            values={group.conditional_assumptions}
          />
          <Statements title="反证与冲突" values={group.counter_evidence} />
          <Statements
            title="需要审核人回答的问题"
            values={group.judgment_questions}
          />
          <details>
            <summary>字段范围与出处版本</summary>
            <ul>
              {group.field_paths.map((path, index) => (
                <li key={index}>
                  <code>{path}</code>
                </li>
              ))}
            </ul>
            {group.evidence_refs.length ? (
              <ul>
                {group.evidence_refs.map((ref, index) => (
                  <li key={index}>
                    <code>{ref.path}</code>
                    <br />
                    <code>SHA-256 {ref.sha256}</code>
                  </li>
                ))}
              </ul>
            ) : (
              <p>本组尚未提供独立出处。</p>
            )}
          </details>
        </details>
      ))}
      {!material.groups.length && (
        <p>当前候选未提供分组问题，不从其他候选补入。</p>
      )}
      <details>
        <summary>本次材料精确版本</summary>
        <p>
          候选：<code>{material.candidate_binding.path}</code>
        </p>
        <p>
          候选 SHA-256：<code>{material.candidate_binding.sha256}</code>
        </p>
        <p>
          输入：<code>{material.input_descriptor_sha256}</code>
        </p>
        <p>
          估值产物：<code>{material.valuation_artifact_sha256}</code>
        </p>
        <p>
          经济评估：<code>{material.assessment_sha256}</code>
        </p>
        <p>
          审核材料：<code>{material.materials_sha256}</code>
        </p>
      </details>
    </section>
  );
}
