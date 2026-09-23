export const COMPETITIONS = ['wc2026', 'ucl2026']

export function validCompetition(value) {
  return COMPETITIONS.includes(value) ? value : 'ucl2026'
}

export function competitionPath(path, competition) {
  const joiner = path.includes('?') ? '&' : '?'
  return `${path}${joiner}competition=${encodeURIComponent(competition)}`
}
