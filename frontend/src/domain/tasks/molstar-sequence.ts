import { Structure, StructureElement, StructureProperties, Unit } from 'molstar/lib/mol-model/structure'

export interface SequenceResidue {
  key: string
  chain: string
  seqId: number
  compId: string
  oneLetter: string
  insCode?: string
}

export interface SequenceChain {
  chain: string
  residues: SequenceResidue[]
}

const THREE_TO_ONE_AMINO_ACID: Readonly<Record<string, string>> = {
  ALA: 'A',
  ARG: 'R',
  ASN: 'N',
  ASP: 'D',
  CYS: 'C',
  CYX: 'C',
  CYM: 'C',
  GLN: 'Q',
  GLU: 'E',
  GLY: 'G',
  HIS: 'H',
  HID: 'H',
  HIE: 'H',
  HIP: 'H',
  HSD: 'H',
  HSE: 'H',
  HSP: 'H',
  ILE: 'I',
  LEU: 'L',
  LYS: 'K',
  LYN: 'K',
  MET: 'M',
  MSE: 'M',
  PHE: 'F',
  PRO: 'P',
  PYL: 'O',
  SEC: 'U',
  SER: 'S',
  THR: 'T',
  TRP: 'W',
  TYR: 'Y',
  VAL: 'V',
  ASH: 'D',
  GLH: 'E',
  // Nucleic acids
  DA: 'A',
  DC: 'C',
  DG: 'G',
  DT: 'T',
  A: 'A',
  C: 'C',
  G: 'G',
  U: 'U',
  I: 'I',
}

export function toOneLetterResidue(compId: string): string {
  const normalized = compId.trim().toUpperCase()
  if (!normalized) {
    return '?'
  }
  return THREE_TO_ONE_AMINO_ACID[normalized] ?? (normalized.length === 1 ? normalized : 'X')
}

export function residueSelectionKey(chain: string, seqId: number): string {
  return `${chain}:${seqId}`
}

/** Extracts polymer chains and ordered residues from a Mol* `Structure` for PyMOL-style sequence selection. */
export function extractPolymerSequenceFromStructure(structure: Structure): SequenceChain[] {
  const chainOrder: string[] = []
  const residuesByChain = new Map<string, SequenceResidue[]>()
  const seenKeys = new Set<string>()
  const location = StructureElement.Location.create(structure)

  for (const unit of structure.units) {
    if (!Unit.isAtomic(unit)) {
      continue
    }

    const elements = unit.polymerElements.length > 0 ? unit.polymerElements : null
    if (!elements || elements.length === 0) {
      continue
    }

    location.unit = unit

    for (let i = 0; i < elements.length; i += 1) {
      location.element = elements[i]!
      const entityType = StructureProperties.entity.type(location)
      if (entityType !== 'polymer') {
        continue
      }

      const chain = StructureProperties.chain.auth_asym_id(location) || StructureProperties.chain.label_asym_id(location) || 'A'
      const seqId = StructureProperties.residue.auth_seq_id(location)
      const insCode = StructureProperties.residue.pdbx_PDB_ins_code(location) || undefined
      const key = residueSelectionKey(chain, seqId)

      if (seenKeys.has(key)) {
        continue
      }
      seenKeys.add(key)

      const compId = StructureProperties.residue.auth_comp_id(location) || StructureProperties.residue.label_comp_id(location) || 'UNK'
      const residue: SequenceResidue = {
        key,
        chain,
        seqId,
        compId,
        oneLetter: toOneLetterResidue(compId),
        ...(insCode ? { insCode } : {}),
      }

      let list = residuesByChain.get(chain)
      if (!list) {
        list = []
        residuesByChain.set(chain, list)
        chainOrder.push(chain)
      }
      list.push(residue)
    }
  }

  return chainOrder.map(chain => ({
    chain,
    residues: residuesByChain.get(chain) ?? [],
  }))
}

export interface ToggleSequenceSelectionParams {
  chains: readonly SequenceChain[]
  currentSelectedKeys: readonly string[]
  clickedChain: string
  clickedSeqId: number
  lastAnchorKey: string | null
  shiftKey: boolean
}

/**
 * Toggles a residue or selects a continuous range within the same chain when `shiftKey` is held.
 * Normal click toggles individual residues so users can multi-select without needing keyboard modifiers.
 */
export function toggleSequenceResidueSelection(params: ToggleSequenceSelectionParams): {
  selectedKeys: string[]
  anchorKey: string | null
} {
  const clickedKey = residueSelectionKey(params.clickedChain, params.clickedSeqId)

  if (params.shiftKey && params.lastAnchorKey) {
    const [anchorChain] = params.lastAnchorKey.split(':')
    if (anchorChain === params.clickedChain) {
      const chainData = params.chains.find(item => item.chain === params.clickedChain)
      if (chainData) {
        const anchorIndex = chainData.residues.findIndex(res => res.key === params.lastAnchorKey)
        const clickedIndex = chainData.residues.findIndex(res => res.key === clickedKey)
        if (anchorIndex >= 0 && clickedIndex >= 0) {
          const start = Math.min(anchorIndex, clickedIndex)
          const end = Math.max(anchorIndex, clickedIndex)
          const next = new Set(params.currentSelectedKeys)
          for (let i = start; i <= end; i += 1) {
            next.add(chainData.residues[i]!.key)
          }
          return {
            selectedKeys: [...next],
            anchorKey: clickedKey,
          }
        }
      }
    }
  }

  const next = new Set(params.currentSelectedKeys)
  if (next.has(clickedKey)) {
    next.delete(clickedKey)
    return {
      selectedKeys: [...next],
      anchorKey: null,
    }
  }

  next.add(clickedKey)
  return {
    selectedKeys: [...next],
    anchorKey: clickedKey,
  }
}

export function groupSelectedResiduesByChain(
  selectedKeys: readonly string[],
): Array<{ chain: string; seqIds: number[] }> {
  const map = new Map<string, Set<number>>()
  for (const key of selectedKeys) {
    const colonIndex = key.lastIndexOf(':')
    if (colonIndex <= 0) {
      continue
    }
    const chain = key.slice(0, colonIndex)
    const seqId = Number(key.slice(colonIndex + 1))
    if (!Number.isFinite(seqId)) {
      continue
    }
    let set = map.get(chain)
    if (!set) {
      set = new Set<number>()
      map.set(chain, set)
    }
    set.add(seqId)
  }

  return Array.from(map.entries()).map(([chain, set]) => ({
    chain,
    seqIds: [...set].sort((a, b) => a - b),
  }))
}

export function shouldShowSequenceRulerTick(index: number, seqId: number, total: number): boolean {
  if (index === 0 || index === total - 1) {
    return true
  }
  return seqId % 10 === 0
}
