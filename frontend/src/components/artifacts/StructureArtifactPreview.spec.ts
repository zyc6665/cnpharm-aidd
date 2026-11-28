import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import StructureArtifactPreview from './StructureArtifactPreview.vue'
import type { ArtifactVersionFile, TypedArtifact } from '@/types/artifacts'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (key: string) => key,
  }),
}))

vi.mock('@/components/tasks/MoleculeViewer.vue', () => ({
  __esModule: true,
  default: {
    name: 'MoleculeViewer',
    props: ['scene', 'mode', 'frameTimesPs', 'canExportMovie'],
    emits: ['export-movie', 'entry-unavailable'],
    template:
      '<div data-testid="molecule-viewer" :data-mode="mode" :data-prefer-complex="scene.entries[0].preferComplexRepresentation" :data-fallback="String(scene.entries[0].fallbackOnFailure)" :data-can-export="canExportMovie" :data-frame-times="JSON.stringify(frameTimesPs)" @click="$emit(\'export-movie\')">{{ scene.entries[0].url }}<button data-testid="fail-entry" @click.stop="$emit(\'entry-unavailable\', scene.entries[0].key)">fail</button></div>',
  },
}))

function makeFile(role: string, filename: string, isPrimary = false): ArtifactVersionFile {
  return {
    id: `file-${role}`,
    role,
    file_id: `file-${role}`,
    is_primary: isPrimary,
    sort_order: 0,
    filename,
    download_url: `/api/v1/files/${role}/download`,
  }
}

function makeArtifact(
  artifactType: TypedArtifact['artifact_type'],
  filename: string,
  files?: ArtifactVersionFile[],
): TypedArtifact {
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
      ...(files ? { files } : {}),
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

  it('prefers the multi-frame movie file and forwards playback props', async () => {
    const wrapper = mount(StructureArtifactPreview, {
      props: {
        artifact: makeArtifact('md_trajectory', 'md_trajectory.pdb', [
          makeFile('topology_pdb', 'topology.pdb'),
          makeFile('trajectory_movie_pdb', 'trajectory_movie.pdb'),
        ]),
        preferredFileRoles: ['trajectory_movie_pdb', 'topology_pdb'],
        frameTimesPs: [0, 2, 4],
        canExportMovie: true,
      },
    })

    await flushPromises()
    const viewer = wrapper.get('[data-testid="molecule-viewer"]')
    expect(viewer.attributes('data-prefer-complex')).toBe('true')
    expect(viewer.attributes('data-can-export')).toBe('true')
    expect(viewer.attributes('data-frame-times')).toBe('[0,2,4]')
    expect(viewer.text()).toContain('/api/v1/files/trajectory_movie_pdb/download')

    await viewer.trigger('click')
    expect(wrapper.emitted('export-movie')).toHaveLength(1)
  })

  it('falls back to the topology file without complex representation for legacy tasks', async () => {
    const wrapper = mount(StructureArtifactPreview, {
      props: {
        artifact: makeArtifact('md_trajectory', 'md_trajectory.pdb', [
          makeFile('topology_pdb', 'topology.pdb', true),
        ]),
        preferredFileRoles: ['trajectory_movie_pdb', 'topology_pdb'],
        canExportMovie: false,
      },
    })

    await flushPromises()
    const viewer = wrapper.get('[data-testid="molecule-viewer"]')
    expect(viewer.attributes('data-prefer-complex')).toBe('false')
    expect(viewer.attributes('data-can-export')).toBe('false')
    expect(viewer.text()).toContain('/api/v1/files/topology_pdb/download')
  })

  it('marks entries fallback-capable so one broken file cannot blank the viewer', async () => {
    const wrapper = mount(StructureArtifactPreview, {
      props: {
        artifact: makeArtifact('md_trajectory', 'md_trajectory.pdb', [
          makeFile('topology_pdb', 'topology.pdb', true),
        ]),
        preferredFileRoles: ['trajectory_movie_pdb', 'topology_pdb'],
      },
    })

    await flushPromises()
    expect(wrapper.get('[data-testid="molecule-viewer"]').attributes('data-fallback')).toBe('true')
  })

  it('falls back to the topology file and reports movie unavailable when the movie fails', async () => {
    const wrapper = mount(StructureArtifactPreview, {
      props: {
        artifact: makeArtifact('md_trajectory', 'md_trajectory.pdb', [
          makeFile('trajectory_movie_pdb', 'trajectory_movie.pdb'),
          makeFile('topology_pdb', 'topology.pdb'),
        ]),
        preferredFileRoles: ['trajectory_movie_pdb', 'topology_pdb'],
        frameTimesPs: [0, 2, 4],
        canExportMovie: true,
      },
    })

    await flushPromises()
    expect(wrapper.get('[data-testid="molecule-viewer"]').text()).toContain(
      '/api/v1/files/trajectory_movie_pdb/download'
    )

    await wrapper.get('[data-testid="fail-entry"]').trigger('click')
    await flushPromises()

    const viewer = wrapper.get('[data-testid="molecule-viewer"]')
    expect(viewer.text()).toContain('/api/v1/files/topology_pdb/download')
    expect(viewer.attributes('data-prefer-complex')).toBe('false')
    expect(wrapper.emitted('movie-unavailable')).toHaveLength(1)
  })

  it('shows an unavailable alert when every candidate file fails', async () => {
    const wrapper = mount(StructureArtifactPreview, {
      props: {
        artifact: makeArtifact('md_trajectory', 'md_trajectory.pdb', [
          makeFile('trajectory_movie_pdb', 'trajectory_movie.pdb'),
          makeFile('topology_pdb', 'topology.pdb'),
        ]),
        preferredFileRoles: ['trajectory_movie_pdb', 'topology_pdb'],
      },
    })

    await flushPromises()
    await wrapper.get('[data-testid="fail-entry"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-testid="fail-entry"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="molecule-viewer"]').exists()).toBe(false)
    expect(
      wrapper.get('[data-testid="structure-preview-unavailable"]').attributes('message')
    ).toBe('artifactAssets.structurePreview.unavailable')
  })
})
