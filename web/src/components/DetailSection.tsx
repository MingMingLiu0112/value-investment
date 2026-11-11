import { Alert, List, Typography } from "antd";

const PREVIEW_LINES = 8;

export function leaves(value: unknown): string[] {
  if (value === null || value === undefined) return [];
  if (typeof value === "string") return value.trim() ? [value.trim()] : [];
  if (typeof value === "number" || typeof value === "boolean")
    return [String(value)];
  if (Array.isArray(value)) return value.flatMap(leaves);
  if (typeof value === "object") {
    const lines: string[] = [];
    for (const [key, item] of Object.entries(
      value as Record<string, unknown>,
    )) {
      if (item === null || item === undefined) {
        lines.push(`${key}：未提供`);
        continue;
      }
      const inner = leaves(item);
      if (!inner.length) continue;
      if (inner.length === 1) lines.push(`${key}：${inner[0]}`);
      else lines.push(`${key}：`, ...inner.map((line) => `・${line}`));
    }
    return lines;
  }
  return [];
}

export function DetailSection({
  title,
  value,
}: {
  title: string;
  value: unknown;
}) {
  const lines = leaves(value);
  if (!lines.length)
    return (
      <section style={{ marginTop: 24 }}>
        <Typography.Title level={4} style={{ fontSize: 16 }}>
          {title}
        </Typography.Title>
        <Alert
          type="info"
          showIcon
          message={`${title}：后端尚未提供可核验内容`}
        />
      </section>
    );
  const preview = lines.slice(0, PREVIEW_LINES);
  const rest = lines.slice(PREVIEW_LINES);
  return (
    <section style={{ marginTop: 24 }}>
      <Typography.Title level={4} style={{ fontSize: 16 }}>
        {title}
      </Typography.Title>
      <List
        size="small"
        bordered
        dataSource={preview}
        renderItem={(entry) => (
          <List.Item style={{ overflowWrap: "anywhere" }}>{entry}</List.Item>
        )}
      />
      {rest.length > 0 && (
        <details style={{ marginTop: 8 }}>
          <summary style={{ cursor: "pointer" }}>
            其余 {rest.length} 条依据
          </summary>
          <List
            size="small"
            bordered
            style={{ marginTop: 8 }}
            dataSource={rest}
            renderItem={(entry) => (
              <List.Item style={{ overflowWrap: "anywhere" }}>
                {entry}
              </List.Item>
            )}
          />
        </details>
      )}
      <details style={{ marginTop: 8 }}>
        <summary style={{ cursor: "pointer" }}>原始数据（可追溯）</summary>
        <pre
          style={{
            marginTop: 8,
            maxHeight: 320,
            overflow: "auto",
            fontSize: 12,
            lineHeight: 1.5,
            whiteSpace: "pre-wrap",
            wordBreak: "break-all",
          }}
        >
          {JSON.stringify(value, null, 2)}
        </pre>
      </details>
    </section>
  );
}
