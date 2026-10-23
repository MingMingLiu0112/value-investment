import { expect, it } from "vitest";
import {
  dailyResearchDates,
  dailyMachineResearchReview,
} from "../src/utils/dailyResearchDates";

function packet(status = "COVERS") {
  return {
    action: "no_order",
    packet_status: "CURRENT",
    source_bindings_verified: true,
    generated_at: "2026-10-23T16:00:00+08:00",
    dates: { research_as_of: "2026-10-11", quote_trade_date: "2026-10-11" },
    data_freshness: { research: { status } },
    company_statuses: {
      "600519": {
        symbol: "600519",
        name: "TEST_ONLY 研究证券",
        price_bridge: {
          incremental_status: "VALID",
          review_cutoff: "2026-10-22",
          blockers: [],
          incremental_validity_binding: {
            path: "TEST_ONLY/validity.json",
            sha256: "a".repeat(64),
          },
        },
      },
    },
  };
}

it("recognizes actual producer coverage enums without minting a trading flag", () => {
  const direct = dailyResearchDates(packet());
  expect(direct.researchCovered).toBe(true);
  expect(direct.coverageLabel).toContain("研究基准覆盖");
  const value = packet("INCREMENTALLY_COVERS");
  value.dates.quote_trade_date = "2026-10-22";
  const incremental = dailyResearchDates(value);
  expect(incremental.researchCovered).toBe(true);
  expect(incremental.researchAsOf).toBe("2026-10-11");
  expect(incremental.coverageLabel).toContain("原研究基准未改变");
  expect(incremental).not.toHaveProperty("trade_eligible");
  expect(incremental).not.toHaveProperty("formal_eligibility");
});

it.each([
  "FRESH",
  "INCREMENTAL_REVIEW_PENDING",
  "STALE",
  "UNKNOWN",
  "FAILED",
  "PARTIAL",
])("does not infer coverage from %s", (status) => {
  expect(dailyResearchDates(packet(status)).researchCovered).toBe(false);
});

it("does not confuse generation, research cutoff or event coverage with an actual review receipt", () => {
  const result = dailyResearchDates(packet());
  expect(result.latestReviewLabel).toContain("尚无可核验复核回执");
  expect(result.latestReviewLabel).not.toContain("2026-10-23");
  expect(result.events[0].cutoff).toBe("2026-10-22");
  expect(result.events[0].label).toBe("增量事件有效性已核验");
});

it.each(["PENDING", "STALE", "INVALID", "UNKNOWN"])(
  "keeps %s event validity unavailable",
  (status) => {
    const value = packet();
    value.company_statuses["600519"].price_bridge.incremental_status = status;
    expect(dailyResearchDates(value).events[0].label).toContain("暂不可用");
  },
);

it("rejects source-unverified coverage and malformed or absent dates", () => {
  const value = packet();
  value.source_bindings_verified = false;
  let result = dailyResearchDates(value);
  expect(result.researchCovered).toBe(false);
  expect(result.events[0].cutoff).toBeNull();
  value.source_bindings_verified = true;
  value.dates.research_as_of = "2026-02-30";
  result = dailyResearchDates(value);
  expect(result.researchAsOf).toBeNull();
  expect(result.researchCovered).toBe(false);
  expect(dailyResearchDates(undefined).researchCovered).toBe(false);
});

it("does not turn a future quote beyond baseline into direct research coverage", () => {
  const value = packet();
  value.dates.quote_trade_date = "2026-10-22";
  expect(dailyResearchDates(value).researchCovered).toBe(false);
  expect(dailyResearchDates(value).coverageLabel).toContain("不一致");
});

it("does not present an incremental label as covered without a valid bound event review", () => {
  const value = packet("INCREMENTALLY_COVERS");
  value.dates.quote_trade_date = "2026-10-22";
  value.company_statuses["600519"].price_bridge.incremental_status = "PENDING";
  expect(dailyResearchDates(value).researchCovered).toBe(false);
  expect(dailyResearchDates(value).coverageLabel).toContain("缺少有效事件版本");
});

// TEST_ONLY machine receipt; never an investment approval fixture.
function machineReceipt() {
  return {
    status: "PARTIAL",
    finished_at: "2026-10-23T17:00:00+08:00",
    research_review: {
      status: "SOURCE_REPLAYED",
      checked_at: "2026-10-23T16:00:00+08:00",
      review_cutoff: "2026-10-22",
      scope: "MACHINE_REVIEW_NOT_RESEARCH_APPROVAL",
      action: "no_order",
      formal_eligibility: false,
      rows: [
        {
          symbol: "600519",
          status: "PARTIAL",
          research_as_of: "2026-10-11",
          scan_through: "2026-10-22",
          event_coverage_through: null,
          announcement_count: 3,
          facts_change_status: "UNKNOWN",
          model_validity_status: "UNKNOWN",
          model_recalculation_required: true,
          materiality_review_required: true,
          formal_eligibility: false,
        },
      ],
    },
  };
}

it("shows only source-replayed machine time and preserves unknown complete event coverage", () => {
  const value = dailyMachineResearchReview(machineReceipt());
  expect(value.checkedAt).toBe("2026-10-23T16:00:00+08:00");
  expect(value.label).toContain("不是人工经济审核");
  expect(value.rows[0].event_coverage_through).toBeNull();
  expect(value.rows[0].scan_through).toBe("2026-10-22");
  expect(value.rows[0].research_as_of).toBe("2026-10-11");
  expect(value.rows[0].formal_eligibility).toBe(false);
});

it.each([
  "UNVERIFIED",
  "RECEIPT_UNAVAILABLE",
  "NOT_RECORDED",
  "FRESH",
  "FAILED",
])("hides trusted machine dates and rows when receipt is %s", (status) => {
  const value = machineReceipt();
  value.research_review.status = status;
  const result = dailyMachineResearchReview(value);
  expect(result.checkedAt).toBeNull();
  expect(result.reviewCutoff).toBeNull();
  expect(result.rows).toEqual([]);
});

it("refuses machine authority changes and missing source scope", () => {
  const value = machineReceipt();
  value.research_review.rows[0].formal_eligibility = true;
  expect(dailyMachineResearchReview(value).checkedAt).toBeNull();
  value.research_review.rows[0].formal_eligibility = false;
  value.research_review.scope = "APPROVED";
  expect(dailyMachineResearchReview(value).checkedAt).toBeNull();
  expect(
    dailyMachineResearchReview({ finished_at: "2026-10-23T17:00:00+08:00" })
      .checkedAt,
  ).toBeNull();
});

it("keeps zero-announcement incomplete windows unknown and preserves observed review-required events", () => {
  const value = machineReceipt();
  const row = value.research_review.rows[0] as Record<string, unknown>;
  row.event_coverage_status = "UNCONFIRMED";
  row.announcement_count = 0;
  row.facts_change_status = "NONE";
  row.model_validity_status = "VALID";
  row.model_recalculation_required = false;
  let output = dailyMachineResearchReview(value).rows[0];
  expect(output.event_coverage_status).toBe("UNCONFIRMED");
  expect(output.event_coverage_through).toBeNull();
  expect(output.facts_change_status).toBe("UNKNOWN");
  expect(output.model_validity_status).toBe("UNKNOWN");
  expect(output.model_recalculation_required).toBeNull();
  row.facts_change_status = "REVIEWED_NO_MODEL_INVALIDATION";
  output = dailyMachineResearchReview(value).rows[0];
  expect(output.facts_change_status).toBe("UNKNOWN");
  expect(output.model_validity_status).toBe("UNKNOWN");
  expect(output.model_recalculation_required).toBeNull();
  row.facts_change_status = "REVIEW_REQUIRED";
  expect(dailyMachineResearchReview(value).rows[0].facts_change_status).toBe(
    "REVIEW_REQUIRED",
  );
  row.event_coverage_status = "COMPLETE";
  row.event_coverage_through = "2026-10-22";
  output = dailyMachineResearchReview(value).rows[0];
  expect(output.event_coverage_status).toBe("COMPLETE");
  expect(output.event_coverage_through).toBe("2026-10-22");
  expect(output.model_validity_status).toBe("VALID");
  expect(output.model_recalculation_required).toBe(false);
});
