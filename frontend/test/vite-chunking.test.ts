import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { test } from 'vitest'
import assert from 'node:assert/strict'

test('vite config splits heavy Molstar modules into dedicated async chunks', () => {
  const source = readFileSync(resolve('vite.config.ts'), 'utf8')

  for (const chunkName of [
    'molstar-viewer',
    'molstar-rendering',
    'molstar-model',
    'molstar-core'
  ]) {
    assert.equal(source.includes(`return '${chunkName}'`), true, `missing ${chunkName}`)
  }

  assert.equal(source.includes("return 'molstar'"), false)
})
