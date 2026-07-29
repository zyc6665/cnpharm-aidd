const TOKEN_KEY = 'cpumodel_token'
const REFRESH_TOKEN_KEY = 'cpumodel_refresh_token'

export const AUTH_CLEARED_EVENT = 'cpumodel-auth-cleared'

const getStorageItem = (key: string): string | null => {
  return typeof localStorage === 'undefined' ? null : localStorage.getItem(key)
}

const setStorageItem = (key: string, value: string): void => {
  if (typeof localStorage !== 'undefined') {
    localStorage.setItem(key, value)
  }
}

const removeStorageItem = (key: string): void => {
  if (typeof localStorage !== 'undefined') {
    localStorage.removeItem(key)
  }
}

export const getToken = (): string | null => getStorageItem(TOKEN_KEY)

export const setToken = (token: string): void => {
  setStorageItem(TOKEN_KEY, token)
}

export const getRefreshToken = (): string | null => getStorageItem(REFRESH_TOKEN_KEY)

export const setRefreshToken = (token: string): void => {
  setStorageItem(REFRESH_TOKEN_KEY, token)
}

export const clearAuthStorage = (): void => {
  removeStorageItem(TOKEN_KEY)
  removeStorageItem(REFRESH_TOKEN_KEY)

  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent(AUTH_CLEARED_EVENT))
  }
}
