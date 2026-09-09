import test from 'node:test'
import assert from 'node:assert/strict'
import { competitionPath, validCompetition } from '../src/lib/competition.mjs'

test('competitionPath URL-encodes the active competition', () => {
  assert.equal(competitionPath('/matches?force=true', 'ucl2026'), '/matches?force=true&competition=ucl2026')
})

test('validCompetition defaults invalid storage values to UCL', () => {
  assert.equal(validCompetition('wc2026'), 'wc2026')
  assert.equal(validCompetition('invalid'), 'ucl2026')
  assert.equal(validCompetition(null), 'ucl2026')
})
