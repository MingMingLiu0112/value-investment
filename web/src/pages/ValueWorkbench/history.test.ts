import { describe, expect, it } from "vitest";
import { selectWorkbenchCompany } from "./index";

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
