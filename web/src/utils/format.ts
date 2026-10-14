const MONEY = new Intl.NumberFormat("zh-CN", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const UNIT_PRICE = new Intl.NumberFormat("zh-CN", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 4,
});

/** Display only; never changes the retained backend decimals. */
export function formatDecimal(value?: string | number | null): string {
  return formatMoney(value);
}

function numeric(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined || value === "") return null;
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

/** 金额：固定两位小数，带千分位。无法解析时原样返回。 */
export function formatMoney(value?: string | number | null): string {
  const parsed = numeric(value);
  if (parsed === null) {
    return value === null || value === undefined ? "—" : String(value);
  }
  return MONEY.format(parsed);
}

/** 每股价格/成本：两位到四位小数，保留费用摊薄后的精度。 */
export function formatUnitPrice(value?: string | number | null): string {
  const parsed = numeric(value);
  if (parsed === null) {
    return value === null || value === undefined ? "—" : String(value);
  }
  return UNIT_PRICE.format(parsed);
}
