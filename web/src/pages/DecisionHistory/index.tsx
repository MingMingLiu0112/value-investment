import { Typography, Alert } from "antd";
import { Workbench } from "../../components/Workbench";
import { RemoteState } from "../../components/RemoteState";
import { DecisionTable } from "../../components/DecisionTable";
import { useApi } from "../../hooks/useApi";
import { api } from "../../services/api";

export default function DecisionHistory() {
  const { data, loading, error, retry } = useApi(api.history);
  return (
    <Workbench>
      <Typography.Title level={2}>历史判断</Typography.Title>
      <RemoteState loading={loading} error={error} retry={retry}>
        {data && (
          <>
            {data.status !== "OK" && (
              <Alert
                type="info"
                showIcon
                message={`历史数据状态：${data.status}`}
              />
            )}
            <DecisionTable
              title="决策记录"
              items={data.items}
              empty="暂无历史判断记录"
            />
          </>
        )}
      </RemoteState>
    </Workbench>
  );
}
