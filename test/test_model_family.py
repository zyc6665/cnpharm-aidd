from app.tools.capabilities import MODEL_FAMILY_BY_SLUG, resolve_model_family


def test_model_family_groups_same_capability_models():
    assert resolve_model_family("pocket2mol-pocket-ligand-generation") == "molecule_generation"
    assert resolve_model_family("therapainter-peptide-prediction") == "peptide_design"
    assert resolve_model_family("boltz2-structure-prediction") == "structure_prediction"
    assert resolve_model_family("lvpocket-pocket-prediction") == "pocket_prediction"
    # 同类多模型应归到同一族
    assert resolve_model_family("autodock-vina-docking") == "docking"
    assert resolve_model_family("builtin-vina-docking") == "docking"
    assert resolve_model_family("gromacs-md") == "molecular_dynamics"
    assert resolve_model_family("builtin-molecular-dynamics") == "molecular_dynamics"


def test_model_family_unknown_slug_is_none():
    assert resolve_model_family("nonexistent-model") is None
    assert resolve_model_family(None) is None
    assert MODEL_FAMILY_BY_SLUG["gmx-mmpbsa"] == "free_energy"
