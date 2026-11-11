import type { DailyPublicPacket, PacketPendingAction } from "../types/api";

export interface SystemActionRow {
  symbol: string;
  name: string;
  valuation: string;
  actions: PacketPendingAction[];
}

/** Project only published next steps; never infer admission from a blocker. */
export function systemActionRows(packet: DailyPublicPacket): SystemActionRow[] {
  return Object.entries(packet.company_statuses ?? {})
    .map(([symbol, company]) => {
      const seen = new Set<string>();
      const actions = (company.pending_actions ?? []).filter((action) => {
        if (!action.label || seen.has(action.label)) return false;
        seen.add(action.label);
        return true;
      });
      return {
        symbol,
        name: company.name || symbol,
        valuation: company.valuation_status?.user_label || "估值状态待核验",
        actions,
      };
    })
    .filter((row) => row.actions.length > 0)
    .sort((a, b) => a.symbol.localeCompare(b.symbol));
}
