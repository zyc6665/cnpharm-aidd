"""Single source of truth for the three ``Artifact`` identity columns.

``Artifact`` expresses the identity of one logical asset with three columns plus a
version carrier:

* ``artifact_type`` — the controlled asset-root type (the 8 values in
  :mod:`app.artifact_standards.asset_types`), ``NOT NULL``.
* ``semantic_type`` — the semantic label of the asset. For every identity written
  through the application this equals ``artifact_type``.
* ``standard_type`` — ``NULL`` for a non-standard artifact, or the standard type
  (== ``artifact_type``) for a standard artifact.
* ``standard_version`` — the *only* carrier of the standard version.

Historically each write path pieced these three columns together on its own, which
let one path write a value, another downgrade it and a third reject it ("A 写、B 降级、
C 拒收"). :func:`resolve_identity` is the single place that encodes the rules; every
writer must go through it.

Data-backed scope of the invariant
-----------------------------------
The project database (dev SQLite is absent; the PostgreSQL verification DB and the
existing test fixtures were inspected) shows two facts:

* Every persisted row has ``standard_type`` ``NULL`` or equal to ``artifact_type``
  (PG: 20 000 / 20 000 rows are ``(protein_structure, protein_structure,
  protein_structure)``).  This is safe to make a **DB CHECK**.
* ``semantic_type`` is *not* universally equal to ``artifact_type`` in historical
  test data: several fixtures deliberately construct ``semantic_type="type@vN"``
  (e.g. ``test/test_artifact_responses.py``, ``test/test_typed_artifacts_api.py``).
  A hard ``CHECK (semantic_type = artifact_type)`` would reject those legitimate
  legacy representations.  We therefore normalise ``semantic_type`` at the
  *service* layer (this resolver) instead of a DB CHECK; the migration still strips
  an ``@vN`` suffix from persisted rows where the base equals ``artifact_type``.
"""

from __future__ import annotations

from app.artifact_standards.asset_types import (
    ASSET_ARTIFACT_TYPES,
    is_asset_artifact_type,
    normalize_asset_artifact_type,
)
from app.common.exceptions import ValidationException

_ARTIFACT_TYPE_HINT = "artifact_type 必须是受控资产类型之一: " + ", ".join(ASSET_ARTIFACT_TYPES)


def split_semantic_version(semantic_type: str | None) -> tuple[str | None, int | None]:
    """Split a ``"type@vN"`` semantic label into ``(type, version)``.

    ``"protein_structure"`` -> ``("protein_structure", None)``;
    ``"protein_structure@3"`` -> ``("protein_structure", 3)``.
    A malformed version suffix raises :class:`ValidationException` rather than being
    silently dropped.
    """
    if not isinstance(semantic_type, str):
        return None, None
    value = semantic_type.strip()
    if not value:
        return None, None
    if "@" not in value:
        return value, None
    base, _, raw_version = value.partition("@")
    base = base.strip()
    raw_version = raw_version.strip()
    if not raw_version:
        # "type@" carries no version information; treat it as a bare type.
        return base or None, None
    try:
        version = int(raw_version)
    except ValueError as exc:
        raise ValidationException(
            f"semantic_type 的版本后缀必须是整数: {semantic_type!r}"
        ) from exc
    if version < 1:
        raise ValidationException(
            f"semantic_type 的版本后缀必须 >= 1: {semantic_type!r}"
        )
    return base or None, version


def resolve_identity_full(
    artifact_type: str,
    semantic_type: str | None = None,
    standard_type: str | None = None,
    standard_version: int | None = None,
) -> tuple[str, str, str | None, int | None]:
    """Resolve the full identity tuple including ``standard_version``.

    Returns ``(artifact_type, semantic_type, standard_type, standard_version)``.
    Use :func:`resolve_identity` when only the three columns are needed.
    """
    if not is_asset_artifact_type(artifact_type):
        raise ValidationException(_ARTIFACT_TYPE_HINT)
    if standard_version is not None and (
        not isinstance(standard_version, int) or isinstance(standard_version, bool)
    ):
        raise ValidationException(f"standard_version 必须是整数: {standard_version!r}")
    if standard_version is not None and standard_version < 1:
        raise ValidationException(f"standard_version 必须 >= 1: {standard_version!r}")

    sem_base_raw, embedded_version = split_semantic_version(semantic_type)
    # Normalise a historical / alias / "type@v" base to a controlled asset type when
    # possible.  A free-form label (e.g. "generic_file") normalises to ``None`` and is
    # treated as a refinement of ``artifact_type`` rather than a competing type.
    sem_base = normalize_asset_artifact_type(sem_base_raw) if sem_base_raw else None

    if embedded_version is not None and standard_version is not None:
        if embedded_version != standard_version:
            raise ValidationException(
                "semantic_type 的 @v 版本与 standard_version 冲突: "
                f"{embedded_version} != {standard_version}"
            )
    resolved_version = standard_version if standard_version is not None else embedded_version

    # A standard identity is signalled by any standard-specific field being present:
    # an explicit standard_type, a standard_version, or an "@vN" suffix on semantic_type.
    is_standard = (
        standard_type is not None or standard_version is not None or embedded_version is not None
    )

    if is_standard:
        if standard_type is not None:
            if not is_asset_artifact_type(standard_type):
                raise ValidationException(_ARTIFACT_TYPE_HINT)
            if standard_type != artifact_type:
                raise ValidationException(
                    "artifact_type 与 standard_type 不一致: "
                    f"{artifact_type!r} != {standard_type!r}"
                )
        if sem_base is not None and sem_base != artifact_type:
            raise ValidationException(
                "标准产物的 semantic_type 与 artifact_type 不一致: "
                f"{sem_base!r} != {artifact_type!r}"
            )
        # Three columns collapse onto the single standard type; version lives only in
        # standard_version.
        return artifact_type, artifact_type, artifact_type, resolved_version

    # Non-standard: standard_type is None, semantic_type tracks artifact_type.
    if sem_base is not None and sem_base != artifact_type and sem_base in ASSET_ARTIFACT_TYPES:
        # Two *controlled* type identities disagree — a real conflict, not a refinement.
        raise ValidationException(
            "非标准产物的 semantic_type 指向了另一个受控资产类型: "
            f"{sem_base!r} != {artifact_type!r}"
        )
    return artifact_type, artifact_type, None, resolved_version


def resolve_identity(
    artifact_type: str,
    semantic_type: str | None = None,
    standard_type: str | None = None,
    standard_version: int | None = None,
) -> tuple[str, str, str | None]:
    """Resolve ``(artifact_type, semantic_type, standard_type)`` for an Artifact row.

    Rules (single source of truth):

    * ``artifact_type`` must be one of the controlled asset types, otherwise a
      :class:`ValidationException` is raised.
    * Standard artifact (explicit ``standard_type``/``standard_version`` or an
      ``@vN`` semantic suffix): all three columns become the standard type; the
      version is carried only by ``standard_version`` (an ``@vN`` suffix is stripped).
    * Non-standard artifact: ``standard_type`` is ``None`` and
      ``semantic_type == artifact_type``.
    * Any conflict (``artifact_type`` vs ``standard_type``, a differing controlled
      semantic type, or a version mismatch) raises :class:`ValidationException`
      instead of silently rewriting the value.

    ``standard_version`` is not part of the returned tuple; call
    :func:`resolve_identity_full` if the caller needs the ``@vN``-derived version.
    """
    resolved_artifact_type, resolved_semantic_type, resolved_standard_type, _ = (
        resolve_identity_full(
            artifact_type,
            semantic_type=semantic_type,
            standard_type=standard_type,
            standard_version=standard_version,
        )
    )
    return resolved_artifact_type, resolved_semantic_type, resolved_standard_type


__all__ = [
    "resolve_identity",
    "resolve_identity_full",
    "split_semantic_version",
]
