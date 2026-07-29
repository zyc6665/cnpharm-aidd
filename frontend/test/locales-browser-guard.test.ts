import { test } from 'vitest'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

test('locale initialization guards browser-only storage access', () => {
  const source = readFileSync(resolve('src/locales/index.ts'), 'utf8')

  assert.equal(source.includes("typeof window !== 'undefined'"), true)
  assert.equal(source.includes("typeof localStorage !== 'undefined'"), true)
  assert.equal(source.includes('const savedLocale = isBrowser'), true)
})
