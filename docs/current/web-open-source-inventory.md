# WEB-D1 open-source inventory

Reviewed 2026-10-12 against upstream repositories. Versions actually installed
are determined by `web/package-lock.json` and the local Python environment.

| Project | License | Decision |
| --- | --- | --- |
| [Ant Design Pro](https://github.com/ant-design/ant-design-pro) | MIT | Umi Max project pattern and layout; trim example administration pages. No wholesale repository copy. |
| [Pro Components](https://github.com/ant-design/pro-components) | MIT | Use its maintained table, detail and form components rather than recreating controls. |
| [FastAPI](https://github.com/fastapi/fastapi) | MIT | Optional Python Web dependency for a thin versioned API. |
| [Lightweight Charts](https://github.com/tradingview/lightweight-charts) | Apache-2.0 | Only for source-dated bars; retain attribution when enabled. No fabricated current chart. |
| [Apache ECharts](https://github.com/apache/echarts) | Apache-2.0 | Portfolio/market charts only when admitted data exists. |
| [TradingAgents](https://github.com/TauricResearch/TradingAgents) | Apache-2.0 | Research-role inspiration only; no imported trading framework. |
| [Ghostfolio](https://github.com/ghostfolio/ghostfolio) | AGPL-3.0 | UX reference only; no source copied or backend imported. |

The UI layer does not introduce a second research, valuation, or portfolio ledger.
Upstream maintenance and transitive dependencies must be rechecked on upgrades.
