import {
  ProForm,
  ProFormText,
  ProFormTextArea,
} from "@ant-design/pro-components";
import { Alert, Checkbox } from "antd";
import dayjs from "dayjs";
import { useEffect, useRef, useState } from "react";
import { reusableCostFields, retryableWrite } from "./PrivateRiskContext";

const labels = [
  "买入费用比率（0 到 1）",
  "卖出费用比率（0 到 1）",
  "最低买入费用（元）",
  "最低卖出费用（元）",
];

export function CostAssumptionsPanel({
  revision,
  onConfirm,
  onDone,
}: {
  revision: number;
  onConfirm: (
    body: Record<string, unknown>,
  ) => Promise<{ action: "no_order"; status: string }>;
  onDone: () => void;
}) {
  const [acknowledged, setAcknowledged] = useState(false);
  const [message, setMessage] = useState<string>();
  const lock = useRef(false);
  const attempt = useRef(retryableWrite());
  useEffect(() => {
    setAcknowledged(false);
    attempt.current.clear();
    setMessage(undefined);
  }, [revision]);
  return (
    <details>
      <summary>确认可复用成本设定</summary>
      <Alert
        type="info"
        message="仅保存本人确认的四项费用；滑点和跳空压力需每次明确设定"
      />
      <ProForm
        key={revision}
        layout="vertical"
        onValuesChange={() => {
          setAcknowledged(false);
          setMessage(undefined);
        }}
        submitter={{
          resetButtonProps: false,
          searchConfig: { submitText: "本人确认并保存成本" },
          submitButtonProps: { disabled: !acknowledged },
        }}
        onFinish={async (form: Record<string, unknown>) => {
          if (!acknowledged || lock.current) return false;
          lock.current = true;
          setMessage(undefined);
          const costs = Object.fromEntries(
            reusableCostFields.map((key) => [
              key,
              String(form[key] ?? "").trim(),
            ]),
          );
          const identity = JSON.stringify([
            revision,
            costs,
            form.valid_until,
            form.confirmation_note,
          ]);
          const body = attempt.current.body(identity, () => ({
            idempotency_key: crypto.randomUUID(),
            expected_revision: revision,
            acknowledged: true,
            costs,
            confirmed_at: dayjs().format("YYYY-MM-DDTHH:mm:ssZ"),
            valid_until: String(form.valid_until ?? ""),
            confirmation_note: String(form.confirmation_note ?? "").trim(),
          }));
          try {
            const response = await onConfirm(body);
            if (
              response.action !== "no_order" ||
              response.status !== "COST_ASSUMPTIONS_CONFIRMED"
            )
              throw new Error("成本保存状态无法核验，请刷新检查");
            attempt.current.clear();
            setAcknowledged(false);
            setMessage("成本已确认保存，请重新读取风险条件");
            onDone();
            return true;
          } catch (cause) {
            setMessage(
              cause instanceof Error ? cause.message : "保存失败，请重试",
            );
            return false;
          } finally {
            lock.current = false;
          }
        }}
      >
        {reusableCostFields.map((key, index) => (
          <ProFormText
            key={key}
            name={key}
            label={labels[index]}
            rules={[
              { required: true, message: "未知请勿保存" },
              { pattern: /^\d+(\.\d+)?$/, message: "填写非负数字" },
              {
                validator: async (_, value) => {
                  if (value && key.endsWith("fraction") && Number(value) > 1)
                    throw new Error("比率不可超过 1");
                },
              },
            ]}
          />
        ))}
        <ProFormText
          name="valid_until"
          label="有效截止时间（含时区）"
          placeholder="例如 2026-12-31T23:59:59+08:00"
          rules={[{ required: true }]}
        />
        <ProFormTextArea
          name="confirmation_note"
          label="本人确认依据与适用范围"
          rules={[{ required: true, whitespace: true }]}
        />
        <Checkbox
          checked={acknowledged}
          onChange={(event) => setAcknowledged(event.target.checked)}
        >
          本人已核对费用口径及有效期，允许在本账户后续试算复用
        </Checkbox>
      </ProForm>
      {message && <Alert type="info" message={message} />}
    </details>
  );
}
