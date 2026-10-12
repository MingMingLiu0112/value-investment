import { Layout, Menu, Typography } from "antd";
import { Link, useLocation } from "@umijs/max";
import type { PropsWithChildren } from "react";

const items = [
  { key: "/daily", label: <Link to="/daily">每日建议</Link> },
  { key: "/portfolio", label: <Link to="/portfolio">我的持仓</Link> },
  { key: "/history", label: <Link to="/history">历史判断</Link> },
];
export function Workbench({ children }: PropsWithChildren) {
  const location = useLocation();
  return (
    <Layout style={{ minHeight: "100vh", background: "#f5f7f8" }}>
      <Layout.Header
        style={{
          background: "#fff",
          borderBottom: "1px solid #e7eaeb",
          display: "flex",
          alignItems: "center",
          gap: 28,
          padding: "0 24px",
        }}
      >
        <Typography.Text strong style={{ fontSize: 17, whiteSpace: "nowrap" }}>
          双策略投资助手
        </Typography.Text>
        <Menu
          mode="horizontal"
          selectedKeys={[
            location.pathname.startsWith("/decisions/")
              ? "/daily"
              : location.pathname,
          ]}
          items={items}
          style={{ flex: 1, minWidth: 0 }}
        />
      </Layout.Header>
      <Layout.Content
        style={{
          width: "min(1200px, 100%)",
          margin: "0 auto",
          padding: "24px 16px",
        }}
      >
        {children}
      </Layout.Content>
    </Layout>
  );
}
