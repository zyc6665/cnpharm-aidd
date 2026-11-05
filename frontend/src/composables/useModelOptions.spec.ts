import { describe, it, expect, vi, beforeEach } from 'vitest'
vi.mock('@/api/tools', () => ({ getToolList: vi.fn() }))
import { getToolList } from '@/api/tools'
import { useModelOptions } from './useModelOptions'

function tool(slug: string, family: string, name = slug) {
  return { id: slug, slug, name, status: 'published', current_version: { id: `${slug}-v`, version: '1.0.0' }, contract: { model_family: family } }
}

describe('useModelOptions', () => {
  beforeEach(() => {
    vi.mocked(getToolList).mockReset()
    localStorage.clear()
  })

  it('lists only published tools in the family and selects the default', async () => {
    vi.mocked(getToolList).mockResolvedValue({
      data: { items: [tool('a', 'molecule_generation', 'A'), tool('b', 'molecule_generation', 'B'), tool('x', 'peptide_design')] },
    } as never)
    const m = useModelOptions('molecule_generation', { defaultSlug: 'a' })
    await m.load()
    expect(m.options.value.map(o => o.slug)).toEqual(['a', 'b'])
    expect(m.selectedSlug.value).toBe('a')
    expect(m.hasChoice.value).toBe(true)
  })

  it('remembers the last selection from localStorage', async () => {
    vi.mocked(getToolList).mockResolvedValue({ data: { items: [tool('a', 'molecule_generation'), tool('b', 'molecule_generation')] } } as never)
    localStorage.setItem('design:model:molecule_generation', 'b')
    const m = useModelOptions('molecule_generation', { defaultSlug: 'a' })
    await m.load()
    expect(m.selectedSlug.value).toBe('b')
  })

  it('falls back to the default slug when no tools are registered', async () => {
    vi.mocked(getToolList).mockResolvedValue({ data: { items: [] } } as never)
    const m = useModelOptions('molecule_generation', { defaultSlug: 'pocket2mol-pocket-ligand-generation' })
    await m.load()
    expect(m.options.value).toEqual([])
    expect(m.selectedSlug.value).toBe('pocket2mol-pocket-ligand-generation')
    expect(m.hasChoice.value).toBe(false)
  })

  it('groups by known slug when contract.model_family is missing (backend not upgraded)', async () => {
    vi.mocked(getToolList).mockResolvedValue({
      data: {
        items: [
          { id: 'p1', slug: 'pocket2mol-pocket-ligand-generation', name: 'Pocket2Mol', status: 'published', current_version: { id: 'v', version: '2.0.0' } },
          { id: 'p2', slug: 'therapainter-peptide-prediction', name: 'TheraPainter', status: 'published' },
        ],
      },
    } as never)
    const m = useModelOptions('molecule_generation', { defaultSlug: 'pocket2mol-pocket-ligand-generation' })
    await m.load()
    expect(m.options.value.map(o => o.slug)).toEqual(['pocket2mol-pocket-ligand-generation'])
    expect(m.options.value[0]!.name).toBe('Pocket2Mol')
  })
})
