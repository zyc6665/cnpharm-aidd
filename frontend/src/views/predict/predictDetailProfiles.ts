/**
 * 单分子预测结果详情的展示 profile。
 *
 * 结果详情按「模型能力族（model_family）」选择，而不是按具体 tool slug：
 * - 同一能力族的不同模型（例如 msign / boltz2 亲和力）复用同一套字段与分组；
 * - 新模型只要登记到已知能力族，就自动获得对应详情，无需新增页面；
 * - 未知能力族走通用 profile，按 CSV 列自动展示，保证不会白屏。
 */
export type PredictDetailPolarity = 'good' | 'risk' | 'neutral'

export interface PredictDetailMetricDef {
  /** 优先本地化的标签 key；缺省用 label。 */
  labelKey?: string
  label?: string
  aliases: string[]
  polarity?: PredictDetailPolarity
  unit?: string
}

export interface PredictDetailSection {
  titleKey: string
  defs: PredictDetailMetricDef[]
}

export interface PredictDetailProfile {
  key: string
  titleKey: string
  showSmiles: boolean
  showRadar: boolean
  basic: PredictDetailSection | null
  sections: PredictDetailSection[]
  radar: Array<[string, string[]]>
  /** true = 按 CSV 列自动生成分组，用于未知能力族。 */
  generic?: boolean
}

const ADMET_BASIC: PredictDetailSection = {
  titleKey: 'predict.result.detailSectionBasic',
  defs: [
    { label: 'Molecular Weight (MW)', aliases: ['mol_weight', 'molecularweight', 'mw'], unit: 'g/mol' },
    { label: 'LogP', aliases: ['logp', 'xlogp'] },
    { label: 'TPSA', aliases: ['tpsa'], unit: 'Å²' },
    { label: 'H-bond Donors', aliases: ['hbd', 'hbonddonors'] },
    { label: 'H-bond Acceptors', aliases: ['hba', 'hbondacceptors'] },
    { label: 'Rotatable Bonds', aliases: ['rotb', 'rotatablebonds'] },
    { label: 'QED', aliases: ['qed'] },
    { label: 'SA Score', aliases: ['sa_score', 'sascore'] },
    { label: 'InChIKey', aliases: ['inchi_key', 'inchikey'] }
  ]
}

const ADMET_SECTIONS: PredictDetailSection[] = [
  {
    titleKey: 'predict.result.detailSectionAbsorption',
    defs: [
      { label: 'F20', aliases: ['F20'], polarity: 'good' },
      { label: 'F30', aliases: ['F30'], polarity: 'good' },
      { label: 'HIA', aliases: ['HIA'], polarity: 'good' },
      { label: 'PAMPA', aliases: ['PAMPA_NCATS', 'PAMPA'], polarity: 'good' },
      { label: 'P-gp Inhibitor', aliases: ['Pgp-inhibitor', 'PgpInhibitor'], polarity: 'risk' },
      { label: 'P-gp Substrate', aliases: ['Pgp-substrate', 'PgpSubstrate'] },
      { label: 'Caco-2 Permeability', aliases: ['Caco2', 'Caco-2'] },
      { label: 'MDCK Permeability (cm/s)', aliases: ['MDCK Permeability', 'MDCK'] }
    ]
  },
  {
    titleKey: 'predict.result.detailSectionDistribution',
    defs: [
      { label: 'BBB', aliases: ['BBB'], polarity: 'good' },
      { label: 'Fraction Unbound (Fu)', aliases: ['Fu'], polarity: 'good' },
      { label: 'PPB', aliases: ['PPB'], unit: '%' },
      { label: 'VDss', aliases: ['VD', 'VDss'], unit: 'L/kg' }
    ]
  },
  {
    titleKey: 'predict.result.detailSectionMetabolism',
    defs: [
      { label: 'CYP1A2 Inhibitor', aliases: ['CYP1A2 inhibitor'], polarity: 'risk' },
      { label: 'CYP1A2 Substrate', aliases: ['CYP1A2 substrate'] },
      { label: 'CYP2C19 Inhibitor', aliases: ['CYP2C19 inhibitor'], polarity: 'risk' },
      { label: 'CYP2C19 Substrate', aliases: ['CYP2C19 substrate'] },
      { label: 'CYP2C9 Inhibitor', aliases: ['CYP2C9 inhibitor'], polarity: 'risk' },
      { label: 'CYP2C9 Substrate', aliases: ['CYP2C9 substrate'] },
      { label: 'CYP2D6 Inhibitor', aliases: ['CYP2D6 inhibitor'], polarity: 'risk' },
      { label: 'CYP2D6 Substrate', aliases: ['CYP2D6 substrate'] },
      { label: 'CYP3A4 Inhibitor', aliases: ['CYP3A4 inhibitor'], polarity: 'risk' },
      { label: 'CYP3A4 Substrate', aliases: ['CYP3A4 substrate'] }
    ]
  },
  {
    titleKey: 'predict.result.detailSectionExcretion',
    defs: [
      { label: 'T1/2', aliases: ['T0.5', 'T1/2', 'halflife'], unit: 'h' },
      { label: 'CL', aliases: ['CL', 'clearance'], unit: 'mL/min/kg' }
    ]
  },
  {
    titleKey: 'predict.result.detailSectionToxicity',
    defs: [
      { label: 'AMES', aliases: ['AMES'], polarity: 'risk' },
      { label: 'Carcinogenicity', aliases: ['Carcinogenicity'], polarity: 'risk' },
      { label: 'ClinTox', aliases: ['ClinTox'], polarity: 'risk' },
      { label: 'DILI', aliases: ['DILI'], polarity: 'risk' },
      { label: 'Eye Corrosion', aliases: ['Eye Corrosion'], polarity: 'risk' },
      { label: 'Eye Irritation', aliases: ['Eye Irritation'], polarity: 'risk' },
      { label: 'FDAMDD', aliases: ['FDAMDD'], polarity: 'risk' },
      { label: 'H-HT-2', aliases: ['H-HT-2'], polarity: 'risk' },
      { label: 'hERG Blockers', aliases: ['hERG'], polarity: 'risk' },
      { label: 'Respiratory Toxicity', aliases: ['Respiratory'], polarity: 'risk' },
      { label: 'ROA', aliases: ['ROA'], polarity: 'risk' },
      { label: 'Skin Sensitization', aliases: ['Skin Sensitization'], polarity: 'risk' }
    ]
  },
  {
    titleKey: 'predict.result.detailSectionTox21',
    defs: [
      { label: 'NR-AhR', aliases: ['NR-AhR'], polarity: 'risk' },
      { label: 'NR-AR', aliases: ['NR-AR'], polarity: 'risk' },
      { label: 'NR-AR-LBD', aliases: ['NR-AR-LBD'], polarity: 'risk' },
      { label: 'NR-Aromatase', aliases: ['NR-Aromatase'], polarity: 'risk' },
      { label: 'NR-ER', aliases: ['NR-ER'], polarity: 'risk' },
      { label: 'NR-ER-LBD', aliases: ['NR-ER-LBD'], polarity: 'risk' },
      { label: 'NR-PPAR-gamma', aliases: ['NR-PPAR-gamma'], polarity: 'risk' },
      { label: 'SR-ARE', aliases: ['SR-ARE'], polarity: 'risk' },
      { label: 'SR-ATAD5', aliases: ['SR-ATAD5'], polarity: 'risk' },
      { label: 'SR-HSE', aliases: ['SR-HSE'], polarity: 'risk' },
      { label: 'SR-MMP', aliases: ['SR-MMP'], polarity: 'risk' },
      { label: 'SR-p53', aliases: ['SR-p53'], polarity: 'risk' }
    ]
  },
  {
    titleKey: 'predict.result.detailSectionEcotoxicity',
    defs: [
      { label: 'BCF', aliases: ['BCF'], polarity: 'risk' },
      { label: 'IGC50', aliases: ['IGC50'], polarity: 'risk' },
      { label: 'LC50', aliases: ['LC50'], polarity: 'risk' },
      { label: 'LC50DM', aliases: ['LC50DM'], polarity: 'risk' }
    ]
  },
  {
    titleKey: 'predict.result.detailSectionLd50',
    defs: [{ label: 'LD50 (Zhu)', aliases: ['LD50_zhu', 'LD50'], unit: 'log(mol/kg)' }]
  }
]

export const ADMET_DETAIL_PROFILE: PredictDetailProfile = {
  key: 'admet_prediction',
  titleKey: 'predict.result.detailProfileAdmet',
  showSmiles: true,
  showRadar: true,
  basic: ADMET_BASIC,
  sections: ADMET_SECTIONS,
  radar: [
    ['HIA', ['HIA']],
    ['F20', ['F20']],
    ['F30', ['F30']],
    ['BBB', ['BBB']],
    ['Fu', ['Fu']],
    ['hERG', ['hERG']],
    ['DILI', ['DILI']],
    ['AMES', ['AMES']]
  ]
}

export const AFFINITY_DETAIL_PROFILE: PredictDetailProfile = {
  key: 'affinity',
  titleKey: 'predict.result.detailProfileAffinity',
  showSmiles: false,
  showRadar: false,
  basic: {
    titleKey: 'predict.result.detailSectionAffinityIdentity',
    defs: [
      { labelKey: 'predict.result.detailFieldMoleculeId', aliases: ['molecule_id'] },
      { labelKey: 'predict.result.detailFieldComplexId', aliases: ['complex_id'] },
      { labelKey: 'predict.result.detailFieldDuration', aliases: ['duration_sec'], unit: 's' }
    ]
  },
  sections: [
    {
      titleKey: 'predict.result.detailSectionAffinityPrediction',
      defs: [
        { labelKey: 'predict.result.detailFieldPredictedAffinity', aliases: ['prediction.predicted_affinity', 'predicted_affinity'] },
        { labelKey: 'predict.result.detailFieldLigandToPocket', aliases: ['prediction.predicted_ligand_to_pocket', 'predicted_ligand_to_pocket'] },
        { labelKey: 'predict.result.detailFieldPocketToLigand', aliases: ['prediction.predicted_pocket_to_ligand', 'predicted_pocket_to_ligand'] },
        { labelKey: 'predict.result.detailFieldScale', aliases: ['prediction.scale', 'scale'] }
      ]
    },
    {
      titleKey: 'predict.result.detailSectionAffinityPreprocessing',
      defs: [
        { labelKey: 'predict.result.detailFieldPocketAtoms', aliases: ['preprocessing.pocket_atom_count', 'pocket_atom_count'] },
        { labelKey: 'predict.result.detailFieldLigandAtoms', aliases: ['preprocessing.ligand_atom_count', 'ligand_atom_count'] },
        { labelKey: 'predict.result.detailFieldPocketBonds', aliases: ['preprocessing.pocket_bond_count', 'pocket_bond_count'] },
        { labelKey: 'predict.result.detailFieldLigandBonds', aliases: ['preprocessing.ligand_bond_count', 'ligand_bond_count'] },
        { labelKey: 'predict.result.detailFieldGeneratedPocketAtoms', aliases: ['preprocessing.generated_pocket_atom_count', 'generated_pocket_atom_count'] }
      ]
    }
  ],
  radar: []
}

export const GENERIC_DETAIL_PROFILE: PredictDetailProfile = {
  key: 'generic',
  titleKey: 'predict.result.detailProfileGeneric',
  showSmiles: true,
  showRadar: false,
  basic: null,
  sections: [],
  radar: [],
  generic: true
}

/** 按模型能力族返回详情 profile；未知族一律走通用兜底。 */
export function resolvePredictDetailProfile(family: string | null | undefined): PredictDetailProfile {
  if (family === 'affinity') {
    return AFFINITY_DETAIL_PROFILE
  }
  if (family === 'admet_prediction') {
    return ADMET_DETAIL_PROFILE
  }
  return { ...GENERIC_DETAIL_PROFILE, key: family || 'generic' }
}
