export function hasScoreMatrix(matrix) {
  if (!matrix || typeof matrix !== 'object' || Array.isArray(matrix)) return false
  return Object.values(matrix).some((row) => row && typeof row === 'object' && !Array.isArray(row)
    && Object.values(row).some((value) => Number.isFinite(Number(value)) && Number(value) > 0))
}
