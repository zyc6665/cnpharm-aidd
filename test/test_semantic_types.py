"""Tests for canonical semantic type registry."""

from app.services.semantic_types import (
    CANONICAL_SEMANTIC_TYPES,
    CANONICAL_AGENT_INPUT_TYPES,
    SEMANTIC_TYPE_ALIASES,
    normalize_semantic_type,
    is_supported_semantic_type,
)


def test_new_aidd_types_are_registered():
    new_types = {
        "admet_report",
        "toxicity_report",
        "synthetic_accessibility",
        "molecular_dynamics_trajectory",
        "interaction_report",
        "docking_pose_diffdock",
        "docking_pose_gnina",
        "docking_pose_smina",
        "database_query_result",
    }
    assert new_types.issubset(CANONICAL_SEMANTIC_TYPES)


def test_aliases_resolve_to_new_types():
    assert normalize_semantic_type("md_traj") == "molecular_dynamics_trajectory"
    assert normalize_semantic_type("sa_score") == "synthetic_accessibility"
    assert normalize_semantic_type("interactions") == "interaction_report"
    assert normalize_semantic_type("chembl_result") == "database_query_result"


def test_is_supported_recognizes_aliases():
    assert is_supported_semantic_type("md_traj") is True
    assert is_supported_semantic_type("unknown_type") is False


def test_new_database_query_result_is_agent_input():
    assert "database_query_result" in CANONICAL_AGENT_INPUT_TYPES
