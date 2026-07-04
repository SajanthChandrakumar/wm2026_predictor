import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import type { CustomBotParams, Match, RawMatch } from '../lib/types'

/** The cache can hold the same fixture under two ids (provider switch) —
 *  keep the entry with the richer prediction per team-pair + kickoff. */
function dedupeMatches(matches: Match[]): Match[] {
  const byKey = new Map<string, Match>()
  for (const m of matches) {
    const key = `${m.home_team}|${m.away_team}|${m.raw_match?.commence_time ?? ''}`
    const prev = byKey.get(key)
    if (!prev || (prev.top_tip === 'N/A' && m.top_tip !== 'N/A') || (prev.max_xp ?? 0) < (m.max_xp ?? 0)) {
      byKey.set(key, m)
    }
  }
  return [...byKey.values()]
}

export const useMatches = () =>
  useQuery({
    queryKey: ['matches'],
    queryFn: () => api.matches(),
    staleTime: 60_000,
    select: dedupeMatches,
  })

export const useArchive = () =>
  useQuery({ queryKey: ['archive'], queryFn: api.archive, staleTime: 60_000 })

export const useQuota = () =>
  useQuery({ queryKey: ['quota'], queryFn: api.quota, staleTime: 60_000 })

export const useEloHistory = () =>
  useQuery({ queryKey: ['eloHistory'], queryFn: api.eloHistory, staleTime: 300_000 })

export const useEloRatings = () =>
  useQuery({ queryKey: ['eloRatings'], queryFn: api.eloRatings, staleTime: 300_000 })

export const useLearningBots = () =>
  useQuery({ queryKey: ['learningBots'], queryFn: api.learningBots, staleTime: 300_000, retry: false })

export const useCustomBot = () =>
  useQuery({ queryKey: ['customBot'], queryFn: api.customBot, staleTime: 300_000, retry: false })

export const usePredict = () =>
  useMutation({
    mutationFn: ({ match, isKo }: { match: RawMatch; isKo: boolean }) => api.predict(match, isKo),
  })

export const useSaveUserTip = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ matchId, tip }: { matchId: string; tip: string }) => api.saveUserTip(matchId, tip),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['archive'] }),
  })
}

export const useSaveCustomBot = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ name, params }: { name: string; params: CustomBotParams }) =>
      api.saveCustomBot(name, params),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['customBot'] })
      qc.invalidateQueries({ queryKey: ['learningBots'] })
    },
  })
}

export const useSimulateBot = () =>
  useMutation({ mutationFn: (params: CustomBotParams) => api.simulateBot(params) })

export const useRefreshData = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.matches(true),
    onSuccess: (data) => {
      qc.setQueryData(['matches'], data)
      qc.invalidateQueries({ queryKey: ['quota'] })
    },
  })
}

export const useSyncElo = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: api.syncElo,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['archive'] })
      qc.invalidateQueries({ queryKey: ['eloHistory'] })
      qc.invalidateQueries({ queryKey: ['eloRatings'] })
      qc.invalidateQueries({ queryKey: ['quota'] })
    },
  })
}
