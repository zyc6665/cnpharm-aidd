import { test } from 'vitest'
import assert from 'node:assert/strict'
import { readFileSync, readdirSync } from 'node:fs'
import { resolve } from 'node:path'

const workflowComponentDir = resolve('src/components/workflow')
const lightOnlyNeutralValues = [
  'rgba(255, 255, 255, 0.',
  'rgba(250, 252, 255',
  'rgba(248, 251, 255',
  'rgba(248, 250, 252',
  'rgba(247, 250, 255',
  'rgba(246, 250, 255',
  'rgba(246, 249, 255',
  'rgba(245, 249, 255',
  'rgba(244, 248, 255',
  'rgba(230, 244, 255',
  'rgba(228, 235, 244',
  'rgba(226, 232, 240',
  'rgba(220, 227, 240',
  'rgba(215, 224, 238',
  'rgba(214, 224, 238',
  'rgba(210, 221, 236',
  'rgba(210, 220, 235',
  'rgba(205, 217, 235',
  '#eef2f7',
  '#355070'
]

test('workflow components use semantic tokens instead of light-only neutral surfaces', () => {
  const violations = readdirSync(workflowComponentDir)
    .filter(file => file.endsWith('.vue'))
    .flatMap(file => {
      const source = readFileSync(resolve(workflowComponentDir, file), 'utf8')
      return lightOnlyNeutralValues
        .filter(value => source.includes(value))
        .map(value => `${file}: ${value}`)
    })

  assert.deepEqual(violations, [])
})
