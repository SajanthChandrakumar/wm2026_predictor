const STORAGE_KEY = 'wm2026_owner_secret'

/**
 * Owner unlock: opening the app with ?owner=<secret> once stores the secret
 * in localStorage on that device and strips it from the URL. Anyone who gets
 * a shared link without that param stays in read-only mode — the tip input
 * never renders and the write endpoint rejects the request server-side too.
 */
export function bootstrapOwnerSecret() {
  const params = new URLSearchParams(window.location.search)
  const secret = params.get('owner')
  if (!secret) return

  localStorage.setItem(STORAGE_KEY, secret)
  params.delete('owner')
  const rest = params.toString()
  const newUrl = window.location.pathname + (rest ? `?${rest}` : '') + window.location.hash
  window.history.replaceState({}, '', newUrl)
}

export function getOwnerSecret(): string | null {
  return localStorage.getItem(STORAGE_KEY)
}

export function isOwner(): boolean {
  return !!getOwnerSecret()
}
