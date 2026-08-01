"""Adapter for invoking the raw model implementation."""

from __future__ import annotations

from pathlib import Path


def run_legacy_predict(
    *,
    model_root: Path,
    input_csv: Path,
    work_dir: Path,
    device: str,
) -> Path:
    """Run original_model/inference.py and return the raw output CSV."""
    del device  # Device selection belongs here when the real model supports it.
    work_dir.mkdir(parents=True, exist_ok=True)
    from original_model.inference import predict

    output_csv = predict(input_csv, work_dir)
    if not output_csv.is_file():
        raise FileNotFoundError(f"Raw model did not produce expected output: {output_csv}")
    if model_root.name == "":
        raise ValueError("model_root must not be empty")
    return output_csv
