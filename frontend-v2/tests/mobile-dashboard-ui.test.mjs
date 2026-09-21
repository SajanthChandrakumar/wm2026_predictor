import test from 'node:test'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'

const read = (path) => readFileSync(new URL(`../${path}`, import.meta.url), 'utf8')

test('mobile shell exposes the approved three-item navigation', () => {
  const shell = read('src/components/layout/AppShell.tsx')
  assert.match(shell, /Spiele/)
  assert.match(shell, /Meine Tipps/)
  assert.match(shell, /Mehr/)
  assert.match(shell, /to: '\/'/)
  assert.match(shell, /to: '\/performance'/)
  assert.match(shell, /lg:hidden/)

  const mehrTriggers = shell.match(/<button[\s\S]*?(?:aria-expanded=\{moreOpen\}|aria-label="Mehr öffnen")[\s\S]*?Mehr[\s\S]*?<\/button>/g) ?? []
  assert.equal(mehrTriggers.length, 1, 'the shell must expose one mobile Mehr trigger')
})

test('mobile Mehr menu has dialog, focus, Escape, and close contracts', () => {
  const shell = read('src/components/layout/AppShell.tsx')
  assert.match(shell, /aria-controls="mobile-more-menu"/)
  assert.match(shell, /id="mobile-more-menu"/)
  assert.match(shell, /role="dialog"/)
  assert.match(shell, /aria-modal="true"/)
  assert.match(shell, /useRef/)
  assert.match(shell, /\.focus\(\)/)
  assert.match(shell, /event\.key [!=]+ 'Escape'/)
  assert.match(shell, /onClick=\{onNavigate\}/)
})

test('dashboard uses plain-language mobile prediction cards', () => {
  const row = read('src/features/dashboard/FixtureRow.tsx')
  assert.match(row, /Unser Tipp/)
  assert.match(row, /Buchmacherquote/)
  assert.match(row, /Elo-Modellquote · nicht wettbar/)
  assert.match(row, /Nicht verfügbar/)
  assert.match(row, /Keine Quote oder Modellwahrscheinlichkeit verfügbar\./)
  assert.match(row, /min-h-\[48px\]/)
  assert.match(row, /data-mobile-trailing/)
  assert.match(row, /\{trailing\}/)
})

test('global styling uses the approved palette and removes the blueprint grid', () => {
  const css = read('src/index.css')
  assert.match(css, /#315efb/i)
  assert.match(css, /#edf1f6/i)
  assert.doesNotMatch(css, /blueprint grid/i)
})

test('built index references assets that exist in the release artifact', () => {
  const index = read('dist/index.html')
  const assets = [...index.matchAll(/(?:src|href)="(\/assets\/[^"]+)"/g)].map(([, path]) => path)
  assert.ok(assets.length >= 2)
  for (const path of assets) assert.ok(existsSync(new URL(`../dist${path}`, import.meta.url)), path)
})
