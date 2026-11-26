import { describe, expect, it } from 'vitest'
import { parsePocketGeometry } from '@/domain/pockets/pocket-geometry'
import { parseFragmentMolecule } from './fragment-graph'
import { createSampleDesignFiles, SAMPLE_LIGAND_SDF, SAMPLE_POCKET_PDB, SAMPLE_RECEPTOR_PDB } from './sample-inputs'

function readFile(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result))
    reader.onerror = () => reject(reader.error)
    reader.readAsText(file)
  })
}

describe('createSampleDesignFiles', () => {
  it('creates fresh local uploads from the bundled structures', async () => {
    const sample = createSampleDesignFiles()
    expect(sample.receptorFile.name).toBe('receptor.pdb')
    expect(sample.pocketFile.name).toBe('pocket0.pdb')
    expect(sample.ligandFile.name).toBe('egfr_ligand.sdf')
    expect(sample.ligandFile).not.toBe(createSampleDesignFiles().ligandFile)
    expect(await Promise.all([sample.receptorFile, sample.pocketFile, sample.ligandFile].map(readFile)))
      .toEqual([SAMPLE_RECEPTOR_PDB, SAMPLE_POCKET_PDB, SAMPLE_LIGAND_SDF])
  })

  it('matches the pocket parser and places the 3D ligand inside the box', () => {
    const sample = createSampleDesignFiles()
    expect(parsePocketGeometry(SAMPLE_POCKET_PDB)).toEqual({
      center: sample.pocketCenter, boxSize: sample.pocketBoxSize, pointCount: 6, source: 'unl'
    })
    expect(sample.pocketCenter).toEqual({ x: 22, y: 0.25, z: 52.79 })
    expect(sample.pocketBoxSize).toEqual({ x: 10, y: 8, z: 8 })
    expect(parseFragmentMolecule(SAMPLE_RECEPTOR_PDB, sample.receptorFile.name)?.atoms).toHaveLength(27)
    const ligand = parseFragmentMolecule(SAMPLE_LIGAND_SDF, sample.ligandFile.name)!
    expect(ligand.atoms).toHaveLength(13)
    expect(ligand.bonds).toHaveLength(15)
    expect(new Set(ligand.atoms.map(atom => atom.z)).size).toBeGreaterThan(1)
    for (const atom of ligand.atoms) {
      for (const axis of ['x', 'y', 'z'] as const) {
        expect(Math.abs(atom[axis] - sample.pocketCenter[axis])).toBeLessThan(sample.pocketBoxSize[axis] / 2)
      }
    }
  })
})
