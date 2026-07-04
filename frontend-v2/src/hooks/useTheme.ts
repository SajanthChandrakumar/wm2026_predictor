import { useCallback, useEffect, useState } from 'react'

// Same localStorage key as the legacy frontend so the preference carries over.
const KEY = 'theme'

export function useTheme() {
  const [light, setLight] = useState(() => localStorage.getItem(KEY) === 'light')

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', light ? 'light' : 'dark')
    if (light) localStorage.setItem(KEY, 'light')
    else localStorage.removeItem(KEY)
  }, [light])

  const toggle = useCallback(() => setLight((v) => !v), [])
  return { light, toggle }
}
