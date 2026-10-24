import React from "react";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { dirname, relative, resolve } from "node:path";
import { expect, it, vi } from "vitest";
import {
  EconomicReviewResult,
  SourceNativeEconomicReview,
} from "../src/components/SourceNativeEconomicReview";
import { verifiedEconomicReview } from "../src/services/sourceNativeEconomicReview";
const { renderToStaticMarkup } = require("react-dom/server");

import {
  economicRef as ref,
  economicFixture as fixture,
} from "./fixtures/sourceNativeEconomic";

it("renders separate terminal conventions and conditional historical-share limits", () => {
  const value = fixture();
  expect(verifiedEconomicReview(value, "600519", ref)).toBe(true);
  const html = renderToStaticMarkup(<EconomicReviewResult value={value} />);
  for (const text of [
    "历史普通股分母",
    "未来股利终值",
    "RI终端剩余收益",
    "70%",
    "50%",
    "不是长期安全阈值",
    "不是当前目标价",
    "正常化利润未在此确认",
  ])
    expect(html).toContain(text);
});

it("opening the existing company page does not issue implicit new requests", () => {
  const spy = vi.spyOn(globalThis, "fetch");
  const html = renderToStaticMarkup(
    <SourceNativeEconomicReview symbol="600519" candidate={ref} />,
  );
  expect(html).toContain("读取经济复核");
  expect(spy).not.toHaveBeenCalled();
  spy.mockRestore();
});

it.each([
  "symbol",
  "candidate",
  "approval",
  "price",
  "normalization",
  "shares",
  "number",
  "duplicate",
  "group",
  "source",
])("rejects stale or promoted economic response: %s", (fault) => {
  const value = fixture();
  if (fault === "symbol") value.symbol = "600887";
  else if (fault === "candidate")
    value.candidate_binding.sha256 = "f".repeat(64);
  else if (fault === "approval") value.research_admitted = true;
  else if (fault === "price") value.price_admitted = true;
  else if (fault === "normalization")
    value.normalized_parent_profit_cny = "100";
  else if (fault === "shares") value.share_basis.current_shares = "10000";
  else if (fault === "number")
    value.scenarios[0].original.ddm_terminal_fraction = "NaN";
  else if (fault === "duplicate") value.scenarios[2].scenario = "bear";
  else if (fault === "group") value.five_groups[0].approval_status = "APPROVED";
  else value.source_bindings[0].path = "../private/account.json";
  expect(verifiedEconomicReview(value, "600519", ref)).toBe(false);
});

it("unsupported challenges remain explicit instead of displaying a made-up number", () => {
  const value = fixture();
  value.scenarios[1].ke_plus_200bp = {
    status: "UNSUPPORTED",
    delta_basis_points: 200,
    alternative_candidate_verified: false,
  };
  expect(verifiedEconomicReview(value, "600519", ref)).toBe(true);
  expect(
    renderToStaticMarkup(<EconomicReviewResult value={value} />),
  ).toContain("现有内核不支持此挑战");
});

it.skipIf(!process.env.NATIVE_ECONOMIC_REVIEW_JSON)(
  "consumes actual public-source HTTP economic diagnostics",
  () => {
    const file = resolve(process.env.NATIVE_ECONOMIC_REVIEW_JSON!);
    expect(relative(resolve(process.cwd(), "..", ".tmp"), file)).not.toMatch(
      /^(?:\.\.|[A-Za-z]:|[\\/])/,
    );
    const bytes = readFileSync(file);
    const receipt = JSON.parse(
      readFileSync(resolve(dirname(file), "receipt.json"), "utf8"),
    );
    expect(receipt.scope).toBe(
      "ACTUAL_PUBLIC_REFERENCES_LOCAL_TESTCLIENT_NOT_LIVE_8001",
    );
    expect(receipt.status).toBe("PASS");
    expect(createHash("sha256").update(bytes).digest("hex")).toBe(
      receipt.result_sha256,
    );
    const value = JSON.parse(bytes.toString("utf8"));
    expect(
      verifiedEconomicReview(value, "600519", receipt.candidate_binding),
    ).toBe(true);
    expect(
      renderToStaticMarkup(<EconomicReviewResult value={value} />),
    ).toContain("不能直接形成买入或加仓资格");
  },
);
