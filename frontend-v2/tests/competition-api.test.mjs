import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { competitionPath, validCompetition } from '../src/lib/competition.mjs'
import { botFormState } from '../src/lib/customBot.mjs'
import { validUclStandingsRows } from '../src/lib/standings.mjs'
import { hasScoreMatrix } from '../src/lib/prediction.mjs'
import { hasUclSimulationResults } from '../src/lib/simulation.mjs'
import { withRatingBaselines } from '../src/lib/team-form.mjs'

let officialPerformance
try {
  ({ officialPerformance } = await import('../src/lib/performance.mjs'))
} catch {
  // The assertion below reports the missing implementation as a failed behavior test.
}

test('competitionPath URL-encodes the active competition', () => {
  assert.equal(competitionPath('/matches?force=true', 'ucl2026'), '/matches?force=true&competition=ucl2026')
})

test('validCompetition defaults invalid storage values to UCL', () => {
  assert.equal(validCompetition('wc2026'), 'wc2026')
  assert.equal(validCompetition('invalid'), 'ucl2026')
  assert.equal(validCompetition(null), 'ucl2026')
})

test('botFormState reloads saved values or clean defaults', () => {
  assert.deepEqual(botFormState(undefined), {
    name: 'Mein Bot',
    params: { market_weight: 0.7, risk: 0, draw_bias: 0, underdog_bias: 0 },
  })
  assert.deepEqual(botFormState({ exists: true, name: 'UCL Bot', params: { market_weight: 0.2 } }), {
    name: 'UCL Bot',
    params: { market_weight: 0.2, risk: 0, draw_bias: 0, underdog_bias: 0 },
  })
})

test('validUclStandingsRows rejects partial, duplicate, or unranked tables', () => {
  const rows = Array.from({ length: 36 }, (_, index) => ({ team: `Team ${index}`, pos: index + 1 }))
  assert.equal(validUclStandingsRows(rows)?.length, 36)
  assert.equal(validUclStandingsRows(rows.slice(0, 35)), null)
  assert.equal(validUclStandingsRows(rows.map((row, index) => index === 35 ? { ...row, team: 'Team 0' } : row)), null)
  assert.equal(validUclStandingsRows(rows.map((row, index) => index === 35 ? { ...row, team: ' Team 0 ' } : row)), null)
  assert.equal(validUclStandingsRows(rows.map(({ team }) => ({ team }))), null)
})

test('hasScoreMatrix rejects empty matrices', () => {
  assert.equal(hasScoreMatrix({}), false)
  assert.equal(hasScoreMatrix({ 0: { 0: 0, 1: 0 }, 1: { 0: 0 } }), false)
  assert.equal(hasScoreMatrix({ 0: { 0: 0.25 } }), true)
})

test('hasUclSimulationResults rejects unavailable and malformed payloads', () => {
  assert.equal(hasUclSimulationResults(undefined), false)
  assert.equal(hasUclSimulationResults({ status: 'unavailable' }), false)
  assert.equal(hasUclSimulationResults({ status: 'fresh' }), false)
  assert.equal(hasUclSimulationResults({ status: 'fresh', results: [] }), true)
})

test('withRatingBaselines makes current ClubElo ratings chartable without invented history', () => {
  assert.deepEqual(
    withRatingBaselines({}, {
      Arsenal: { elo: 2035 },
      Barcelona: { elo: 2015 },
    }),
    {
      Arsenal: [{ timestamp: 0, match_id: 'baseline', elo: 2035 }],
      Barcelona: [{ timestamp: 0, match_id: 'baseline', elo: 2015 }],
    },
  )

  const existing = { Arsenal: [{ timestamp: 123, match_id: 'match-1', elo: 2020 }] }
  assert.deepEqual(withRatingBaselines(existing, { Arsenal: { elo: 2035 } }), existing)
})

test('performance counts only actual user tips and refreshes archive data', () => {
  const performance = readFileSync(new URL('../src/features/performance/usePerformanceData.ts', import.meta.url), 'utf8')
  const scoreboard = readFileSync(new URL('../src/features/performance/BotScoreboard.tsx', import.meta.url), 'utf8')
  const view = readFileSync(new URL('../src/features/performance/PerformanceView.tsx', import.meta.url), 'utf8')
  const queries = readFileSync(new URL('../src/hooks/queries.ts', import.meta.url), 'utf8')
  const refresh = queries.slice(queries.indexOf('export const useRefreshData'))

  assert.match(performance, /userCount/)
  assert.match(scoreboard, /tipped: totals\.userCount/)
  assert.match(view, /totals\.correctTendency \/ totals\.userCount/)
  assert.match(refresh, /invalidateQueries\(\{ queryKey: \['archive', competition\] \}\)/)
})

test('official performance excludes post-match Elo reconstructions', () => {
  assert.equal(typeof officialPerformance, 'function')

  const result = officialPerformance({
    tracked: {
      prediction: { algo_reconstructed: false },
      post_match_result: {
        status: 'completed', algo_points: 6,
        bot_points: { broker: 5, professor: 6 },
      },
    },
    reconstructed: {
      prediction: { algo_reconstructed: true },
      post_match_result: {
        status: 'completed', algo_points: 10,
        bot_points: { broker: 10, professor: 10 },
      },
    },
    pending: {
      prediction: { algo_reconstructed: false },
      post_match_result: { status: 'pending', algo_points: 10 },
    },
  }, ['broker', 'professor'])

  assert.deepEqual(result, {
    algoTotal: 6,
    algoCount: 1,
    algoTendency: 1,
    reconstructedCount: 1,
    botStats: {
      broker: { pts: 5, tipped: 1, tendency: 1 },
      professor: { pts: 6, tipped: 1, tendency: 1 },
    },
  })
})
