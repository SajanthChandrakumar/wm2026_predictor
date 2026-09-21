import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const read = (path) => readFileSync(new URL(`../${path}`, import.meta.url), 'utf8')

test('mobile shell exposes the approved three-item navigation', () => {
  const shell = read('src/components/layout/AppShell.tsx')
  assert.match(shell, /Spiele/)
  assert.match(shell, /Meine Tipps/)
  assert.match(shell, /Mehr/)
  assert.match(shell, /lg:hidden/)
})

test('dashboard uses plain-language mobile prediction cards', () => {
  const row = read('src/features/dashboard/FixtureRow.tsx')
  assert.match(row, /Unser Tipp/)
  assert.match(row, /Buchmacherquote|Elo-Modellquote|Nicht verfügbar/)
  assert.match(row, /min-h-\[48px\]/)
})

test('global styling uses the approved palette and removes the blueprint grid', () => {
  const css = read('src/index.css')
  assert.match(css, /#315efb/i)
  assert.match(css, /#edf1f6/i)
  assert.doesNotMatch(css, /blueprint grid/i)
})
