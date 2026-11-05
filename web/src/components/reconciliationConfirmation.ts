export type ReconciliationMode = "INTERNAL" | "EXTERNAL";
export const accountEvidenceKinds = [
  "broker_statement",
  "account_statement",
  "custodian_statement",
] as const;

export function reconciliationConfirmation(input: {
  mode: ReconciliationMode;
  evidenceId: string;
  evidenceKind?: string;
  note: string;
  checks: Record<string, boolean>;
}) {
  if (
    !input.note.trim() ||
    !["cash_checked", "positions_checked", "fills_checked"].every(
      (key) => input.checks[key] === true,
    )
  )
    throw new Error("请逐项核对现金、持仓成本与成交，并填写本人说明");
  if (input.mode !== "INTERNAL" && input.mode !== "EXTERNAL")
    throw new Error("请选择对账范围");
  if (
    input.mode === "EXTERNAL" &&
    (!input.evidenceId.trim() ||
      !accountEvidenceKinds.some((kind) => kind === input.evidenceKind))
  )
    throw new Error("外部对账需要真实对账单引用编号及凭证类型");
  return {
    confirmation_note: input.note.trim(),
    cash_checked: true,
    positions_checked: true,
    fills_checked: true,
    ...(input.mode === "EXTERNAL"
      ? {
          account_evidence: {
            id: input.evidenceId.trim(),
            kind: input.evidenceKind!,
          },
        }
      : {}),
  };
}
