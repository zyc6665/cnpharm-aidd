"""Adapter for invoking the legacy MolP-PC prediction entrypoint."""

from __future__ import annotations

import os
import sys
import importlib.util
from pathlib import Path

from .result_builder import LEGACY_PREDICTION_FILENAME


REQUIRED_LEGACY_MODULES = ("dgl", "rdkit", "torch")


def validate_runtime_dependencies() -> None:
    """Validate dependencies needed by the legacy MolP-PC predictor."""
    missing = [name for name in REQUIRED_LEGACY_MODULES if importlib.util.find_spec(name) is None]
    if missing:
        raise RuntimeError(
            "MolP-PC runtime dependencies missing: "
            f"{', '.join(missing)}. Activate the environment declared in admet.yml "
            "or set MOLP_PC_PYTHON to that environment's python executable."
        )


def run_legacy_predict(
    *,
    model_root: Path,
    input_csv: Path,
    work_dir: Path,
    device: str,
) -> Path:
    """Run predict/test.py::predict and return the generated legacy CSV path."""
    predict_dir = model_root / "predict"
    weights_dir = predict_dir / "model"
    if not (predict_dir / "test.py").is_file():
        raise FileNotFoundError(f"Prediction entry not found: {predict_dir / 'test.py'}")
    if not weights_dir.is_dir():
        raise FileNotFoundError(f"Model weights directory not found: {weights_dir}")
    validate_runtime_dependencies()

    run_dir = work_dir / f"molp_pc_runtime_{os.getpid()}"
    run_dir.mkdir(parents=True, exist_ok=True)
    weights_link = run_dir / "model"
    if not weights_link.exists():
        os.symlink(weights_dir, weights_link, target_is_directory=True)

    old_cwd = Path.cwd()
    try:
        os.chdir(run_dir)
        sys.path.insert(0, str(predict_dir))
        import test  # type: ignore[import-not-found]

        os.environ["MOLP_PC_DEVICE"] = device
        test.args["device"] = device
        cache_path = run_dir / "platform_input.pkl"
        if cache_path.exists():
            cache_path.unlink()
        result_csv = run_dir / LEGACY_PREDICTION_FILENAME
        if result_csv.exists():
            result_csv.unlink()
        test.predict(str(input_csv), "platform_input")
    finally:
        os.chdir(old_cwd)

    result_csv = run_dir / LEGACY_PREDICTION_FILENAME
    if not result_csv.is_file():
        raise FileNotFoundError(f"Model did not create expected output CSV: {result_csv}")
    return result_csv
