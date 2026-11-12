/**
 * 残基的类别与理化性质（前端展示用）。
 *
 * 为什么要在前端放一份：关键残基列表里「LEU15 0.86」对人来说只是三个字母加一个数字，
 * 研发人员要的是「亮氨酸、疏水、Kyte–Doolittle 3.8」这种能直接参与判断的信息。
 * 这份表与后端 `app/services/pocket_residue_scoring.py` 的 `KYTE_DOOLITTLE` 同源，
 * 只做展示，不参与打分——打分口径的单一真源仍在后端。
 */

export type ResidueCategory = '疏水' | '芳香' | '极性' | '酸性' | '碱性' | '特殊'

export interface ResidueProperty {
  /** 三字母码（大写） */
  code: string
  /** 中文名 */
  chinese: string
  /** 侧链类别 */
  category: ResidueCategory
  /** Kyte–Doolittle 疏水指数（越大越疏水） */
  hydropathy: number
  /** 一句话性质说明 */
  note: string
}

export const RESIDUE_PROPERTIES: Record<string, ResidueProperty> = {
  ALA: { code: 'ALA', chinese: '丙氨酸', category: '疏水', hydropathy: 1.8, note: '侧链最小，常出现在口袋底部' },
  ARG: { code: 'ARG', chinese: '精氨酸', category: '碱性', hydropathy: -4.5, note: '长侧链胍基，常与酸性残基成盐桥' },
  ASN: { code: 'ASN', chinese: '天冬酰胺', category: '极性', hydropathy: -3.5, note: '酰胺侧链，可提供氢键' },
  ASP: { code: 'ASP', chinese: '天冬氨酸', category: '酸性', hydropathy: -3.5, note: '带负电，常见于金属配位与盐桥' },
  CYS: { code: 'CYS', chinese: '半胱氨酸', category: '极性', hydropathy: 2.5, note: '巯基可成二硫键，也易被共价修饰' },
  GLN: { code: 'GLN', chinese: '谷氨酰胺', category: '极性', hydropathy: -3.5, note: '酰胺侧链，氢键供体与受体兼具' },
  GLU: { code: 'GLU', chinese: '谷氨酸', category: '酸性', hydropathy: -3.5, note: '带负电，亲水性强' },
  GLY: { code: 'GLY', chinese: '甘氨酸', category: '特殊', hydropathy: -0.4, note: '无侧链，主链最柔顺' },
  HIS: { code: 'HIS', chinese: '组氨酸', category: '碱性', hydropathy: -3.2, note: '咪唑环可配位金属、可质子化' },
  ILE: { code: 'ILE', chinese: '异亮氨酸', category: '疏水', hydropathy: 4.5, note: '支链疏水，常构成疏水口袋壁' },
  LEU: { code: 'LEU', chinese: '亮氨酸', category: '疏水', hydropathy: 3.8, note: '支链疏水，口袋中占比最高的残基之一' },
  LYS: { code: 'LYS', chinese: '赖氨酸', category: '碱性', hydropathy: -3.9, note: '长侧链氨基，带正电、易成盐桥' },
  MET: { code: 'MET', chinese: '甲硫氨酸', category: '疏水', hydropathy: 1.9, note: '含硫，柔顺且可极化' },
  PHE: { code: 'PHE', chinese: '苯丙氨酸', category: '芳香', hydropathy: 2.8, note: '苯环，常见 π–π 堆积' },
  PRO: { code: 'PRO', chinese: '脯氨酸', category: '特殊', hydropathy: -1.6, note: '环状，限制主链构象' },
  SER: { code: 'SER', chinese: '丝氨酸', category: '极性', hydropathy: -0.8, note: '羟甲基，氢键与磷酸化位点' },
  THR: { code: 'THR', chinese: '苏氨酸', category: '极性', hydropathy: -0.7, note: '羟基侧链，氢键供体' },
  TRP: { code: 'TRP', chinese: '色氨酸', category: '芳香', hydropathy: -0.9, note: '吲哚环，体积大、可形成 π 堆积' },
  TYR: { code: 'TYR', chinese: '酪氨酸', category: '芳香', hydropathy: -1.3, note: '酚羟基，氢键与 π 堆积兼具' },
  VAL: { code: 'VAL', chinese: '缬氨酸', category: '疏水', hydropathy: 4.2, note: '支链疏水，常见于口袋核心' }
}

const UNKNOWN: ResidueProperty = {
  code: '',
  chinese: '未知残基',
  category: '特殊',
  hydropathy: 0,
  note: '非标准或修饰残基'
}

/** 按三字母码取残基性质；大小写不敏感，未知残基返回占位信息而不抛错。 */
export function residuePropertyOf(name: string | null | undefined): ResidueProperty {
  const key = (name ?? '').trim().toUpperCase()
  return RESIDUE_PROPERTIES[key] ?? { ...UNKNOWN, code: key }
}

/** 残基类别的展示色：疏水偏暖、带电偏冷，让性质一眼可分。 */
export function residueCategoryColor(category: ResidueCategory): string {
  switch (category) {
    case '疏水':
      return '#d48806'
    case '芳香':
      return '#9254de'
    case '极性':
      return '#13c2c2'
    case '酸性':
      return '#f5222d'
    case '碱性':
      return '#2f54eb'
    default:
      return '#8c8c8c'
  }
}
