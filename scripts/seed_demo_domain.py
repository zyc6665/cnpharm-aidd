"""开发/自测用的领域数据造数脚本（幂等：按 DEMO 标记清理后重建）。

只用于本地演示与 UX 走查，不参与交付。覆盖：靶点 → 蛋白 → 结构 → 口袋 → 残基、
化合物 → 候选物 → 候选集、决策记录、工作流定义与一次运行。

用法（在 backend 同级仓库根目录）：
    python scripts/_seed_demo_domain.py
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from sqlalchemy import delete, select  # noqa: E402

from app.common.time import utcnow  # noqa: E402
from app.database.session import async_session_factory  # noqa: E402
from app.models.compounds import (  # noqa: E402
    Candidate,
    CandidateSet,
    CandidateSetItem,
    Compound,
    MoleculeFingerprint,
)
from app.models.decisions import DecisionItem, DecisionRecord  # noqa: E402
from app.models.projects import Organization, Project, ProjectMember  # noqa: E402
from app.models.targets import Pocket, PocketResidue, Protein, ProteinStructure, Target  # noqa: E402
from app.models.tasks import Task  # noqa: E402
from app.chemistry.molecule_properties import describe_smiles
from app.models.users import User  # noqa: E402
from app.models.workflows import WorkflowDefinition, WorkflowRun  # noqa: E402

DEMO_TAG = "demo-seed"

# 一条真实可解析的 EGFR 激酶域片段（约 300 aa），用于结构页与预测页演示
EGFR_SEQ = (
    "MRPSGTAGAALLALLAALCPASRALEEKKVCQGTSNKLTQLGTFEDHFLSLQRMFNNCEVVLGNLEITYVQRNYDLSFLKTIQEVAGYV"
    "LIALNTVERIPLENLQIIRGNMYYENSYALAVLSNYDANKTGLKELPMRNLQEILHGAVRFSNNPALCNVESIQWRDIVSSDFLSNMSM"
    "DFQNHLGSCQKCDPSCPNGSCWGAGEENCQKLTKIICAQQCSGRCRGKSPSDCCHNQCAAGCTGPRESDCLVCRKFRDEATCKDTCPPLM"
    "LYNPTTYQMDVNPEGKYSFGATCVKKCPRNYVVTDHGSCVRACGADSYEMEEDGVRKCKKCEGPCRKVCNGIGIGEFKDSLSINATNIKH"
    "FKNCTSISGDLHILPVAFRGDSFTHTPPLDPQELDILKTVKEITGFLLIQAWPENRTDLHAFENLEIIRGRTKQHGQFSLAVVSLNITSLG"
    "LRSLKEISDGDVIISGNKNLCYANTINWKKLFGTSGQKTKIISNRGENSCKATGQVCHALCSPEGCWGPEPRDCVSCRNVSRGRECVDKC"
)

COMPOUNDS = [
    ("CCO", "乙醇（对照）"),
    ("CC(=O)Oc1ccccc1C(=O)O", "阿司匹林"),
    ("CC(C)Cc1ccc(cc1)C(C)C(=O)O", "布洛芬"),
    ("CN1CCC[C@H]1c2cccnc2", "尼古丁"),
    ("O=C(N)c1nc2ccccc2[nH]1", "苯并咪唑甲酰胺"),
]


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


async def _clean(db) -> None:
    """按 DEMO 标记清理，避免影响既有数据。"""
    projects = (await db.execute(select(Project).where(Project.name.like("演示项目%")))).scalars().all()
    for project in projects:
        pid = project.id
        target_ids = [
            row for row in (await db.execute(select(Target.id).where(Target.project_id == pid))).scalars().all()
        ]
        if target_ids:
            protein_ids = (
                await db.execute(select(Protein.id).where(Protein.target_id.in_(target_ids)))
            ).scalars().all()
            if protein_ids:
                structure_ids = (
                    await db.execute(select(ProteinStructure.id).where(ProteinStructure.protein_id.in_(protein_ids)))
                ).scalars().all()
                if structure_ids:
                    pocket_ids = (
                        await db.execute(select(Pocket.id).where(Pocket.structure_id.in_(structure_ids)))
                    ).scalars().all()
                    if pocket_ids:
                        await db.execute(delete(PocketResidue).where(PocketResidue.pocket_id.in_(pocket_ids)))
                    await db.execute(delete(Pocket).where(Pocket.structure_id.in_(structure_ids)))
                await db.execute(delete(ProteinStructure).where(ProteinStructure.protein_id.in_(protein_ids)))
            await db.execute(delete(Protein).where(Protein.target_id.in_(target_ids)))
        await db.execute(delete(Target).where(Target.project_id == pid))

        set_ids = (
            await db.execute(select(CandidateSet.id).where(CandidateSet.project_id == pid))
        ).scalars().all()
        if set_ids:
            await db.execute(delete(CandidateSetItem).where(CandidateSetItem.set_id.in_(set_ids)))
        decision_ids = (
            await db.execute(select(DecisionRecord.id).where(DecisionRecord.project_id == pid))
        ).scalars().all()
        if decision_ids:
            await db.execute(delete(DecisionItem).where(DecisionItem.decision_id.in_(decision_ids)))
            await db.execute(delete(DecisionRecord).where(DecisionRecord.id.in_(decision_ids)))
        candidate_ids = (
            await db.execute(select(Candidate.id).where(Candidate.project_id == pid))
        ).scalars().all()
        if candidate_ids:
            await db.execute(delete(Candidate).where(Candidate.id.in_(candidate_ids)))
        await db.execute(delete(CandidateSet).where(CandidateSet.project_id == pid))
        run_ids = (
            await db.execute(select(WorkflowRun.id).where(WorkflowRun.project_id == pid))
        ).scalars().all()
        if run_ids:
            await db.execute(delete(WorkflowRun).where(WorkflowRun.id.in_(run_ids)))
        await db.execute(delete(WorkflowDefinition).where(WorkflowDefinition.project_id == pid))
        # 成员关系必须显式先删：走查时手工加过成员，直接删项目会撞外键。
        await db.execute(delete(ProjectMember).where(ProjectMember.project_id == pid))
        await db.execute(delete(Project).where(Project.id == pid))
    demo_compounds = (
        await db.execute(select(Compound.id).where(Compound.props["demo_tag"].as_string() == DEMO_TAG))
    ).scalars().all()
    if demo_compounds:
        await db.execute(delete(MoleculeFingerprint).where(MoleculeFingerprint.compound_id.in_(demo_compounds)))
        await db.execute(delete(Compound).where(Compound.id.in_(demo_compounds)))
    await db.commit()


async def main() -> int:
    async with async_session_factory() as db:
        await _clean(db)

        owner = (await db.execute(select(User).where(User.username == "admin"))).scalars().first()
        if owner is None:
            raise SystemExit("需要先有 admin 用户（python -m app.cli.ensure_admin）")

        organization = (await db.execute(select(Organization).limit(1))).scalars().first()
        if organization is None:
            organization = Organization(
                id=str(uuid.uuid4()), name="演示组织", slug="demo-org", description="本地演示用组织"
            )
            db.add(organization)
            await db.flush()

        project = Project(
            id=str(uuid.uuid4()),
            organization_id=organization.id,
            created_by=owner.id,
            name="演示项目 · EGFR 抑制剂发现",
            goal="围绕 EGFR 激酶域完成结构解析、口袋识别、分子生成与虚拟筛选，产出可进入实验验证的候选物。",
            status="active",
            model_policy={},
            data_policy={},
        )
        db.add(project)
        await db.flush()

        target = Target(
            id=str(uuid.uuid4()),
            project_id=project.id,
            created_by=owner.id,
            name="EGFR（表皮生长因子受体）",
            target_type="PROTEIN",
            uniprot_id="P00533",
            gene_name="EGFR",
            description="非小细胞肺癌一线靶点，ATP 结合口袋位于激酶域 N 叶与 C 叶之间。",
        )
        db.add(target)
        await db.flush()

        protein = Protein(
            id=str(uuid.uuid4()),
            target_id=target.id,
            name="EGFR 激酶域（野生型）",
            sequence=EGFR_SEQ,
            seq_length=len(EGFR_SEQ),
            source="IMPORT",
            current_version=1,
        )
        db.add(protein)
        await db.flush()

        structure = ProteinStructure(
            id=str(uuid.uuid4()),
            protein_id=protein.id,
            source_type="IMPORTED",
            structure_urn="demo://structures/egfr-1m17.pdb",
            sha256=_sha("egfr-1m17"),
            plddt_mean=None,
            model_name=None,
            model_version=None,
            tool_name="PDB Import",
            tool_version="1.0",
        )
        db.add(structure)
        await db.flush()

        pockets = []
        for rank, (score, volume, cx, cy, cz, count) in enumerate(
            [
                (8.9134, 412.55, 15.231, -2.118, 18.664, 21),
                (7.4421, 288.19, 4.902, 12.771, 6.335, 16),
                (6.1205, 205.44, -11.508, 3.402, -8.917, 13),
                (5.3377, 164.02, 21.664, 9.115, -4.223, 11),
                (4.8812, 131.87, -6.774, -18.336, 12.005, 9),
            ],
            start=1,
        ):
            pocket = Pocket(
                id=str(uuid.uuid4()),
                structure_id=structure.id,
                rank=rank,
                score=score,
                volume=volume,
                center_x=cx,
                center_y=cy,
                center_z=cz,
                box_size_x=22.0,
                box_size_y=22.0,
                box_size_z=22.0,
                residue_count=count,
                selected=(rank == 1),
                tool_name="LVpocket",
                tool_version="2.0.0",
            )
            db.add(pocket)
            pockets.append(pocket)
        await db.flush()

        residues = [
            ("A", 745, "LYS", True, 0.8712),
            ("A", 745, "LYS", False, 0.0),
            ("A", 766, "MET", True, 0.7934),
            ("A", 793, "THR", True, 0.7511),
            ("A", 796, "LEU", False, 0.6218),
            ("A", 841, "ASP", True, 0.5902),
            ("A", 855, "PHE", True, 0.5461),
            ("A", 858, "LEU", False, 0.4877),
        ]
        seen = set()
        for chain, seq, name, is_key, contribution in residues:
            key = (chain, seq, name)
            if key in seen:
                continue
            seen.add(key)
            db.add(
                PocketResidue(
                    id=str(uuid.uuid4()),
                    pocket_id=pockets[0].id,
                    chain=chain,
                    residue_seq=seq,
                    residue_name=name,
                    is_key=is_key,
                    contribution=contribution,
                )
            )

        compounds = []
        for smiles, name in COMPOUNDS:
            digest = _sha(smiles)
            # 演示数据也走真实化学层：InChIKey 与分子性质都由 RDKit 算出来，
            # 否则截图里会出现「DEMO...」这种假 InChIKey 和一片「未计算」，
            # 让走查的人误判成平台算不出来（真实导入路径本来就会算）。
            descriptor = describe_smiles(smiles)
            compound = Compound(
                id=str(uuid.uuid4()),
                created_by=owner.id,
                name=name,
                inchikey=descriptor.inchikey,
                canonical_smiles=descriptor.canonical_smiles,
                mol_formula=descriptor.mol_formula,
                mol_weight=descriptor.mol_weight,
                props={**descriptor.props, "demo_tag": DEMO_TAG},
                structure_urn=None,
            )
            db.add(compound)
            compounds.append(compound)
        await db.flush()

        candidate_set = CandidateSet(
            id=str(uuid.uuid4()),
            project_id=project.id,
            created_by=owner.id,
            name="第一轮生成候选集 · 2026-11-01",
            description="口袋 1 条件生成 100 个分子，按 QED 与 SA 分数筛选后保留 4 个。",
            item_count=0,
            version=1,
            is_archived=False,
        )
        db.add(candidate_set)
        await db.flush()

        candidates = []
        for index, compound in enumerate(compounds[:4], start=1):
            candidate = Candidate(
                id=str(uuid.uuid4()),
                project_id=project.id,
                created_by=owner.id,
                candidate_type="SMALL_MOLECULE",
                compound_id=compound.id,
                name=f"候选物-{index:02d}",
                code=f"EGFR-C{index:02d}",
                source="DESIGN",
                design_score=round(0.92 - index * 0.07, 4),
                attrs={"demo_tag": DEMO_TAG, "sa_score": round(2.1 + index * 0.4, 2)},
            )
            db.add(candidate)
            candidates.append(candidate)
        await db.flush()

        peptide = Candidate(
            id=str(uuid.uuid4()),
            project_id=project.id,
            created_by=owner.id,
            candidate_type="PEPTIDE",
            compound_id=None,
            peptide_sequence="Ac-ALWKTLLKKVLKAC-NH2",
            name="多肽候选物-P01",
            code="EGFR-P01",
            source="DESIGN",
            design_score=0.4312,
            attrs={"demo_tag": DEMO_TAG, "length": 14},
        )
        db.add(peptide)
        await db.flush()
        candidates.append(peptide)
        candidate_set.item_count = len(candidates)

        for ordinal, candidate in enumerate(candidates, start=1):
            db.add(
                CandidateSetItem(
                    id=str(uuid.uuid4()),
                    set_id=candidate_set.id,
                    candidate_id=candidate.id,
                    ordinal=ordinal,
                    snapshot_score=candidate.design_score,
                )
            )

        decision = DecisionRecord(
            id=str(uuid.uuid4()),
            project_id=project.id,
            decision_point="DP3",
            subject_type="CANDIDATE_SET",
            subject_id=candidate_set.id,
            reason="对接分数优于 -8.0 kcal/mol 且 QED > 0.6 的候选进入下一轮亲和力评估；多肽保留作为对照。",
            basis_task_ids=[],
            basis_metrics={"dock_score_threshold": -8.0, "qed_threshold": 0.6},
            decided_by="admin",
            decided_at=utcnow(),
        )
        db.add(decision)
        await db.flush()
        for candidate in candidates:
            db.add(
                DecisionItem(
                    id=str(uuid.uuid4()),
                    decision_id=decision.id,
                    candidate_id=candidate.id,
                    verdict="SELECTED" if candidate in candidates[:2] else "EXCLUDED",
                    snapshot_score=candidate.design_score,
                    snapshot_rank=candidates.index(candidate) + 1,
                    snapshot_attrs={"demo_tag": DEMO_TAG},
                )
            )

        task = (await db.execute(select(Task).where(Task.status == "SUCCESS").limit(1))).scalars().first()
        definition = WorkflowDefinition(
            id=str(uuid.uuid4()),
            project_id=project.id,
            name="EGFR 标准流程 · 结构→口袋→生成→筛选",
            description="从蛋白序列出发，结构预测后识别口袋，再以口袋为条件生成分子并做虚拟筛选。",
            user_id=owner.id,
            canvas_preset_id="protein-pocket-template",
            status="active",
            nodes=[
                {"id": "n1", "type": "tool", "tool_slug": "boltz2-structure-prediction", "title": "结构预测"},
                {"id": "n2", "type": "tool", "tool_slug": "lvpocket-pocket-prediction", "title": "口袋识别"},
                {"id": "n3", "type": "tool", "tool_slug": "std-diff", "title": "分子生成"},
            ],
            edges=[{"source": "n1", "target": "n2"}, {"source": "n2", "target": "n3"}],
        )
        db.add(definition)
        await db.flush()

        run = WorkflowRun(
            id=str(uuid.uuid4()),
            workflow_definition_id=definition.id,
            project_id=project.id,
            owner_id=owner.id,
            name="EGFR 标准流程 · 运行 #1",
            status="running",
            definition={"nodes": definition.nodes, "edges": definition.edges},
            input_files=[],
            execution_order=["n1", "n2", "n3"],
            node_states={
                "n1": {"status": "success", "task_id": task.id if task else None},
                "n2": {"status": "success"},
                "n3": {"status": "running", "progress": 42},
            },
            artifact_lineage=[],
            started_at=utcnow(),
        )
        db.add(run)
        await db.commit()

        print("project", project.id)
        print("target", target.id, "protein", protein.id, "structure", structure.id, "pocket", pockets[0].id)
        print("compound", compounds[0].id, "candidate", candidates[0].id, "set", candidate_set.id)
        print("decision", decision.id, "run", run.id)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
