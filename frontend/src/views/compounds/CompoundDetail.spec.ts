import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CompoundDetail from './CompoundDetail.vue'
import type { Compound, CompoundSearchResult } from '@/types/compounds'

const getCompoundMock = vi.fn()
const searchCompoundsMock = vi.fn()

vi.mock('@/api/compounds', () => ({
  getCompound: (...args: unknown[]) => getCompoundMock(...args),
  searchCompounds: (...args: unknown[]) => searchCompoundsMock(...args)
}))

vi.mock('ant-design-vue', () => ({
  message: { warning: vi.fn(), error: vi.fn(), success: vi.fn() }
}))

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string) => key })
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({
    params: { compoundId: 'c-0' },
    query: { project_id: 'project-1' }
  })
}))

/** `a-table` 用带 `bodyCell` 插槽的轻量替身，让模板里的 `record.*` 取值真正被渲染出来。 */
const ATableStub = {
  props: ['columns', 'dataSource', 'rowKey', 'pagination', 'size', 'locale'],
  template: `<div class="a-table">
    <div class="a-table-head">
      <span v-for="column in columns" :key="column.key" class="a-table-th">{{ column.title }}</span>
    </div>
    <div
      v-for="(record, index) in dataSource"
      :key="index"
      class="a-table-row"
    >
      <span v-for="column in columns" :key="column.key" class="a-table-td">
        <slot name="bodyCell" :column="column" :record="record" :index="index" />
      </span>
    </div>
  </div>`
}

const RouterLinkStub = {
  props: ['to'],
  template: '<a class="router-link" :href="String(to)"><slot /></a>'
}

const PassThrough = { template: '<div><slot /></div>' }

const stubs = {
  ATable: ATableStub,
  RouterLink: RouterLinkStub,
  AppPageHeader: PassThrough,
  SkeletonDetail: true,
  Smiles2DCell: true,
  AAlert: PassThrough,
  ASpace: PassThrough,
  ASpin: PassThrough,
  ARow: PassThrough,
  ACol: PassThrough,
  AForm: PassThrough,
  AFormItem: PassThrough,
  AInput: true,
  AInputNumber: true,
  AButton: { template: '<button type="button"><slot /></button>' },
  ADescriptions: PassThrough,
  ADescriptionsItem: PassThrough
}

function compound(): Compound {
  return {
    id: 'c-0',
    name: 'Query compound',
    inchikey: 'LFQSCWFLJHTTHZ-UHFFFAOYSA-N',
    canonical_smiles: 'CCO',
    mol_formula: 'C2H6O',
    mol_weight: 46.069,
    props: { logP: -0.3, TPSA: 20.23, HBD: 1, HBA: 1, RotB: 0, QED: 0.407 },
    structure_urn: null,
    created_at: '2026-10-01T00:00:00Z'
  }
}

function similarityResult(): CompoundSearchResult {
  return {
    query: { smiles: 'CCO' },
    fingerprint: { algorithm: 'ECFP4', bits: 2048 },
    items: [
      {
        similarity: 0.8,
        compound: {
          id: 'c-1',
          name: 'Ethanol',
          inchikey: 'LFQSCWFLJHTTHZ-UHFFFAOYSA-N',
          canonical_smiles: 'CCO',
          mol_formula: 'C2H6O',
          mol_weight: 46.069,
          props: { logP: -0.3, TPSA: 20.23, HBD: 1, HBA: 1, RotB: 0, QED: 0.407 },
          structure_urn: null,
          created_at: '2026-10-01T00:00:00Z'
        }
      }
    ]
  }
}

async function mountPage() {
  const wrapper = mount(CompoundDetail, { global: { stubs } })
  await flushPromises()
  return wrapper
}

describe('CompoundDetail 相似性检索表格', () => {
  beforeEach(() => {
    getCompoundMock.mockReset()
    searchCompoundsMock.mockReset()
    getCompoundMock.mockResolvedValue({ code: 0, message: 'ok', data: compound() })
    searchCompoundsMock.mockResolvedValue({ code: 0, message: 'ok', data: similarityResult() })
  })

  it('按 record.compound 渲染命中项并给出可点击的化合物链接', async () => {
    const wrapper = await mountPage()

    await wrapper.get('[data-testid="compound-similarity-submit"]').trigger('click')
    await flushPromises()

    // 页面上有两张表（7 项性质 + 相似性命中），只断言相似性表格的行
    const table = wrapper.get('[data-testid="compound-similarity-table"]')
    const rows = table.findAll('.a-table-row')
    expect(rows).toHaveLength(1)

    const row = rows[0]!
    const text = row.text()
    expect(text).toContain('Ethanol')
    expect(text).toContain('LFQSCWFLJHTTHZ-UHFFFAOYSA-N')
    expect(text).toContain('46.069')
    expect(text).toContain('0.800')

    const link = row.get('.router-link')
    expect(link.attributes('href')).toContain('c-1')
  })

  it('相似度检索命中时 query 与阈值沿用页面状态', async () => {
    const wrapper = await mountPage()

    await wrapper.get('[data-testid="compound-similarity-submit"]').trigger('click')
    await flushPromises()

    expect(searchCompoundsMock).toHaveBeenCalledTimes(1)
    const firstCall = searchCompoundsMock.mock.calls[0]!
    expect(firstCall[0]).toEqual({ smiles: 'CCO' })
  })
})
