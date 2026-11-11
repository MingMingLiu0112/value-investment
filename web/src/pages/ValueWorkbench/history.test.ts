import { describe, expect, it } from "vitest";
import { historicalTaskReadError, selectWorkbenchCompany } from "./index";
import { ApiError } from "../../services/api";

describe("sealed D2 task selection", () => {
  const registered = [{ symbol: "000568" }];
  const candidates = [{ symbol: "600887" }];

  it("opens a verified task-only symbol without treating it as a current candidate", () => {
    expect(
      selectWorkbenchCompany("600519", registered, candidates, false, [
        "600519",
      ]),
    ).toBe("600519");
    expect(
      selectWorkbenchCompany("600519", registered, candidates, false),
    ).toBe("000568");
  });

  it("preserves the ordinary registered/candidate selection and loading state", () => {
    expect(
      selectWorkbenchCompany("600887", registered, candidates, false, [
        "600519",
      ]),
    ).toBe("600887");
    expect(selectWorkbenchCompany(undefined, [], [], true, [])).toBeUndefined();
  });
});

describe("sealed task read errors", () => {
  it("separates expired local authorization from sealed source corruption", () => {
    expect(
      historicalTaskReadError(
        new ApiError(401, "LOCAL_AUTHORIZATION_REQUIRED", null),
      ),
    ).toContain("会话未解锁");
    expect(
      historicalTaskReadError(
        new ApiError(
          422,
          "HORIZON_TASK_DISCOVERY_UNAVAILABLE",
          "V11_SOURCE_CHANGED",
        ),
      ),
    ).toContain("V11_SOURCE_CHANGED");
    expect(
      historicalTaskReadError(
        new ApiError(
          422,
          "HORIZON_TASK_DISCOVERY_UNAVAILABLE",
          "unsafe raw detail!",
        ),
      ),
    ).not.toContain("unsafe raw detail");
  });
});
