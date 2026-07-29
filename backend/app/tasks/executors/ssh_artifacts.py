"""SSH 作业输出文件筛选与归档。"""

import glob
import os
import zipfile
from pathlib import Path
from typing import Any


def prepare_output_files(config: dict[str, Any], download_root: str, output_root: str) -> list[str]:
    matched: dict[str, None] = {}
    for pattern in config.get("output_globs") or ["output/**/*"]:
        for path in glob.glob(os.path.join(download_root, pattern), recursive=True):
            if os.path.isfile(path):
                matched[path] = None
    if not matched:
        for path in Path(output_root).rglob("*"):
            if path.is_file():
                matched[str(path)] = None
    files = list(matched)
    threshold = int(config.get("bulk_sdf_zip_threshold", 10))
    if threshold <= 0:
        return files
    sdf_dirs: dict[str, list[str]] = {}
    for file_path in files:
        path = Path(file_path)
        if path.suffix.lower() == ".sdf" and path.parent.name.lower() == "sdf":
            sdf_dirs.setdefault(str(path.parent), []).append(file_path)
    zip_paths: dict[str, str] = {}
    for directory_name, sdf_files in sdf_dirs.items():
        if len(sdf_files) < threshold:
            continue
        directory = Path(directory_name)
        zip_path = directory.with_suffix(".zip")
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for child in sorted(directory.rglob("*")):
                if child.is_file() and child != zip_path:
                    archive.write(child, child.relative_to(directory.parent).as_posix())
        zip_paths[directory_name] = str(zip_path)
    if not zip_paths:
        return files
    return [path for path in files if str(Path(path).parent) not in zip_paths] + list(zip_paths.values())
