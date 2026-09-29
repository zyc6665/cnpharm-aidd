"""化学数据库查询工具（virtual tools）。

为 AIDD Agent 提供 ChEMBL、PubChem、PDBbind 的查询能力。
输出统一为 ``database_query_result`` 语义类型。

Feature flag ``ENABLE_DATABASE_TOOLS`` 默认关闭；关闭时调用任何查询函数都会抛出
``ValidationException``。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional
from urllib.parse import quote

import httpx

from app.common.exceptions import ValidationException
from app.config import settings
from app.exceptions.external_api import (
    APIConnectionException,
    APIResponseException,
    APITimeoutException,
    ExternalAPIException,
)

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30.0
MAX_RETRIES = 3
BASE_DELAY = 1.0


def _check_feature_flag() -> None:
    """校验数据库查询工具 feature flag 是否开启。"""
    if not settings.ENABLE_DATABASE_TOOLS:
        raise ValidationException("数据库查询工具已禁用")


async def _request_with_retry(
    api_name: str,
    url: str,
    *,
    params: Optional[dict[str, Any]] = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """带简单重试的 HTTP GET 请求。

    对连接超时类错误执行指数退避重试（1s / 2s / 4s），非 2xx 响应直接抛出
    ``APIResponseException``。
    """
    last_exception: Optional[ExternalAPIException] = None

    for attempt in range(MAX_RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                return response.json()
        except httpx.TimeoutException:
            last_exception = APITimeoutException(
                message=f"{api_name} request timed out after {timeout}s: {url}",
                api_name=api_name,
            )
        except httpx.ConnectError as exc:
            last_exception = APIConnectionException(
                message=f"{api_name} connection failed: {exc}",
                api_name=api_name,
            )
        except httpx.HTTPStatusError as exc:
            raise APIResponseException(
                message=f"{api_name} returned {exc.response.status_code}",
                api_name=api_name,
                status_code=exc.response.status_code,
                response_body=exc.response.text[:500],
            ) from exc
        except Exception as exc:
            raise ExternalAPIException(
                message=f"{api_name} request failed: {exc}",
                api_name=api_name,
            ) from exc

        if attempt < MAX_RETRIES:
            delay = BASE_DELAY * (2 ** attempt)
            logger.warning(
                f"{api_name} request failed, retrying in {delay}s (attempt {attempt + 1}/{MAX_RETRIES})",
                extra={"api_name": api_name, "url": url, "attempt": attempt},
            )
            await asyncio.sleep(delay)

    raise last_exception or ExternalAPIException(
        message=f"{api_name} request failed after {MAX_RETRIES} retries",
        api_name=api_name,
    )


def _build_query_result(
    source: str,
    query: dict[str, Any],
    records: list[dict[str, Any]],
    raw_url: str,
) -> dict[str, Any]:
    """构建统一的 database_query_result 输出格式。"""
    return {
        "source": source,
        "query": query,
        "record_count": len(records),
        "records": records,
        "raw_url": raw_url,
    }


async def query_chembl(
    smiles: Optional[str] = None,
    query: Optional[str] = None,
    *,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """查询 ChEMBL 数据库。

    若提供 ``smiles``，执行相似性搜索；否则按 ``query`` 关键词搜索分子。
    """
    _check_feature_flag()

    if smiles:
        encoded_smiles = quote(smiles, safe="")
        url = f"https://www.ebi.ac.uk/chembl/api/data/similarity/{encoded_smiles}/90.json"
        params = {"limit": 5}
        search_query = {"smiles": smiles, "similarity": 90}
    elif query:
        url = "https://www.ebi.ac.uk/chembl/api/data/molecule.json"
        params = {"limit": 5, "q": query}
        search_query = {"q": query}
    else:
        raise ValidationException("query_chembl 需要提供 smiles 或 query 参数")

    data = await _request_with_retry(
        "ChEMBL", url, params=params, timeout=timeout
    )

    molecules = data.get("molecules", [])
    records = [
        {
            "chembl_id": mol.get("molecule_chembl_id"),
            "name": mol.get("pref_name"),
            "smiles": mol.get("molecule_structures", {}).get("canonical_smiles"),
        }
        for mol in molecules
        if isinstance(mol, dict)
    ]

    return _build_query_result(
        source="chembl",
        query=search_query,
        records=records,
        raw_url=url,
    )


async def query_pubchem(
    smiles: Optional[str] = None,
    query: Optional[str] = None,
    *,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """查询 PubChem 数据库。

    若提供 ``smiles``，按 SMILES 查询化合物属性；否则按 ``query`` 关键词搜索。
    """
    _check_feature_flag()

    if smiles:
        encoded_smiles = quote(smiles, safe="")
        url = (
            "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/smiles/"
            f"{encoded_smiles}"
            "/property/IsomericSMILES,MolecularFormula,MolecularWeight,IUPACName/JSON"
        )
        search_query = {"smiles": smiles}
    elif query:
        encoded_query = quote(query, safe="")
        url = (
            "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/"
            f"{encoded_query}"
            "/property/IsomericSMILES,MolecularFormula,MolecularWeight,IUPACName/JSON"
        )
        search_query = {"name": query}
    else:
        raise ValidationException("query_pubchem 需要提供 smiles 或 query 参数")

    data = await _request_with_retry("PubChem", url, timeout=timeout)

    properties = data.get("PropertyTable", {}).get("Properties", [])
    records = [
        {
            "cid": prop.get("CID"),
            "smiles": prop.get("IsomericSMILES"),
            "molecular_formula": prop.get("MolecularFormula"),
            "molecular_weight": prop.get("MolecularWeight"),
            "iupac_name": prop.get("IUPACName"),
        }
        for prop in properties
        if isinstance(prop, dict)
    ]

    return _build_query_result(
        source="pubchem",
        query=search_query,
        records=records,
        raw_url=url,
    )


async def query_pdbbind(
    protein_pdb_id: Optional[str] = None,
    ligand_name: Optional[str] = None,
    *,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """查询 PDBbind 数据集。

    PDBbind 没有公开 REST API，因此本函数返回公开下载页元数据或本地索引提示。
    若提供 ``protein_pdb_id``，会构造到 PDBbind 对应记录的搜索链接。
    """
    _check_feature_flag()

    query: dict[str, Any] = {}
    if protein_pdb_id:
        query["protein_pdb_id"] = protein_pdb_id
    if ligand_name:
        query["ligand_name"] = ligand_name

    # PDBbind 公开入口
    base_url = "http://www.pdbbind.org.cn/"
    search_url = f"{base_url}index.php"

    records: list[dict[str, Any]] = []
    if protein_pdb_id:
        records.append(
            {
                "protein_pdb_id": protein_pdb_id,
                "ligand_name": ligand_name,
                "note": "PDBbind does not expose a public REST API; use the official download page.",
                "download_page": "http://www.pdbbind.org.cn/download.php",
            }
        )

    return _build_query_result(
        source="pdbbind",
        query=query,
        records=records,
        raw_url=search_url,
    )
