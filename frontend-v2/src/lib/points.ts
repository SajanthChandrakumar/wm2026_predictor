// SRF-Tippspiel scoring helpers (display only — scoring happens in the backend).
// Regeln: Tendenz 5 · je exakte Toranzahl +1 · korrekte Differenz +3 → max 10.
// K.O.-Phase: Punkte ×2.

export type PointsTier = 'exact' | 'diff' | 'tendency' | 'miss' | 'na'

export function pointsTier(p: number | null | undefined): PointsTier {
  if (p == null) return 'na'
  if (p >= 10) return 'exact'
  if (p >= 8) return 'diff'
  if (p >= 5) return 'tendency'
  return 'miss'
}

export const TIER_STYLES: Record<PointsTier, string> = {
  exact: 'bg-emerald-dim text-emerald-a border-emerald-a/40',
  diff: 'bg-emerald-dim text-emerald-a border-emerald-a/25',
  tendency: 'bg-gold-dim text-gold-a border-gold-a/30',
  miss: 'bg-red-a/10 text-red-a border-red-a/25',
  na: 'bg-surface text-fg-3 border-line',
}
