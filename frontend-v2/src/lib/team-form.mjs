export function withRatingBaselines(history = {}, ratings = {}) {
  const merged = { ...history }
  for (const [team, rating] of Object.entries(ratings)) {
    if (!merged[team]?.length && Number.isFinite(rating?.elo)) {
      merged[team] = [{ timestamp: 0, match_id: 'baseline', elo: rating.elo }]
    }
  }
  return merged
}
