export interface PocketVoxelBox {
  center: [number, number, number]
  halfSize: number
}

export interface PocketVoxelGrid {
  boxes: PocketVoxelBox[]
  color?: number
  radius?: number
}

const DEFAULT_HALF_SIZE = 0.85

/**
 * Pocket PDB files (LVPocket `pocket0.pdb`) are a set of 2Å-spaced dummy atoms
 * that mark the occupied voxels of a pocket. Turn each atom into one box so the
 * result view can render the pocket as a wireframe voxel grid instead of a
 * barely visible blob.
 */
export function parsePocketVoxelBoxes(
  pdbText: string,
  halfSize = DEFAULT_HALF_SIZE,
): PocketVoxelBox[] {
  const boxes: PocketVoxelBox[] = []

  for (const line of pdbText.split(/\r?\n/)) {
    if (!/^(ATOM|HETATM)/.test(line)) {
      continue
    }

    const x = Number(line.slice(30, 38).trim())
    const y = Number(line.slice(38, 46).trim())
    const z = Number(line.slice(46, 54).trim())

    if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(z)) {
      continue
    }

    boxes.push({ center: [x, y, z], halfSize })
  }

  return boxes
}
