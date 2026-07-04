import { useMemo } from 'react'
import { useArchive, useEloHistory, useEloRatings } from '../../hooks/queries'
import { normTeam } from '../../lib/util'
import type { Archive } from '../../lib/types'

export interface TeamRow {
  team: string
  elo: number
  delta: number
  w: number; d: number; l: number
  last5: ('W' | 'D' | 'L')[]
}

export interface MatchInfo {
  opponent: string
  score: string
  result: 'W' | 'D' | 'L'
}

/** Per-team match log keyed by match_id — feeds the Elo chart tooltip. */
function buildMatchInfo(archive: Archive | undefined): Record<string, Record<string, MatchInfo>> {
  const out: Record<string, Record<string, MatchInfo>> = {}
  for (const [matchId, m] of Object.entries(archive ?? {})) {
    const pmr = m.post_match_result
    if (pmr?.status !== 'completed' || !pmr.actual_score) continue
    const [hs, as] = pmr.actual_score.split(':').map(Number)
    if (Number.isNaN(hs) || Number.isNaN(as)) continue
    const home = normTeam(m.metadata.home_team)
    const away = normTeam(m.metadata.away_team)
    ;(out[home] ??= {})[matchId] = {
      opponent: away, score: `${hs}:${as}`,
      result: hs > as ? 'W' : hs < as ? 'L' : 'D',
    }
    ;(out[away] ??= {})[matchId] = {
      opponent: home, score: `${as}:${hs}`,
      result: as > hs ? 'W' : as < hs ? 'L' : 'D',
    }
  }
  return out
}

export function useTeamFormData() {
  const { data: history, isLoading: l1 } = useEloHistory()
  const { data: ratings, isLoading: l2 } = useEloRatings()
  const { data: archive, isLoading: l3 } = useArchive()

  const matchInfo = useMemo(() => buildMatchInfo(archive), [archive])

  const rows = useMemo<TeamRow[]>(() => {
    const teams = new Set<string>([
      ...Object.keys(ratings ?? {}),
      ...Object.keys(history ?? {}),
    ])
    const out: TeamRow[] = []
    for (const team of teams) {
      const hist = history?.[team] ?? []
      const baseline = hist.find((p) => p.match_id === 'baseline')?.elo ?? hist[0]?.elo
      const current = ratings?.[team]?.elo ?? hist[hist.length - 1]?.elo
      if (current == null) continue
      const log = Object.values(matchInfo[team] ?? {})
      const w = log.filter((x) => x.result === 'W').length
      const d = log.filter((x) => x.result === 'D').length
      const l = log.filter((x) => x.result === 'L').length
      out.push({
        team,
        elo: current,
        delta: baseline != null ? current - baseline : 0,
        w, d, l,
        last5: log.slice(-5).map((x) => x.result),
      })
    }
    return out.sort((a, b) => b.elo - a.elo)
  }, [ratings, history, matchInfo])

  return { rows, history, matchInfo, isLoading: l1 || l2 || l3 }
}
