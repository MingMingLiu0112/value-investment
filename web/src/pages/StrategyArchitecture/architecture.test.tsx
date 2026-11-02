import React from "react";
import { describe, expect, it, vi } from "vitest";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
const { renderToStaticMarkup } = require("react-dom/server");
vi.mock("@umijs/max", () => ({
  Link: ({ to, children }: any) => <a href={to}>{children}</a>,
  useLocation: () => ({ pathname: "/strategy/value" }),
}));
import {
  catalog,
  review,
  valueVerticalScope,
  valueMainModuleIds,
} from "../../config/strategyArchitecture.v1";
import { ArchitectureView, StageButton, StageDetail } from "./index";
describe("versioned strategy architecture", () => {
  it("separates independently delivered scope from unfinished modules", () => {
    for (const id of valueMainModuleIds) {
      const stage = catalog.value.stages.find((s) => s.id === id)!;
      const review = stage.deliveryReview!;
      expect(review).toBeDefined();
      for (const key of [
        "what",
        "why",
        "how",
        "done",
        "gap",
        "acceptance",
      ] as const)
        expect(review[key].length).toBeGreaterThan(8);
      expect(review.evidence.length).toBeGreaterThan(0);
      const html = renderToStaticMarkup(<StageDetail stage={stage} />);
      expect(html).toContain("模块交付说明");
      expect(html).toContain("完成标准");
      expect(html).not.toContain("<details open=");
    }
    expect(
      catalog.value.stages
        .filter((s) => s.deliveryReview?.status === "COMPLETE")
        .map((s) => s.id),
    ).toEqual(["C", "F1"]);
    expect(
      catalog.value.stages.find((s) => s.id === "C")!.deliveryReview!.scope,
    ).toContain("固定五家");
    expect(
      catalog.value.stages.find((s) => s.id === "F1")!.deliveryReview!.gap,
    ).toContain("不等于当前买价");
  });
  it("pins review separately from disconnected runtime evidence", () => {
    expect(review.baseline).toBe("283c7212d832f52118705bb095e046e0c36dcbfc");
    expect(review.runtimeEvidence).toBe("NOT_CONNECTED");
    expect(catalog.value.stages.find((s) => s.id === "F2")?.evidence).toContain(
      "跨日股本",
    );
  });
  it.each(["value", "hotspot"] as const)(
    "renders %s with stopping branches and existing destinations",
    (key) => {
      const html = renderToStaticMarkup(<ArchitectureView strategy={key} />);
      for (const text of [
        "不是实时进度",
        "资料不足",
        "无法评价",
        "条件不符",
        "不操作",
        "人工复核",
        "共享组合风险",
        "NOT_CONNECTED",
      ])
        expect(html).toContain(text);
      for (const path of ["/daily", "/history", "/system", "/portfolio"])
        expect(html).toContain('href="' + path + '"');
      expect(html.replace("0.10=10%", "")).not.toMatch(
        /\d+%|ant-progress|ant-tag-success/,
      );
      if (key === "value") {
        expect(html).toContain("模块交付进度");
        expect(html).toContain("可独立交付");
      } else {
        expect(html).toContain("工程：");
        expect(html).toContain("证据：");
      }
      expect(catalog[key].stages.length).toBe(key === "value" ? 16 : 8);
      const ids = catalog[key].stages.map((s) => s.id);
      expect(new Set(ids).size).toBe(ids.length);
      for (const [index, stage] of catalog[key].stages.entries()) {
        for (const dep of stage.dependencies) expect(ids).toContain(dep);
        for (const path of stage.modules)
          expect(existsSync(resolve("..", path)), path).toBe(true);
        const detail = renderToStaticMarkup(<StageDetail stage={stage} />);
        for (const text of [
          stage.existingEvidence,
          stage.evidence,
          stage.nextStep,
          stage.ruleWhy,
        ])
          expect(detail).toContain(text);
      }
    },
  );
  it("selects stable IDs through native button activation", () => {
    const select = vi.fn(),
      stage = catalog.hotspot.stages[2];
    const node = StageButton({ stage, selected: false, onSelect: select });
    expect(node.type).toBe("button");
    expect(node.props["aria-controls"]).toBe("architecture-detail");
    node.props.onClick();
    expect(select).toHaveBeenCalledWith("hotspot_validation");
    expect(
      StageButton({ stage, selected: true, onSelect: select }).props[
        "aria-pressed"
      ],
    ).toBe(true);
  });
  it("preserves historical evidence and independent hotspot dependencies", () => {
    const hotspot = JSON.stringify(catalog.hotspot);
    expect(hotspot).toContain("34次历史触发、32次完整五交易日跟踪、2次右删失");
    expect(hotspot).toContain("NOT_PROVEN");
    expect(
      catalog.hotspot.stages
        .flatMap((s) => s.dependencies)
        .some((id) => id.startsWith("value_")),
    ).toBe(false);
    expect(JSON.stringify(catalog.value)).toContain("2026-06-30");
    expect(JSON.stringify(catalog.value)).toContain("非当前买价");
    expect(
      catalog.value.stages.find((s) => s.id === "B")?.channels,
    ).toHaveLength(4);
  });
  it("maps all proposal modules with distinct progress axes and no fake first-company completion", () => {
    expect(catalog.value.stages.map((s) => s.id)).toEqual([
      "A",
      "B",
      "C",
      "D1",
      "D2",
      "E1",
      "E2",
      "F1",
      "F2",
      "G1",
      "G2",
      "S1",
      "S2",
      "S3",
      "S4",
      "W1",
    ]);
    for (const stage of catalog.value.stages) {
      expect(stage.progress?.acceptance).toContain("尚未确认");
      expect(stage.progress?.realData).toBeTruthy();
      expect(stage.progress?.consumer).toBeTruthy();
      expect(stage.progress?.economic).toBeTruthy();
      expect(stage.progress?.deployment).toBeTruthy();
    }
    expect(
      catalog.value.stages.find((s) => s.id === "E2")?.dependencies,
    ).not.toContain("E1");
    expect(
      catalog.value.stages.find((s) => s.id === "E2")?.engineeringStatus,
    ).toBe("工程首编与真实来源重算完成／部署待验收");
    expect(catalog.value.stages.find((s) => s.id === "B")?.evidence).toContain(
      "CONFLICT",
    );
    const html = renderToStaticMarkup(<ArchitectureView strategy="value" />);
    expect(html).toContain("H1–H4");
    expect(html).toContain("无旧估值");
    expect(html).toContain("用户确认");
    expect(html).toContain("目标输出（不代表已实现）");
    expect(html).toContain("不代表共同前置");
    expect(html).toContain("不阻塞公开研究");
    expect(
      catalog.value.stages.find((s) => s.id === "F1")?.dependencies,
    ).not.toContain("E2");
    expect(html).toContain("/decisions/600887?strategy=value");
    expect(html).toContain('href="/project"');
  });
  it("shows C's four independent frozen states in overview and details without graduating downstream inputs", () => {
    const c = catalog.value.stages.find((stage) => stage.id === "C")!;
    for (const html of [renderToStaticMarkup(<StageDetail stage={c} />)]) {
      expect(html).toContain("C模块四轴状态");
      for (const text of [
        "工程闭环完成",
        "固定五家验收通过",
        "部署待验收",
        "用户尚未确认",
      ])
        expect(html).toContain(text);
    }
    const current = renderToStaticMarkup(
      <StageButton stage={c} selected={true} onSelect={() => {}} />,
    );
    expect(current).toContain("可独立交付");
    expect(current).not.toContain("部署待验收");
    expect(c.boundary).toContain("不授予经济、估值或交易资格");
    const detail = renderToStaticMarkup(<StageDetail stage={c} />);
    expect(detail).toContain("已验输入（固定五家范围）");
    expect(detail).toContain("已验输出（固定五家范围）");
    expect(detail).toContain(c.input);
    expect(detail).toContain(c.output);
    for (const id of ["D1", "D2", "E2"]) {
      const stage = catalog.value.stages.find((item) => item.id === id)!;
      expect(stage.engineeringStatus).not.toBe("工程闭环完成");
      const html = renderToStaticMarkup(<StageDetail stage={stage} />);
      expect(html).toContain(stage.input);
      expect(html).toContain(stage.output);
      expect(html).toContain("目标输出（不代表已实现）");
    }
  });
  it("keeps project as module map while the main value route opens the transparent workbench", () => {
    const routes = readFileSync(".umirc.ts", "utf8");
    const component = (path: string) => {
      const declaration = routes
        .split("\n")
        .find((line) => line.includes('path: "' + path + '"'));
      return declaration?.match(/component: "([^"]+)"/)?.[1];
    };
    expect(component("/project")).toBe("./StrategyArchitecture/Value");
    expect(component("/strategy/value")).toBe("./ValueWorkbench");
    const html = renderToStaticMarkup(<ArchitectureView strategy="value" />);
    expect(html).toContain(
      "/project保留模块地图，/strategy/value进入价值研究工作台",
    );
    expect(html).not.toContain("当前工作树没有已接入的/project");
    expect(html).toContain("不因C完成而推定已闭环");
  });
  it("registers both routes and menu entries without transports", () => {
    const routes = readFileSync(".umirc.ts", "utf8"),
      menu = readFileSync("src/components/Workbench.tsx", "utf8");
    for (const path of ["/strategy/value", "/strategy/hotspot"]) {
      expect(routes).toContain(path);
      expect(menu).toContain(path);
    }
    const page = readFileSync(
      "src/pages/StrategyArchitecture/index.tsx",
      "utf8",
    );
    expect(page).not.toMatch(/useApi|fetch\(|services\/|localStorage/);
  });
});

it("records the current driver bridge arithmetic acceptance without adopting parameters, capital cash or valuation", () => {
  const d1 = catalog.value.stages.find((stage) => stage.id === "D1")!;
  const d2 = catalog.value.stages.find((stage) => stage.id === "D2")!;
  for (const stage of [d1, d2]) {
    expect(stage.evidenceSource).toContain(
      "rt-eac1c74997d17510398ce1fe1e5bea9e-recovered.json",
    );
    expect(stage.evidenceSource).toContain("independent-acceptance.json");
    expect(stage.evidenceSource).toContain(
      "artifacts/current/d2-operating-driver-20261101.json",
    );
    expect(stage.evidenceSource).not.toContain("待Root");
    expect(stage.nextStep).toContain(
      "验证参数经济适用性及资本/现金资料，不重试模型凑通过",
    );
    expect(stage.progress?.acceptance).toContain("尚未确认");
  }
  expect(d1.evidenceStatus).toContain("4次调用含1次反证缺字段拒绝后恢复");
  expect(d1.evidenceStatus).toContain("不是今日调用总数");
  expect(d1.evidence).toContain(
    "历史rt-c40任务峰值费率保守估算0.15066元，非账单",
  );
  expect(d1.evidence).toContain("昨日浏览器实际0.158元");
  expect(d1.evidence).toContain("旧估算7.33345元不是实际费用");
  expect(d2.evidenceStatus).toContain(
    "21项经营驱动范围、6项增长/税前利润率由代码派生、9项资本UNKNOWN",
  );
  expect(d2.implementation).toContain("H12026→H12027");
  expect(d2.implementation).toContain("同比FY只对FY、H1只对H1");
  expect(d2.milestone).toContain("3×128角点及12条阈值一致");
  expect(d2.milestone).toContain("等于不触发");
  expect(d2.existingEvidence).toContain("rt-c40经济拒绝保留为历史");
  expect(d2.evidence).toContain("typed bridge不消费这些文字");
  expect(d2.progress?.economic).toContain("参数经济适用性未证");
  const html = renderToStaticMarkup(<ArchitectureView strategy="value" />);
  for (const text of [
    "21项经营驱动范围",
    "9项资本UNKNOWN",
    "条件压力分析算术已验收",
    "0.10=10%",
    "同值不触发",
    "不能混用历史阈值",
    "不等于未来参数已证明、主估值、E2批准、G3或交易",
    "验证参数经济适用性及资本/现金资料，不重试模型凑通过",
  ])
    expect(html).toContain(text);
  expect(html).toContain('href="/decisions/000568?strategy=value"');
  expect(html).toContain("真实Agent研究结果（条件现金/估值已接，待终验）");
  expect(html).not.toContain("首要决定性缺口是经营量价/成本传导与一致性验证");
  expect(
    catalog.value.stages.find((stage) => stage.id === "C")?.progress
      ?.acceptance,
  ).toContain("用户尚未确认");
  expect(
    catalog.value.stages.find((stage) => stage.id === "E2")?.engineeringStatus,
  ).toBe("工程首编与真实来源重算完成／部署待验收");
});

it("separates the actual capital blocker and vertical acceptance from future platform expansion", () => {
  const evidence = JSON.parse(
    readFileSync(resolve("..", valueVerticalScope.evidenceSource), "utf8"),
  );
  expect(evidence.capital_assumptions_unknown).toBe(
    valueVerticalScope.capitalUnknownCount,
  );
  expect(evidence.compile_into_main_valuation).toBe(false);
  expect(evidence.condition_price).toBeNull();
  const cash = JSON.parse(
    readFileSync(resolve("..", valueVerticalScope.cashEvidenceSource), "utf8"),
  );
  expect(cash.actual_results.status).toBe(
    "CONDITIONAL_RESEARCH_CANDIDATE_PENDING_ECONOMIC_REVIEW",
  );
  expect(cash.actual_results.main_range_adopted).toBe(false);
  expect(cash.actual_results.condition_price).toBeNull();
  expect(cash.actual_results.formal_eligibility).toBe(false);
  expect(cash.actual_results.current_comparable).toBe(false);
  expect(cash.actual_results.annual_cash_rows).toBe(30);
  expect(cash.actual_model_receipt.path).toMatch(/^runtime\//);
  const closure = JSON.parse(
    readFileSync(resolve("..", cash.source_closure.path), "utf8"),
  );
  expect(closure.sources.length).toBe(closure.source_count);
  expect(closure.source_count).toBeGreaterThan(0);
  expect(cash.source_spec.path).toContain("source-lf-v2");
  // This is a committed evidence-index contract; actual finance replays run separately.

  const html = renderToStaticMarkup(<ArchitectureView strategy="value" />);
  const focus = html
    .split('aria-label="本轮纵向链与扩展边界"')[1]
    .split('aria-label="业务依赖图"')[0];
  expect(focus).toContain(valueVerticalScope.focus);
  expect(focus).toContain(
    "原9项资本UNKNOWN不因复用来源绑定的条件现金政策而升级为已证",
  );
  expect(focus).toContain("不能补零、未经核验沿用旧假设或重试模型凑通过");
  expect(focus).toContain("经营税前利润不能直接当股东现金");
  expect(focus).toContain("当前不生成买价");
  expect(focus).toContain("公开条件研究不依赖私人持仓解锁");
  const current = focus
    .split('aria-label="当前阻断与后续纵向验收"')[1]
    .split('aria-label="未来扩展非本轮前置"')[0];
  for (const text of [
    "新Q3实际 + 条件Q4 + 条件次年H1",
    "复用既有计算、不复制公式",
    "不再列作计算通道缺失",
    "非机械年化",
    "不得H1×2",
    "不得调整COGS凑利润",
    "税后归属与现金政策（经济采纳待验）",
    "条件估值已消费，主区间未采用",
    "当前资本/分配/事件/报价及价格理由（当前必需）",
    "不冒充本次D2消费",
    "母公司v2义务与准备金实际进入模型",
    "付款年是研究假设",
    "无阈值理由不出条件价",
  ])
    expect(current).toContain(text);
  expect(valueVerticalScope.nextRequired).toHaveLength(4);
  const future = focus.split('aria-label="未来扩展非本轮前置"')[1];
  for (const text of [
    "全市场自动研究",
    "通用企业分类",
    "真实组合",
    "热点通道",
    "非本轮前置",
  ])
    expect(future).toContain(text);
  expect(focus).toContain("不表示需先完成全部模块");
  expect(focus).toContain("本轮正式回执已形成条件研究工作候选");
  expect(focus).toContain("约6.19516/16.85149/27.22284");
  expect(focus).toContain("acceptance-source-lf-v2.json");
  expect(focus).toContain("来源spec2c09f05f及SHA已固定");
  expect(focus).toContain("业务版7537c7a0已在唯一8001完成公司页与API核验");
  expect(focus).toContain("旧全产品刊发注册仍不可用，用户尚未确认");
  expect(focus).toContain("旧9.03/20.26/25.82");
  expect(focus).toContain("不是本轮最新结果");
  expect(focus).toContain("本页仅手工整理真实回执，非自动监测");
  expect(focus).toContain("11,013,375,072.53元");
  expect(focus).not.toContain("二者尚不兼容");
  expect(
    renderToStaticMarkup(<ArchitectureView strategy="hotspot" />),
  ).not.toContain("本轮纵向链与扩展边界");
});

it("separates eleven main nodes and five support nodes while preserving IDs and routes", () => {
  const html = renderToStaticMarkup(<ArchitectureView strategy="value" />);
  expect(html).toContain("价值主链（11个模块）");
  expect(html).toContain("共享支持（5个模块，非公开研究共同前置）");
  expect(catalog.value.stages.slice(0, 11).map((s) => s.id)).toEqual([
    "A",
    "B",
    "C",
    "D1",
    "D2",
    "E1",
    "E2",
    "F1",
    "F2",
    "G1",
    "G2",
  ]);
  expect(catalog.value.stages.slice(11).map((s) => s.id)).toEqual([
    "S1",
    "S2",
    "S3",
    "S4",
    "W1",
  ]);
  expect(
    renderToStaticMarkup(<ArchitectureView strategy="hotspot" />),
  ).not.toContain("价值主链（11个模块）");
  const route = readFileSync(resolve(".umirc.ts"), "utf8");
  expect(route).toContain('path: "/strategy/hotspot"');
  expect(route.split('component: "./StrategyArchitecture/Value"')).toHaveLength(
    3,
  );
});
it("scopes disconnected runtime to the directory and acknowledges existing task controls", () => {
  const stage = catalog.value.stages.find((s) => s.id === "G2")!;
  const html = renderToStaticMarkup(<StageDetail stage={stage} />);
  expect(html).toContain("本目录尚未接运行reader");
  expect(html).toContain("不否认既有API和页面消费者");
  expect(html).not.toContain("没有开始、取消、恢复");
  expect(stage.implementation).toContain(
    "开始、历史读取、手动刷新、取消与恢复",
  );
  expect(html).toContain("config/value-mainline-modules-v1.json");
});
it("renders native references and eight method capabilities without claiming a run", () => {
  const methods = Object.fromEntries(
    Array.from({ length: 8 }, (_, i) => [
      "method_" + i,
      (["DESIGNED", "IMPLEMENTED", "PARTIAL"] as const)[i % 3],
    ]),
  );
  const stage = {
    ...catalog.value.stages[0],
    nativeContract: {
      source: "TEST_ONLY_ROOT_CONTRACT",
      entryRefs: ["TEST_ONLY_NATIVE_ENTRY"],
      inputSchemaRefs: ["TEST_ONLY_INPUT_SCHEMA"],
      outputSchemaRefs: ["TEST_ONLY_OUTPUT_SCHEMA"],
      methods,
    },
  };
  const html = renderToStaticMarkup(<StageDetail stage={stage} />);
  for (const text of [
    "TEST_ONLY_INPUT_SCHEMA",
    "TEST_ONLY_OUTPUT_SCHEMA",
    "TEST_ONLY_NATIVE_ENTRY",
    "DESIGNED",
    "IMPLEMENTED",
    "PARTIAL",
    "不是本次运行结果或经济批准",
  ])
    expect(html).toContain(text);
  for (const method of Object.keys(methods)) expect(html).toContain(method);
});

it("consumes Root's sole eleven-module catalog with all eight native capability methods and no reader fanout", () => {
  const root = JSON.parse(
    readFileSync(
      resolve("..", "config/value-mainline-modules-v1.json"),
      "utf8",
    ),
  );
  expect(root.modules).toHaveLength(11);
  for (const module of root.modules) {
    const stage = catalog.value.stages.find(
      (item) => item.id === module.module_id,
    )!;
    const contract = stage.nativeContract!;
    expect(contract.baseline).toBe(root.source_baseline);
    expect(contract.inputSchemaRefs).toEqual([module.input_schema.$ref]);
    expect(contract.outputSchemaRefs).toEqual([module.output_schema.$ref]);
    expect(contract.rawMethods).toEqual(module.method_status);
    expect(Object.keys(contract.methods)).toHaveLength(8);
    const html = renderToStaticMarkup(<StageDetail stage={stage} />);
    expect(html).toContain("原生已实现不等于统一wrapper已完成");
    expect(html).toContain(module.source_report);
    for (const status of Object.values(module.method_status))
      expect(html).toContain(String(status));
  }
  for (const stage of catalog.value.stages.slice(11))
    expect(stage.nativeContract).toBeUndefined();
  const page = readFileSync(
    resolve("src/pages/StrategyArchitecture/index.tsx"),
    "utf8",
  );
  const config = readFileSync(
    resolve("src/config/strategyArchitecture.v1.ts"),
    "utf8",
  );
  expect(page).not.toMatch(
    /useApi|useEffect|fetch\s*\(|setInterval|Promise\.all/,
  );
  expect(config).not.toMatch(/fetch\s*\(|setInterval|Promise\.all/);
  expect(page).not.toContain('from "../../services/api"');
});

it("shows Root phase-one source deltas only for A/B without promoting audited baseline to deployment", () => {
  const root = JSON.parse(
    readFileSync(
      resolve("..", "config/value-mainline-modules-v1.json"),
      "utf8",
    ),
  );
  expect(review.baseline).toBe(root.source_baseline);
  expect(catalog.value.summary).toContain("11个价值主链模块与5个共享支持模块");
  for (const id of ["A", "B"]) {
    const stage = catalog.value.stages.find((item) => item.id === id)!;
    expect(stage.nativeContract?.phase1Delta?.implementation).toEqual(
      root.phase1_implementation_delta[id].implementation,
    );
    const html = renderToStaticMarkup(<StageDetail stage={stage} />);
    expect(html).toContain("本轮源码未部署");
    expect(html).toContain(root.phase1_implementation_delta[id].boundary);
    for (const ref of root.phase1_implementation_delta[id].implementation)
      expect(html).toContain(ref);
  }
  expect(
    catalog.value.stages.find((item) => item.id === "C")?.nativeContract
      ?.phase1Delta,
  ).toBeUndefined();
});
