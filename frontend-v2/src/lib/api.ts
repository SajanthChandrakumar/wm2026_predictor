import type {
  Archive, BotSimulation, CustomBot, CustomBotParams, EloHistory,
  EloRatings, KnockoutSimulation, LearningBot, Match, Prediction, Quota, RawMatch, SyncResult,
} from './types'
import { getOwnerSecret } from './ownerAuth'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`${res.status} ${res.statusText}${body ? ` — ${body.slice(0, 200)}` : ''}`)
  }
  return res.json() as Promise<T>
}

export const api = {
  quota: () => request<Quota>('/quota'),
  matches: (force = false) => request<Match[]>(`/matches${force ? '?force=true' : ''}`),
  predict: (match: RawMatch, isKo: boolean) =>
    request<Prediction>('/predict', {
      method: 'POST',
      body: JSON.stringify({ match, is_ko: isKo }),
    }),
  archive: () => request<Archive>('/archive'),
  eloHistory: () => request<EloHistory>('/elo_history'),
  eloRatings: () => request<EloRatings>('/elo_ratings'),
  syncElo: () => request<SyncResult>('/sync_elo?force=true'),
  saveUserTip: (matchId: string, userTip: string) =>
    request<{ status: string }>('/archive/user_tip', {
      method: 'POST',
      headers: { 'X-Owner-Secret': getOwnerSecret() ?? '' },
      body: JSON.stringify({ match_id: matchId, user_tip: userTip }),
    }),
  learningBots: () => request<LearningBot[]>('/learning_bots'),
  customBot: () => request<CustomBot>('/custom_bot'),
  saveCustomBot: (name: string, params: CustomBotParams) =>
    request<{ status: string }>('/custom_bot', {
      method: 'POST',
      headers: { 'X-Owner-Secret': getOwnerSecret() ?? '' },
      body: JSON.stringify({ name, params }),
    }),
  simulateBot: (params: CustomBotParams) =>
    request<BotSimulation>('/custom_bot/simulate', {
      method: 'POST',
      body: JSON.stringify({ params }),
    }),
  simulateKnockout: (runs = 20_000) =>
    request<KnockoutSimulation>(`/simulate_knockout?runs=${runs}`),
}
