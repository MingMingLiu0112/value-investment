import { Link, useLocation } from "@umijs/max";
import type { PropsWithChildren } from "react";
import "./workbench.css";

const groups = [
  {
    title: "投资研究",
    links: [
      ["/daily", "今日决策"],
      ["/strategy/value", "价值策略"],
      ["/strategy/hotspot", "热点策略"],
    ],
  },
  {
    title: "持仓与复核",
    links: [
      ["/portfolio", "我的持仓"],
      ["/history", "交易复盘"],
      ["/alerts", "提醒与待办"],
      ["/daily#confirmations", "需要我确认"],
    ],
  },
  {
    title: "系统",
    links: [
      ["/project", "模块与运行"],
      ["/system", "数据状态"],
    ],
  },
];

export function Workbench({ children }: PropsWithChildren) {
  const { pathname, search, hash } = useLocation();
  const strategy = new URLSearchParams(search).get("strategy");
  const section = pathname.startsWith("/decisions/")
    ? strategy === "value"
      ? "/strategy/value"
      : strategy === "hotspot"
        ? "/strategy/hotspot"
        : "/daily"
    : pathname +
      (pathname === "/daily" && hash === "#confirmations" ? hash : "");

  return (
    <div className="workbench-shell">
      <aside className="workbench-sidebar">
        <Link className="workbench-brand" to="/daily">
          <span aria-hidden="true">研</span>
          投资研究工作台
        </Link>
        <nav aria-label="工作台主导航" className="workbench-nav">
          {groups.map((group) => (
            <div className="workbench-nav-group" key={group.title}>
              <p>{group.title}</p>
              {group.links.map(([href, name]) => (
                <Link
                  key={href}
                  to={href}
                  aria-current={section === href ? "page" : undefined}
                >
                  {name}
                </Link>
              ))}
            </div>
          ))}
        </nav>
      </aside>
      <main className="workbench-content">{children}</main>
    </div>
  );
}
