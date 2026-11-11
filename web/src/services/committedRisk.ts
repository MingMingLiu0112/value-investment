export type CommittedRiskRow = {
  symbol: string;
  exchange: string;
  sleeve: string;
  quantity: string;
  cost_basis_cny: string;
  committed_risk_cny: string | null;
  evidence_ref: string | null;
};

export type CommittedRiskView = {
  action: "no_order";
  status: string;
  account_scope: string | null;
  revision: number;
  journal_tip_sha256: string | null;
  allocations: CommittedRiskRow[];
  blockers?: string[];
  formal_eligibility: false;
  confirmation_status?: string;
  confirmation_sha256?: string | null;
  qualification_status?: string;
  ledger_written?: boolean;
  changes_holdings?: boolean;
  request_binding?: {
    expected_revision: number;
    account_scope: string;
    journal_tip_sha256: string;
  };
};

export function verifyCommittedRiskResponse(
  response: CommittedRiskView,
  request: ReturnType<typeof committedRiskConfirmation>,
) {
  const amountKey = (value: string) => {
    if (!/^\d+(\.\d+)?$/.test(value)) throw new Error("风险金额响应不合法。");
    const [whole, fraction = ""] = value.split(".");
    return `${whole.replace(/^0+(?=\d)/, "")}.${fraction.replace(/0+$/, "")}`;
  };
  if (
    response.action !== "no_order" ||
    response.status !== "COMMITTED_RISK_CONFIRMED" ||
    response.formal_eligibility !== false ||
    response.account_scope !== request.account_scope ||
    response.revision !== request.expected_revision + 1 ||
    response.request_binding?.expected_revision !== request.expected_revision ||
    response.request_binding?.account_scope !== request.account_scope ||
    response.request_binding?.journal_tip_sha256 !==
      request.journal_tip_sha256 ||
    !/^[a-f0-9]{64}$/.test(response.journal_tip_sha256 ?? "") ||
    response.journal_tip_sha256 === request.journal_tip_sha256 ||
    response.changes_holdings !== false ||
    !/^[a-f0-9]{64}$/.test(response.confirmation_sha256 ?? "") ||
    !Array.isArray(response.allocations) ||
    response.allocations.length !== request.amounts.length
  )
    throw new Error("风险确认回执与当前请求不一致，请重新读取。");
  for (const expected of request.amounts) {
    const actual = response.allocations.filter(
      (row) => row.symbol === expected.symbol && row.sleeve === expected.sleeve,
    );
    if (
      actual.length !== 1 ||
      actual[0].committed_risk_cny === null ||
      amountKey(actual[0].committed_risk_cny) !==
        amountKey(expected.committed_risk_cny) ||
      actual[0].evidence_ref !== expected.evidence_ref
    )
      throw new Error("风险确认金额或依据与请求不一致。");
  }
}

export type RiskAmount = {
  symbol: string;
  sleeve: string;
  committed_risk_cny: string;
  evidence_ref: string;
};

export function committedRiskConfirmation(
  view: CommittedRiskView,
  revision: number,
  amounts: RiskAmount[],
  note: string,
  acknowledged: boolean,
) {
  if (
    view.action !== "no_order" ||
    view.formal_eligibility !== false ||
    view.revision !== revision ||
    !Number.isInteger(revision) ||
    revision <= 0 ||
    !view.account_scope ||
    !/^[a-f0-9]{64}$/.test(view.journal_tip_sha256 ?? "") ||
    !acknowledged ||
    !note.trim() ||
    !view.allocations.length ||
    view.allocations.length !== amounts.length
  )
    throw new Error("请重新读取当前持仓，逐项填写风险金额和依据，再明确确认。");
  const keys = new Set<string>();
  const checked = view.allocations.map((row) => {
    const key = `${row.sleeve}:${row.symbol}`;
    const matches = amounts.filter(
      (amount) => amount.symbol === row.symbol && amount.sleeve === row.sleeve,
    );
    if (keys.has(key) || matches.length !== 1)
      throw new Error("风险金额必须与当前分池持仓逐项一致。");
    keys.add(key);
    const amount = matches[0];
    const value = amount.committed_risk_cny.trim();
    if (
      !/^\d+(\.\d{1,2})?$/.test(value) ||
      !Number.isFinite(Number(value)) ||
      !amount.evidence_ref.trim()
    )
      throw new Error(
        "请填写非负金额（最多两位小数）和可回查的风险依据；未知不能填零。",
      );
    return {
      ...amount,
      committed_risk_cny: value,
      evidence_ref: amount.evidence_ref.trim(),
    };
  });
  return {
    expected_revision: revision,
    account_scope: view.account_scope,
    journal_tip_sha256: view.journal_tip_sha256,
    amounts: checked,
    confirmation_note: note.trim(),
    read_and_confirmed: true,
  };
}
