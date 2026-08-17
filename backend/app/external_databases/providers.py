"""Provider adapters for external scientific databases."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import httpx


class ExternalDatabaseProviderError(ValueError):
    """Raised when an external database cannot return a usable record."""


@dataclass(frozen=True)
class ExternalArtifactFile:
    role: str
    filename: str
    content: bytes
    content_type: str


@dataclass(frozen=True)
class ExternalArtifactPayload:
    artifact_type: str
    standard_ref: str
    name: str
    description: str | None
    metadata: dict
    files: list[ExternalArtifactFile]


class ExternalDatabaseProvider(Protocol):
    async def fetch_ligand(self, identifier: str) -> ExternalArtifactPayload:
        """Return a ligand Artifact payload for an external identifier."""

    async def fetch_protein(self, identifier: str) -> ExternalArtifactPayload:
        """Return a protein Artifact payload for an external identifier."""


class PubChemProvider:
    base_url = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"

    async def fetch_ligand(self, identifier: str) -> ExternalArtifactPayload:
        cid = _normalize_identifier(identifier)
        async with httpx.AsyncClient(timeout=20.0) as client:
            properties = await self._fetch_properties(client, cid)
            two_d = await self._fetch_sdf(client, cid, record_type="2d", required=True)
            three_d = await self._fetch_sdf(client, cid, record_type="3d", required=False)

        compound = properties.get("PropertyTable", {}).get("Properties", [{}])[0]
        canonical_smiles = compound.get("CanonicalSMILES")
        files = [
            ExternalArtifactFile(
                role="structure_file",
                filename=f"pubchem-{cid}.sdf",
                content=three_d or two_d,
                content_type="chemical/x-mdl-sdfile",
            ),
            ExternalArtifactFile(
                role="structure_2d_sdf",
                filename=f"pubchem-{cid}.2d.sdf",
                content=two_d,
                content_type="chemical/x-mdl-sdfile",
            ),
        ]
        if three_d:
            files.append(
                ExternalArtifactFile(
                    role="structure_3d_sdf",
                    filename=f"pubchem-{cid}.3d.sdf",
                    content=three_d,
                    content_type="chemical/x-mdl-sdfile",
                )
            )
        metadata = {
            "ligand_id": f"pubchem:{cid}",
            "source_database": "pubchem",
            "source_id": cid,
            "pubchem_cid": cid,
            "canonical_smiles": canonical_smiles,
            "isomeric_smiles": compound.get("IsomericSMILES"),
            "iupac_name": compound.get("IUPACName"),
            "molecular_formula": compound.get("MolecularFormula"),
            "molecular_weight": compound.get("MolecularWeight"),
            "structure_3d_source": "pubchem_3d" if three_d else "2d_only",
            "hydrogens_added": False,
        }
        return ExternalArtifactPayload(
            artifact_type="ligand_structure",
            standard_ref="ligand_structure@1",
            name=str(compound.get("IUPACName") or f"PubChem CID {cid}"),
            description="Imported from PubChem",
            metadata={key: value for key, value in metadata.items() if value is not None},
            files=files,
        )

    async def fetch_protein(self, identifier: str) -> ExternalArtifactPayload:
        raise ExternalDatabaseProviderError("PubChem only supports ligand imports")

    async def _fetch_properties(self, client: httpx.AsyncClient, cid: str) -> dict:
        fields = ",".join(
            [
                "CanonicalSMILES",
                "IsomericSMILES",
                "IUPACName",
                "MolecularFormula",
                "MolecularWeight",
            ]
        )
        response = await client.get(f"{self.base_url}/compound/cid/{cid}/property/{fields}/JSON")
        if response.status_code >= 400:
            raise ExternalDatabaseProviderError(f"PubChem CID not found: {cid}")
        return response.json()

    async def _fetch_sdf(
        self,
        client: httpx.AsyncClient,
        cid: str,
        *,
        record_type: str,
        required: bool,
    ) -> bytes:
        response = await client.get(
            f"{self.base_url}/compound/cid/{cid}/SDF",
            params={"record_type": record_type},
        )
        if response.status_code >= 400:
            if required:
                raise ExternalDatabaseProviderError(
                    f"PubChem CID {cid} has no {record_type.upper()} SDF"
                )
            return b""
        return response.content


class RCSBProvider:
    files_url = "https://files.rcsb.org/download"

    async def fetch_protein(self, identifier: str) -> ExternalArtifactPayload:
        pdb_id = _normalize_identifier(identifier).upper()
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(f"{self.files_url}/{pdb_id}.pdb")
        if response.status_code >= 400:
            raise ExternalDatabaseProviderError(f"RCSB PDB entry not found: {pdb_id}")
        content = response.content
        pdb_stats = _pdb_stats(content.decode("utf-8", errors="ignore"))
        metadata = {
            "chain_ids": pdb_stats["chain_ids"],
            "residue_count": pdb_stats["residue_count"],
            "atom_count": pdb_stats["atom_count"],
            "structure_format": "pdb",
            "source_filename": f"{pdb_id}.pdb",
            "source_database": "rcsb",
            "source_id": pdb_id,
        }
        return ExternalArtifactPayload(
            artifact_type="protein_structure",
            standard_ref="protein_structure@1",
            name=pdb_id,
            description="Imported from RCSB PDB",
            metadata=metadata,
            files=[
                ExternalArtifactFile(
                    role="structure_file",
                    filename=f"{pdb_id}.pdb",
                    content=content,
                    content_type="chemical/x-pdb",
                )
            ],
        )

    async def fetch_ligand(self, identifier: str) -> ExternalArtifactPayload:
        raise ExternalDatabaseProviderError("RCSB only supports protein imports")


def default_external_database_providers() -> dict[str, ExternalDatabaseProvider]:
    return {
        "pubchem": PubChemProvider(),
        "rcsb": RCSBProvider(),
    }


def _normalize_identifier(identifier: str) -> str:
    value = identifier.strip()
    if not value:
        raise ExternalDatabaseProviderError("External database identifier is required")
    return value


def _pdb_stats(text: str) -> dict[str, object]:
    chains: set[str] = set()
    residues: set[tuple[str, str]] = set()
    atom_count = 0
    for line in text.splitlines():
        if not line.startswith(("ATOM", "HETATM")):
            continue
        atom_count += 1
        chain_id = line[21:22].strip() or "_"
        residue_id = line[22:27].strip()
        chains.add(chain_id)
        residues.add((chain_id, residue_id))
    return {
        "chain_ids": sorted(chains),
        "residue_count": len(residues),
        "atom_count": atom_count,
    }
