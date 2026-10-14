import {
  ProForm,
  ProFormDatePicker,
  ProFormList,
  ProFormSelect,
  ProFormText,
  ProFormTextArea,
} from "@ant-design/pro-components";
import {
  Alert,
  Button,
  Checkbox,
  Descriptions,
  Input,
  Space,
  Typography,
} from "antd";
import dayjs from "dayjs";
import { useApi } from "../hooks/useApi";
import { useEffect, useState } from "react";
import { ApiError, api } from "../services/api";
import {
  missingPolicyInputs,
  policyAmountFields,
  policyBooleanFields,
  policyConfirmationBody,
  policyFieldLabel,
  policyFormValues,
  policyFromForm,
  policyPercentFields,
  policyReviewRows,
  policySleeves,
} from "../utils/portfolioPolicy";
import { RemoteState } from "./RemoteState";
import { sleeveLabel } from "./PositionTable";

function failureText(cause: unknown) {
  if (cause instanceof ApiError)
    return `${cause.code}：${String(cause.detail ?? "")}`;
  return cause instanceof Error ? cause.message : "IPS 操作未完成";
}

export function PortfolioPolicyPanel({
  revision,
  fillPending,
  onDone,
}: {
  revision: number;
  fillPending: boolean;
  onDone: () => void;
}) {
  const result = useApi(api.policy);
  const [failure, setFailure] = useState<string>();
  const [notice, setNotice] = useState<string>();
  const [note, setNote] = useState("");
  const [acknowledged, setAcknowledged] = useState(false);
  const [busy, setBusy] = useState(false);
  const data = result.data;
  const draft = data?.pending_policy;
  const sameRevision = data?.revision === revision;
  const missing = draft
    ? (draft.missing_fields ?? missingPolicyInputs(draft.policy))
    : [];
  useEffect(() => {
    setAcknowledged(false);
    setNote("");
  }, [draft?.prepared_record_sha256, data?.revision]);
  const refresh = () => {
    result.retry();
    onDone();
  };

  const save = async (form: Record<string, unknown>) => {
    setFailure(undefined);
    setNotice(undefined);
    if (!sameRevision || fillPending) return false;
    try {
      const response = await api.preparePolicy({
        idempotency_key: crypto.randomUUID(),
        expected_revision: revision,
        policy: policyFromForm(form),
      });
      if (response.status !== "POLICY_PREPARED")
        throw new Error("草稿保存状态未核验，请刷新台账。");
      setNotice("IPS 草稿已保存，尚未确认，不改变持仓或个人操作资格。");
      setAcknowledged(false);
      setNote("");
      refresh();
      return true;
    } catch (cause) {
      setFailure(failureText(cause));
      return false;
    }
  };

  const confirm = async () => {
    if (!draft || !sameRevision || fillPending || missing.length) return;
    setBusy(true);
    setFailure(undefined);
    try {
      const response = await api.confirmPolicy({
        idempotency_key: crypto.randomUUID(),
        ...policyConfirmationBody(
          revision,
          draft.prepared_record_sha256,
          note,
          acknowledged,
          dayjs().format("YYYY-MM-DDTHH:mm:ssZ"),
        ),
      });
      if (response.status !== "POLICY_CONFIRMED")
        throw new Error("确认状态未核验，请刷新台账。");
      setNotice("IPS 已由本人确认；个人资格仍以证券门禁与风险复核结果为准。");
      setAcknowledged(false);
      setNote("");
      refresh();
    } catch (cause) {
      setFailure(failureText(cause));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section aria-label="投资政策与分池风险">
      <Typography.Title level={4} style={{ fontSize: 16, marginTop: 24 }}>
        投资政策与分池风险（IPS）
      </Typography.Title>
      <RemoteState
        loading={result.loading}
        error={result.error}
        retry={result.retry}
      >
        {data && (
          <>
            <Alert
              type="info"
              showIcon
              message={
                data.status === "CONFIRMED"
                  ? "已有人工确认的 IPS"
                  : "IPS 尚未确认"
              }
              description="草稿不会启用个人仓位建议。证券风险属性、行情和独立门禁缺失时仍保留阻塞；系统不下单。"
            />
            {failure && (
              <Alert
                type="error"
                showIcon
                message="IPS 操作未完成"
                description={failure}
              />
            )}
            {notice && <Alert type="info" showIcon message={notice} />}
            {!sameRevision && (
              <Alert
                type="warning"
                message="IPS 与台账版本不一致，已停止保存和确认"
                action={<Button onClick={refresh}>刷新</Button>}
              />
            )}
            {fillPending && (
              <Alert
                type="warning"
                message="请先确认或作废已有成交草稿，再修改 IPS"
              />
            )}
            {data.status === "CONFIRMED" && data.policy && (
              <details style={{ marginTop: 12 }}>
                <summary>已确认的投资政策</summary>
                <Descriptions
                  column={1}
                  size="small"
                  items={policyReviewRows(data.policy).map((row) => ({
                    ...row,
                    children: row.value,
                  }))}
                />
              </details>
            )}
            {draft && (
              <div style={{ marginTop: 16 }}>
                <Typography.Title level={5}>待确认 IPS 草稿</Typography.Title>
                <Descriptions
                  column={1}
                  size="small"
                  items={policyReviewRows(draft.policy).map((row) => ({
                    ...row,
                    children: row.value,
                  }))}
                />
                {!!missing.length && (
                  <Alert
                    type="warning"
                    message="草稿尚不完整，可继续编辑保存"
                    description={missing.map(policyFieldLabel).join("；")}
                  />
                )}
                <Typography.Text
                  type="secondary"
                  style={{ overflowWrap: "anywhere" }}
                >
                  草稿绑定：{draft.prepared_record_sha256}；台账修订{" "}
                  {data.revision}
                </Typography.Text>
                <div style={{ marginTop: 12 }}>
                  <Checkbox
                    checked={acknowledged}
                    onChange={(event) => setAcknowledged(event.target.checked)}
                  >
                    本人已逐项核对上述预算、现金分配、风险选择及生效日期
                  </Checkbox>
                </div>
                <Input.TextArea
                  aria-label="IPS 本人确认说明"
                  placeholder="本人确认说明"
                  value={note}
                  onChange={(event) => setNote(event.target.value)}
                  style={{ marginTop: 8 }}
                />
                <Button
                  type="primary"
                  loading={busy}
                  disabled={
                    !sameRevision ||
                    fillPending ||
                    !!missing.length ||
                    !acknowledged ||
                    !note.trim()
                  }
                  onClick={confirm}
                  style={{ marginTop: 8 }}
                >
                  本人确认 IPS 草稿
                </Button>
              </div>
            )}
            <details
              style={{ marginTop: 16 }}
              open={!draft && data.status !== "CONFIRMED"}
            >
              <summary>{draft ? "修改草稿" : "填写或更新投资政策"}</summary>
              <ProForm
                key={`${data.revision}-${draft?.prepared_record_sha256 ?? "new"}`}
                layout="vertical"
                initialValues={policyFormValues(
                  draft?.policy ?? data.policy ?? {},
                )}
                onFinish={save}
                disabled={!sameRevision || fillPending || busy}
                submitter={{
                  resetButtonProps: false,
                  searchConfig: { submitText: "保存 IPS 草稿" },
                }}
              >
                <ProForm.Group>
                  {policyAmountFields.map(([name, label]) => (
                    <ProFormText
                      key={name}
                      name={name}
                      label={label}
                      width="md"
                      rules={[
                        {
                          pattern: /^\d+(\.\d{1,4})?$/,
                          message: "填写非负数字",
                        },
                      ]}
                    />
                  ))}
                  {policyPercentFields.map(([name, label]) => (
                    <ProFormText
                      key={name}
                      name={name}
                      label={label}
                      width="md"
                      rules={[
                        {
                          pattern: /^\d+(\.\d{1,4})?$/,
                          message: "填写非负百分数",
                        },
                        {
                          validator: async (_, value) => {
                            if (value && Number(value) > 100)
                              throw new Error("百分数不可超过 100");
                          },
                        },
                      ]}
                    />
                  ))}
                  {policyBooleanFields.map(([name, label]) => (
                    <ProFormSelect
                      key={name}
                      name={name}
                      label={label}
                      width="md"
                      options={[
                        { value: "ALLOW", label: "允许" },
                        { value: "DENY", label: "不允许" },
                      ]}
                    />
                  ))}
                  <ProFormSelect
                    name="risk_tolerance"
                    label="风险偏好"
                    width="md"
                    options={[
                      { value: "CONSERVATIVE", label: "保守" },
                      { value: "BALANCED", label: "均衡" },
                      { value: "GROWTH", label: "成长" },
                    ]}
                  />
                  <ProFormDatePicker
                    name="effective_date"
                    label="生效日期"
                    width="md"
                  />
                  <ProFormText
                    name="tax_regime"
                    label="税务口径（可选）"
                    width="md"
                  />
                </ProForm.Group>
                {policySleeves.map((sleeve) => (
                  <div key={sleeve}>
                    <Typography.Title level={5}>
                      {sleeveLabel(sleeve)}
                    </Typography.Title>
                    <ProForm.Group>
                      {[
                        "cash_cny",
                        "risk_budget_cny",
                        ...(sleeve === "HOTSPOT_SATELLITE"
                          ? ["single_security_risk_cny"]
                          : []),
                      ].map((field) => (
                        <ProFormText
                          key={field}
                          name={["sleeves", sleeve, field]}
                          label={policyFieldLabel(`sleeves.${sleeve}.${field}`)}
                          width="md"
                          rules={[
                            {
                              pattern: /^\d+(\.\d{1,4})?$/,
                              message: "填写非负数字",
                            },
                          ]}
                        />
                      ))}
                    </ProForm.Group>
                  </div>
                ))}
                <ProFormTextArea
                  name="restrictions"
                  label="其他约束（可选，每项一行）"
                />
                <ProFormList
                  name="security_bindings"
                  label="证券风险属性来源（未核验可留空）"
                  copyIconProps={false}
                  creatorButtonProps={{ creatorButtonText: "添加已核验来源" }}
                >
                  <Space direction="vertical" style={{ width: "100%" }}>
                    <ProFormText
                      name="symbol"
                      label="证券代码"
                      rules={[{ pattern: /^\d{6}$/, message: "六位证券代码" }]}
                    />
                    <ProFormText name="path" label="风险属性证据路径" />
                    <ProFormText
                      name="sha256"
                      label="证据 SHA256"
                      rules={[
                        {
                          pattern: /^[a-f0-9]{64}$/,
                          message: "64 位小写 SHA256",
                        },
                      ]}
                    />
                  </Space>
                </ProFormList>
              </ProForm>
            </details>
          </>
        )}
      </RemoteState>
    </section>
  );
}
