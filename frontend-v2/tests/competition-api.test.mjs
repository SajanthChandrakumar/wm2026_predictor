import test from 'node:test'
import assert from 'node:assert/strict'
import { competitionPath, validCompetition } from '../src/lib/competition.mjs'
import { botFormState } from '../src/lib/customBot.mjs'
import { validUclStandingsRows } from '../src/lib/standings.mjs'
import { hasScoreMatrix } from '../src/lib/prediction.mjs'

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
