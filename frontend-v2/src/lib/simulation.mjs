export function hasUclSimulationResults(data) {
  return Boolean(data && data.status !== 'unavailable' && Array.isArray(data.results))
}
