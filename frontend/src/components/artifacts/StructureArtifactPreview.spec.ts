import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import StructureArtifactPreview from './StructureArtifactPreview.vue'
import type { TypedArtifact } from '@/types/artifacts'

vi.mock('@/components/tasks/MoleculeViewer.vue', () => ({
  __esModule: true,
  default: {
    name: 'MoleculeViewer',
    props: ['scene', 'mode'],
    template: '<div data-testid="molecule-viewer" :data-mode="mode">{{ scene.entries[0].url }}</div>',
  },
}))

function makeArtifact(artifactType: TypedArtifact['artifact_type'], filename: string): TypedArtifact {
  return {
    id: 'artifact-1',
    project_id: 'project-1',
    artifact_type: artifactType,
    semantic_type: artifactType,
    name: filename,
    latest_version: {
      id: 'version-1',
      version: 1,
      filename,
      size_bytes: 1024,
      sha256: 'a'.repeat(64),
      status: 'available',
      created_at: '2026-11-23T00:00:00Z',
    },
    created_at: '2026-11-23T00:00:00Z',
    updated_at: '2026-11-23T00:00:00Z',
  }
}

describe('StructureArtifactPreview', () => {
  it('resolves protein mode for protein_structure artifacts even when role is omitted', async () => {
    const wrapper = mount(StructureArtifactPreview, {
      props: {
        artifact: makeArtifact('protein_structure', 'target.pdb'),
      },
    })

    await flushPromises()
    expect(wrapper.get('[data-testid="molecule-viewer"]').attributes('data-mode')).toBe('protein')
  })

  it('resolves molecule mode for ligand_structure artifacts and pocket mode for binding_pocket', async () => {
    const ligand = mount(StructureArtifactPreview, {
      props: {
        artifact: makeArtifact('ligand_structure', 'ligand.sdf'),
        role: 'ligand',
      },
    })
    await flushPromises()
    expect(ligand.get('[data-testid="molecule-viewer"]').attributes('data-mode')).toBe('molecule')

    const pocket = mount(StructureArtifactPreview, {
      props: {
        artifact: makeArtifact('binding_pocket', 'pocket.pdb'),
      },
    })
    await flushPromises()
    expect(pocket.get('[data-testid="molecule-viewer"]').attributes('data-mode')).toBe('pocket')
  })

  it('respects an explicit mode prop override', async () => {
    const wrapper = mount(StructureArtifactPreview, {
      props: {
        artifact: makeArtifact('protein_structure', 'complex.pdb'),
        mode: 'docking',
      },
    })
    await flushPromises()
    expect(wrapper.get('[data-testid="molecule-viewer"]').attributes('data-mode')).toBe('docking')
  })
})
