import { describe, expect, it } from "vitest";
import {
  codeText,
  describeCode,
  engineAlertText,
  reconciliationText,
  strategyText,
} from "../src/utils/codes";

describe("machine code translation", () => {
  it("translates the frozen backend codes into plain Chinese", () => {
    expect(codeText("UNVERIFIED_PROVIDER_TRADE_DATE")).toBe(
      "行情供应商的交易日期尚未独立核实",
    );
    expect(codeText("NO_FORMAL_ADMISSION")).toBe(
      "目前没有通过全部正式审核条件的买卖候选",
    );
    expect(codeText("PRICE_NOT_ADMITTED")).toBe("尚未接入经核验的当前行情");
    expect(codeText("minimum_cash_cny")).toBe("现金底线");
    expect(codeText("time_horizon_years")).toBe("投资期限");
    expect(codeText("concentration_allowed")).toBe("是否允许集中");
    expect(codeText("risk_tolerance")).toBe("风险承受度");
    expect(codeText("reconciliation")).toBe("尚未执行对账");
    expect(codeText("holding_market_value")).toBe(
      "正式风险计算缺少已准入的持仓市值",
    );
    expect(codeText("investable_assets_cny")).toBe("可投资资产");
    expect(codeText("max_single_security_pct")).toBe("单票上限");
    expect(codeText("max_single_industry_pct")).toBe("行业上限");
    expect(codeText("security_attributes.missing")).toBe("证券风险属性");
    expect(codeText("sleeve_policy.private_input_missing")).toBe(
      "双资金池预算",
    );
    expect(codeText("cash_reserve")).toBe("现金储备");
    expect(codeText("no_order")).toBe("仅供研究复核，不构成下单");
  });

  it("falls back to the raw code instead of inventing a translation", () => {
    expect(codeText("BRAND_NEW_CODE")).toBeNull();
    expect(describeCode("BRAND_NEW_CODE")).toBe("BRAND_NEW_CODE");
    expect(describeCode(undefined)).toBe("未提供");
    expect(engineAlertText("MADE_UP")).toBe("MADE_UP");
  });

  it("labels strategy, reconciliation and engine alerts without raw enums", () => {
    expect(strategyText("value")).toBe("价值投资");
    expect(strategyText("hotspot")).toBe("热点追踪");
    expect(reconciliationText("RECONCILED")).toBe("已完成对账");
    expect(reconciliationText("PENDING_RECONCILIATION")).toBe("尚未执行对账");
    expect(engineAlertText("CORE_VALUE:risk_unknown")).toBe(
      "价值池：尚未提供承诺风险金额，风险敞口未知",
    );
    expect(engineAlertText("shared:cash_floor_violation")).toBe(
      "跨资金池：现金储备低于设定的现金底线",
    );
  });
});
