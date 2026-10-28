import { Layout, Menu, Typography } from "antd";
import { Link, useLocation } from "@umijs/max";
import type { PropsWithChildren } from "react";
import "./workbench.css";

const items = [
  { key: "/daily", label: <Link to="/daily">今日决策</Link> },
  { key: "/portfolio", label: <Link to="/portfolio">我的持仓</Link> },
  { key: "/history", label: <Link to="/history">交易复盘</Link> },
  { key: "/alerts", label: <Link to="/alerts">提醒与待办</Link> },
  { key: "/project", label: <Link to="/project">架构与进度</Link> },
  {
    key: "/confirmations",
    label: <Link to="/daily#confirmations">需要我确认</Link>,
  },
];
export function Workbench({ children }: PropsWithChildren) {
  const location = useLocation();
  return (
    <Layout style={{ minHeight: "100vh", background: "#f8faf9" }}>
      <Layout.Header
        className="workbench-header"
        style={{
          background: "#fff",
          borderBottom: "1px solid #e7eaeb",
          display: "flex",
          alignItems: "center",
          gap: 20,
          padding: "0 20px",
        }}
      >
        <Typography.Text strong style={{ fontSize: 17, whiteSpace: "nowrap" }}>
          投资决策工作台
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
        <Link className="workbench-system" to="/system">
          数据状态
        </Link>
      </Layout.Header>
      <Layout.Content
        style={{
          width: "min(1380px, 100%)",
          margin: "0 auto",
          padding: "22px 18px",
        }}
      >
        {children}
      </Layout.Content>
    </Layout>
  );
}
