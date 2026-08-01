"""Draft migrations from legacy semantic labels to standard Artifact refs."""

from __future__ import annotations

from dataclasses import dataclass

from app.artifact_standards.registry import is_standard_artifact_ref


@dataclass(frozen=True)
class LegacyArtifactTypeMigration:
    raw_type: str
    standard_type: str | None
    candidates: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    requires_choice: bool = False


DIRECT_LEGACY_TYPE_MAPPINGS: dict[str, str] = {
    "protein_pdb": "protein_structure@1",
    "protein_structure": "protein_structure@1",
    "pocket_pdb": "binding_pocket@1",
    "pocket_result": "binding_pocket@1",
    "pocket_structure": "binding_pocket@1",
    "smiles_csv": "molecule_table@1",
    "ranking_csv": "molecule_table@1",
}

AMBIGUOUS_LEGACY_TYPE_CANDIDATES: dict[str, tuple[str, ...]] = {
    "generated_ligand": ("ligand_structure@1", "molecule_table@1"),
}


def migrate_legacy_artifact_type(raw_type: str) -> LegacyArtifactTypeMigration:
    """Return a migration draft for a legacy semantic label."""
    if is_standard_artifact_ref(raw_type):
        return LegacyArtifactTypeMigration(raw_type=raw_type, standard_type=raw_type)

    if raw_type in DIRECT_LEGACY_TYPE_MAPPINGS:
        return LegacyArtifactTypeMigration(
            raw_type=raw_type,
            standard_type=DIRECT_LEGACY_TYPE_MAPPINGS[raw_type],
        )

    if raw_type in AMBIGUOUS_LEGACY_TYPE_CANDIDATES:
        candidates = AMBIGUOUS_LEGACY_TYPE_CANDIDATES[raw_type]
        return LegacyArtifactTypeMigration(
            raw_type=raw_type,
            standard_type=None,
            candidates=candidates,
            requires_choice=True,
            warnings=(
                f"{raw_type} can represent multiple standard Artifact shapes; "
                "choose the Tool Package output slot explicitly.",
            ),
        )

    return LegacyArtifactTypeMigration(
        raw_type=raw_type,
        standard_type=None,
        warnings=(f"No standard Artifact migration is known for {raw_type}.",),
        requires_choice=True,
    )
