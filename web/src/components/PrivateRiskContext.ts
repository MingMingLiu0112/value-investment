export type PrivateRiskContext = {
  action: "no_order";
  symbol: string;
  revision: number;
  policy: Record<string, unknown> | null;
  cost_profile: {
    costs: Record<string, string>;
    confirmed_at: string;
    valid_until: string;
    record_sha256: string;
  } | null;
  verified_rules: Record<string, string>;
  rule_gaps: string[];
};

export const reusableCostFields = [
  "buy_fee_fraction",
  "sell_fee_fraction",
  "minimum_buy_fee_cny",
  "minimum_sell_fee_cny",
] as const;

/** One immutable request per attempt, including retries after a lost response. */
export function retryableWrite() {
  let attempt: { identity: string; body: Record<string, unknown> } | undefined;
  return {
    body(identity: string, create: () => Record<string, unknown>) {
      if (attempt?.identity !== identity)
        attempt = { identity, body: create() };
      return attempt.body;
    },
    clear() {
      attempt = undefined;
    },
  };
}
