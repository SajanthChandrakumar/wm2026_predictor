// Backend response shapes — mirrors src/api.py + routes/services.

export interface Odds {
  home: number
  draw: number
  away: number
  over25?: number
  under25?: number
}

export interface TeamForm {
  form: ('W' | 'D' | 'L')[]
  on_fire: boolean
}

export interface BotTip {
  tip: string
  xp?: number
}

export type BotKey = 'broker' | 'professor' | 'sniper' | 'gambler'

export interface RawMatch {
  id: string
  commence_time?: string
  [key: string]: unknown
}

export interface Match {
  id: string
  home_team: string
  away_team: string
  home_disp: string
  away_disp: string
  odds: Odds
  top_tip: string
  max_xp: number
  edge_home?: number | null
  market_home_share?: number | null
  elo_home_share?: number | null
  home_form?: TeamForm
  away_form?: TeamForm
  h2h?: Record<string, number>
  lineup_diff?: Record<string, { starters: Record<string, string>; missing: string[] }>
  bots?: Partial<Record<BotKey, BotTip>>
  home_team_id?: number
  away_team_id?: number
  is_ko_phase?: boolean
  completed?: boolean
  actual_score?: string | null
  raw_match: RawMatch
}

export interface XpTip {
  Tipp: string
  xP: number
}

export interface Prediction {
  xg_home: number
  xg_away: number
  max_prob?: number
  /** Dict-of-dicts keyed by home/away goal count (backend serializes the DataFrame). */
  matrix: Record<number, Record<number, number>>
  xp_tips: XpTip[]
}

export interface ArchiveEntry {
  metadata: {
    home_team: string
    away_team: string
    home_disp: string
    away_disp: string
    is_ko_phase: boolean
    commence_time?: string | null
  }
  pre_match_snapshot?: {
    timestamp_recorded?: string
    [key: string]: unknown
  } | null
  prediction: {
    top_tip: string | null
    max_xp: number | null
    user_tip?: string | null
    algo_reconstructed?: boolean
    bots?: Partial<Record<BotKey, BotTip>>
  }
  post_match_result: {
    status: 'pending' | 'completed'
    actual_score?: string | null
    points_earned?: number | null
    algo_points?: number | null
    bot_points?: Partial<Record<BotKey, number | null>>
  }
}

export type Archive = Record<string, ArchiveEntry>

export interface EloHistoryPoint {
  timestamp: number
  match_id: string
  elo: number
}

export type EloHistory = Record<string, EloHistoryPoint[]>

export type EloRatings = Record<string, { team_code?: string; elo: number }>

export interface Quota {
  odds: { remaining: string | number; used: string | number }
  football: { remaining: string | number; used: string | number; limit?: string | number }
}

export interface CustomBotParams {
  market_weight: number
  risk: number
  draw_bias: number
  underdog_bias: number
}

export interface CustomBot {
  exists: boolean
  name?: string
  params?: CustomBotParams
}

export interface BotSimulation {
  total_points: number
  matches: number
  tendency_rate: number
  breakdown: { match_id: string; points: number }[]
}

export interface LearningBot {
  key: string
  name: string
  color: string
  pts: number
  tipped: number
  tendency: number
  pointsByMatch: Record<string, number>
  learned_label?: string | null
}

export interface SyncResult {
  status: 'success' | 'info' | 'error'
  updates?: number
  message?: string
}
