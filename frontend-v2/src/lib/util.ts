// Pure helpers — ported from the legacy frontend's util.js.
import type { Odds } from './types'

/** Implied probability as rounded percent; dash for placeholder fixtures. */
export const pct = (p: number | null | undefined): string =>
  Number.isFinite(p) && (p as number) > 0 ? `${((p as number) * 100).toFixed(0)}%` : '–'

/** Remove bookmaker margin from h2h decimal odds → true probabilities. */
export function computeImpliedProbs(odds?: Odds | null): { home: number; draw: number; away: number } {
  if (!odds || !odds.home || !odds.draw || !odds.away) return { home: 0, draw: 0, away: 0 }
  const rh = 1 / odds.home
  const rd = 1 / odds.draw
  const ra = 1 / odds.away
  const t = rh + rd + ra
  return { home: rh / t, draw: rd / t, away: ra / t }
}

/** Heatmap cell color — 3-stop gradient driven by the theme's --heat-* tokens. */
export function probColor(prob: number, maxProb: number, isLight: boolean): string {
  const darkStops: [number, number, number][] = [[13, 18, 32], [90, 55, 10], [210, 148, 26]]
  const lightStops: [number, number, number][] = [[245, 240, 230], [217, 140, 88], [200, 121, 65]]
  const stops = isLight ? lightStops : darkStops
  if (!prob || !maxProb) return `rgb(${stops[0].join(',')})`
  const r = Math.min(prob / maxProb, 1)
  const [c1, c2, t] = r < 0.5 ? [stops[0], stops[1], r / 0.5] : [stops[1], stops[2], (r - 0.5) / 0.5]
  const mix = (i: number) => Math.round(c1[i] + (c2[i] - c1[i]) * t)
  return `rgb(${mix(0)},${mix(1)},${mix(2)})`
}

/** Map archive (Odds-API) team names → normalized Elo team names. */
const TEAM_NORMALIZE: Record<string, string> = {
  'United States': 'United States', USA: 'United States',
  'Korea Republic': 'South Korea', 'South Korea': 'South Korea',
  Czechia: 'Czech Republic', 'Czech Republic': 'Czech Republic',
  'IR Iran': 'Iran', "Côte d'Ivoire": 'Ivory Coast', 'Ivory Coast': 'Ivory Coast',
  Türkiye: 'Türkiye', Turkey: 'Türkiye',
  'Bosnia & Herzegovina': 'Bosnia and Herzegovina',
  'Bosnia and Herzegovina': 'Bosnia and Herzegovina',
}
export const normTeam = (t: string): string => TEAM_NORMALIZE[t] ?? t

const FLAGS: Record<string, string> = {
  Argentina: '🇦🇷', Brazil: '🇧🇷', France: '🇫🇷', Germany: '🇩🇪', Spain: '🇪🇸', England: '🏴󠁧󠁢󠁥󠁮󠁧󠁿',
  Netherlands: '🇳🇱', Portugal: '🇵🇹', Italy: '🇮🇹', Belgium: '🇧🇪', Croatia: '🇭🇷', Switzerland: '🇨🇭',
  Denmark: '🇩🇰', Sweden: '🇸🇪', Austria: '🇦🇹', 'Czech Republic': '🇨🇿', Türkiye: '🇹🇷', Norway: '🇳🇴',
  Poland: '🇵🇱', Mexico: '🇲🇽', 'United States': '🇺🇸', Canada: '🇨🇦', Uruguay: '🇺🇾', Colombia: '🇨🇴',
  Ecuador: '🇪🇨', Paraguay: '🇵🇾', 'South Korea': '🇰🇷', Japan: '🇯🇵', Iran: '🇮🇷', 'Saudi Arabia': '🇸🇦',
  Iraq: '🇮🇶', Australia: '🇦🇺', 'New Zealand': '🇳🇿', Morocco: '🇲🇦', Senegal: '🇸🇳', 'Ivory Coast': '🇨🇮',
  Tunisia: '🇹🇳', Algeria: '🇩🇿', Egypt: '🇪🇬', Ghana: '🇬🇭', Cameroon: '🇨🇲', Nigeria: '🇳🇬',
  'DR Congo': '🇨🇩', 'South Africa': '🇿🇦', Qatar: '🇶🇦', Jordan: '🇯🇴', Curaçao: '🇨🇼', 'Cape Verde': '🇨🇻',
  Scotland: '🏴󠁧󠁢󠁳󠁣󠁴󠁿', Wales: '🏴󠁧󠁢󠁷󠁬󠁳󠁿', Haiti: '🇭🇹', Uzbekistan: '🇺🇿', 'Bosnia and Herzegovina': '🇧🇦',
}
export const flag = (t: string): string => FLAGS[normTeam(t)] ?? '🏳️'

export const cn = (...parts: (string | false | null | undefined)[]) => parts.filter(Boolean).join(' ')
