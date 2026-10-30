import { beforeEach, describe, expect, it } from 'vitest'

import {
  CSRF_COOKIE_NAME,
  CSRF_HEADER_NAME,
  buildCsrfHeader,
  getCsrfToken,
  isSafeMethod,
  readCookie
} from './cookies'

function setCookie(name: string, value: string): void {
  document.cookie = `${name}=${encodeURIComponent(value)}; path=/`
}

function clearCookies(): void {
  document.cookie.split(';').forEach(part => {
    const name = part.split('=')[0]?.trim()
    if (name) {
      document.cookie = `${name}=; path=/; max-age=0`
    }
  })
}

describe('cookies', () => {
  beforeEach(() => {
    clearCookies()
  })

  it('reads a cookie by name', () => {
    setCookie('cpumodel_csrf', 'csrf-value')

    expect(readCookie('cpumodel_csrf')).toBe('csrf-value')
    expect(readCookie('missing')).toBeNull()
  })

  it('decodes encoded cookie values', () => {
    document.cookie = 'cpumodel_csrf=token%2Bwith%2Bplus; path=/'

    expect(readCookie('cpumodel_csrf')).toBe('token+with+plus')
  })

  it('reads the csrf token convenience helper', () => {
    setCookie(CSRF_COOKIE_NAME, 'abc123')

    expect(getCsrfToken()).toBe('abc123')
  })

  it('identifies safe http methods', () => {
    expect(isSafeMethod('GET')).toBe(true)
    expect(isSafeMethod('head')).toBe(true)
    expect(isSafeMethod('OPTIONS')).toBe(true)
    expect(isSafeMethod('POST')).toBe(false)
    expect(isSafeMethod('PATCH')).toBe(false)
    expect(isSafeMethod()).toBe(true)
  })

  it('builds the X-CSRF-Token header for unsafe methods', () => {
    setCookie(CSRF_COOKIE_NAME, 'csrf-1')

    expect(buildCsrfHeader('post')).toEqual({ [CSRF_HEADER_NAME]: 'csrf-1' })
    expect(buildCsrfHeader('DELETE')).toEqual({ [CSRF_HEADER_NAME]: 'csrf-1' })
  })

  it('omits the csrf header for safe methods or missing cookie', () => {
    expect(buildCsrfHeader('GET')).toEqual({})

    setCookie(CSRF_COOKIE_NAME, 'csrf-2')
    expect(buildCsrfHeader('GET')).toEqual({})

    clearCookies()
    expect(buildCsrfHeader('POST')).toEqual({})
  })
})
