import { Link } from "@umijs/max";
import { Button, Descriptions, Skeleton, Typography } from "antd";
import { Workbench } from "../../components/Workbench";
import { useApi } from "../../hooks/useApi";
import { api } from "../../services/api";
import { describeCode } from "../../utils/codes";

export default function SystemStatus() {
  const { data, loading, error, retry } = useApi(api.packet);
  return (
    <Workbench>
      <Typography.Title level={2}>数据与系统状态</Typography.Title>
      <Typography.Paragraph type="secondary">
        研究依据与发布时间在这里核对，不等于买卖准入。
      </Typography.Paragraph>
      {loading && <Skeleton active />}
      {error && (
        <p role="alert">
          读取失败：{error} <Button onClick={retry}>重试</Button>
        </p>
      )}
      {data && (
        <>
          <Descriptions
            bordered
            size="small"
            column={{ xs: 1, sm: 2 }}
            items={[
              {
                key: "status",
                label: "发布状态",
                children: data.packet_status,
              },
              {
                key: "id",
                label: "发布版本",
                children: data.publication_id || "未验证",
              },
              {
                key: "research",
                label: "研究截至",
                children: data.dates.research_as_of || "未验证",
              },
              {
                key: "quote",
                label: "行情日期",
                children: data.dates.quote_trade_date || "未验证",
              },
              {
                key: "model",
                label: "模型有效性",
                children: data.dates.model_validity.status,
              },
              {
                key: "source",
                label: "来源校验",
                children: data.source_bindings_verified
                  ? "来源哈希匹配；不等于投资批准"
                  : "未通过或未完成",
              },
              {
                key: "formal",
                label: "正式准入",
                children: data.formal_admission_count,
              },
              {
                key: "excel",
                label: "Excel 日期",
                children: data.dates.excel_published_as_of || "未验证",
              },
            ]}
          />
          {data.blockers.length > 0 && (
            <section style={{ marginTop: 22 }}>
              <h2 style={{ fontSize: 16 }}>尚需核验</h2>
              <ul>
                {data.blockers.map((code) => (
                  <li key={code}>{describeCode(code)}</li>
                ))}
              </ul>
            </section>
          )}
          <Link to="/daily">返回今日机会</Link>
        </>
      )}
    </Workbench>
  );
}
