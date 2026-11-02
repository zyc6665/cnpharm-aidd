import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

import { STAGE_STEP_MAP, STAGE_STEP_MAP_DEFAULT_ALLOWED } from './contract-bindings'

interface RegisteredCapability {
  readonly slug: string
  readonly capability: string
  readonly stage: string
}

/**
 * 直接读取后端静态登记表，确保前端步骤映射不会落后于后端新增的真实工具。
 * 只认 `    "slug": ToolCapability(` 形式的顶层条目；builtin-*（含 PLACEHOLDER）不参与映射。
 */
function readRegisteredCapabilities(): RegisteredCapability[] {
  const capabilitiesPath = resolve(process.cwd(), '..', 'backend', 'app', 'tools', 'capabilities.py')
  const source = readFileSync(capabilitiesPath, 'utf8')
  const parts = source.split(/\n {4}"([a-z0-9-]+)": ToolCapability\(/)
  const capabilities: RegisteredCapability[] = []

  for (let index = 1; index < parts.length; index += 2) {
    const slug = parts[index] ?? ''
    if (!slug || slug.startsWith('builtin-')) {
      continue
    }

    const block = parts[index + 1] ?? ''
    const capability = /capability="([^"]+)"/.exec(block)?.[1]
    const stage = /stage="([^"]+)"/.exec(block)?.[1]
    expect(capability, `${slug} 缺少 capability`).toBeTruthy()
    expect(stage, `${slug} 缺少 stage`).toBeTruthy()
    capabilities.push({ slug, capability: capability ?? '', stage: stage ?? '' })
  }

  return capabilities
}

describe('STAGE_STEP_MAP guard', () => {
  it('每个已登记的非 builtin 工具都能映射到工作流步骤，或显式登记为允许默认分支', () => {
    const capabilities = readRegisteredCapabilities()
    expect(capabilities.length).toBeGreaterThan(0)

    const unmapped = capabilities
      .filter(
        ({ slug, capability, stage }) =>
          !(stage in STAGE_STEP_MAP) &&
          !(capability in STAGE_STEP_MAP) &&
          !(slug in STAGE_STEP_MAP_DEFAULT_ALLOWED)
      )
      .map(({ slug, capability, stage }) => `${slug} (capability=${capability}, stage=${stage})`)

    expect(unmapped).toEqual([])
  })

  it('允许默认分支的白名单必须写明原因，且不与显式映射重复', () => {
    for (const [slug, reason] of Object.entries(STAGE_STEP_MAP_DEFAULT_ALLOWED)) {
      expect(reason.trim().length, `${slug} 缺少原因`).toBeGreaterThan(0)
      expect(STAGE_STEP_MAP[slug], `${slug} 已有显式映射，不应再进白名单`).toBeUndefined()
    }
  })
})
