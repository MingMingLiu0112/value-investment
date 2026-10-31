import { Alert, Button, Spin } from "antd";
import type { PropsWithChildren } from "react";

export function RemoteState({
  loading,
  error,
  retry,
  children,
}: PropsWithChildren<{ loading: boolean; error?: string; retry: () => void }>) {
  if (loading)
    return (
      <div style={{ padding: 40, textAlign: "center" }}>
        <Spin tip="正在读取研究数据" />
      </div>
    );
  if (error)
    return (
      <Alert
        type="error"
        showIcon
        message={error}
        action={<Button onClick={retry}>重试</Button>}
      />
    );
  return <>{children}</>;
}
