import { parsePocketGeometry } from '@/domain/pockets/pocket-geometry'

// Synthetic demo inputs, not an experimental protein–ligand structure.
export const SAMPLE_RECEPTOR_PDB = `ATOM      1  N   GLY A   1      30.128  14.516  51.996  1.00  0.00           N
ATOM      2  CA  GLY A   1      28.796  14.080  51.548  1.00  0.00           C
ATOM      3  C   GLY A   1      28.177  13.100  52.551  1.00  0.00           C
ATOM      4  O   GLY A   1      28.764  12.705  53.556  1.00  0.00           O
ATOM      5  N   ALA A   2      26.903  12.708  52.224  1.00  0.00           N
ATOM      6  CA  ALA A   2      26.150  11.743  53.018  1.00  0.00           C
ATOM      7  C   ALA A   2      25.070  11.131  52.104  1.00  0.00           C
ATOM      8  O   ALA A   2      24.797  11.613  51.004  1.00  0.00           O
ATOM      9  CB  ALA A   2      25.515  12.410  54.233  1.00  0.00           C
ATOM     10  N   VAL A   3      24.447  10.010  52.612  1.00  0.00           N
ATOM     11  CA  VAL A   3      23.237   9.484  51.981  1.00  0.00           C
ATOM     12  C   VAL A   3      22.021  10.094  52.713  1.00  0.00           C
ATOM     13  O   VAL A   3      22.109  10.614  53.825  1.00  0.00           O
ATOM     14  CB  VAL A   3      23.186   7.940  51.993  1.00  0.00           C
ATOM     15  CG1 VAL A   3      24.278   7.353  51.093  1.00  0.00           C
ATOM     16  CG2 VAL A   3      23.291   7.338  53.397  1.00  0.00           C
ATOM     17  N   GLY A   4      20.826   9.969  52.050  1.00  0.00           N
ATOM     18  CA  GLY A   4      19.604  10.527  52.590  1.00  0.00           C
ATOM     19  C   GLY A   4      18.453  10.297  51.612  1.00  0.00           C
ATOM     20  O   GLY A   4      18.624   9.807  50.498  1.00  0.00           O
ATOM     21  N   SER A   5      17.220  10.695  52.090  1.00  0.00           N
ATOM     22  CA  SER A   5      16.065  10.737  51.184  1.00  0.00           C
ATOM     23  C   SER A   5      15.946  12.107  50.511  1.00  0.00           C
ATOM     24  O   SER A   5      15.080  12.428  49.709  1.00  0.00           O
ATOM     25  CB  SER A   5      14.756  10.473  51.936  1.00  0.00           C
ATOM     26  OG  SER A   5      13.696  10.107  51.054  1.00  0.00           O
ATOM     27  OXT SER A   5      16.862  13.014  50.917  1.00  0.00           O
TER      28      SER A   5
END
`

export const SAMPLE_POCKET_PDB = `HETATM    1  C1  UNL A   1      17.000   5.000  52.000  1.00  0.00           C
HETATM    2  C2  UNL A   1      27.000   5.000  52.000  1.00  0.00           C
HETATM    3  C3  UNL A   1      22.000   1.000  52.000  1.00  0.00           C
HETATM    4  C4  UNL A   1      22.000   9.000  52.000  1.00  0.00           C
HETATM    5  C5  UNL A   1      22.000   5.000  48.000  1.00  0.00           C
HETATM    6  C6  UNL A   1      22.000   5.000  56.000  1.00  0.00           C
END
`

export const SAMPLE_LIGAND_SDF = `4-Cyclopropylquinazoline (offline sample)
     RDKit          3D

 13 15  0  0  0  0  0  0  0  0999 V2000
   24.3115    3.5258   52.6788 C   0  0  0  0  0  0  0  0  0  0  0  0
   25.1190    4.5603   52.2276 C   0  0  0  0  0  0  0  0  0  0  0  0
   24.5359    5.7445   51.7689 C   0  0  0  0  0  0  0  0  0  0  0  0
   23.1584    5.9262   51.7469 C   0  0  0  0  0  0  0  0  0  0  0  0
   22.6747    7.0877   51.2984 N   0  0  0  0  0  0  0  0  0  0  0  0
   21.3449    7.2216   51.3007 C   0  0  0  0  0  0  0  0  0  0  0  0
   20.4583    6.3066   51.7044 N   0  0  0  0  0  0  0  0  0  0  0  0
   20.9500    5.1258   52.1497 C   0  0  0  0  0  0  0  0  0  0  0  0
   19.9358    4.0925   52.6114 C   0  0  0  0  0  0  0  0  0  0  0  0
   18.6072    3.9578   51.8994 C   0  0  0  0  0  0  0  0  0  0  0  0
   19.6414    2.8847   51.7488 C   0  0  0  0  0  0  0  0  0  0  0  0
   22.3358    4.8830   52.1988 C   0  0  0  0  0  0  0  0  0  0  0  0
   22.9272    3.6834   52.6663 C   0  0  0  0  0  0  0  0  0  0  0  0
  1  2  2  0
  2  3  1  0
  3  4  2  0
  4  5  1  0
  5  6  2  0
  6  7  1  0
  7  8  2  0
  8  9  1  0
  9 10  1  0
 10 11  1  0
  8 12  1  0
 12 13  2  0
 13  1  1  0
 12  4  1  0
 11  9  1  0
M  END
$$$$
`

export function createSampleDesignFiles() {
  const geometry = parsePocketGeometry(SAMPLE_POCKET_PDB)
  if (!geometry) throw new Error('The bundled sample pocket has no geometry.')
  return {
    receptorFile: new File([SAMPLE_RECEPTOR_PDB], 'receptor.pdb', { type: 'chemical/x-pdb' }),
    pocketFile: new File([SAMPLE_POCKET_PDB], 'pocket0.pdb', { type: 'chemical/x-pdb' }),
    ligandFile: new File([SAMPLE_LIGAND_SDF], 'egfr_ligand.sdf', { type: 'chemical/x-mdl-sdfile' }),
    pocketCenter: geometry.center,
    pocketBoxSize: geometry.boxSize
  }
}
