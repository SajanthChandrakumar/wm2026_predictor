export const DEFAULT_BOT_PARAMS = { market_weight: 0.7, risk: 0, draw_bias: 0, underdog_bias: 0 }

export function botFormState(customBot) {
  return {
    name: customBot?.exists ? (customBot.name || 'Mein Bot') : 'Mein Bot',
    params: customBot?.exists ? { ...DEFAULT_BOT_PARAMS, ...(customBot.params || {}) } : { ...DEFAULT_BOT_PARAMS },
  }
}
