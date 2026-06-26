"""化学数据库查询工具测试。"""

from unittest.mock import AsyncMock, patch

import pytest

from app.agents.aidd import database_tools
from app.common.exceptions import ValidationException
from app.config import settings
from app.exceptions.external_api import APIResponseException, APITimeoutException


@pytest.fixture(autouse=True)
def enable_database_tools(monkeypatch):
    """测试期间临时开启数据库查询工具 feature flag。"""
    monkeypatch.setattr(settings, "ENABLE_DATABASE_TOOLS", True)


class TestQueryChembl:
    """ChEMBL 查询测试。"""

    @pytest.mark.asyncio
    async def test_query_chembl_by_smiles(self):
        mock_data = {
            "molecules": [
                {
                    "molecule_chembl_id": "CHEMBL25",
                    "pref_name": "Aspirin",
                    "molecule_structures": {"canonical_smiles": "CC(=O)Oc1ccccc1C(=O)O"},
                }
            ]
        }
        with patch.object(
            database_tools, "_request_with_retry", new_callable=AsyncMock, return_value=mock_data
        ) as mock_request:
            result = await database_tools.query_chembl(smiles="CC(=O)Oc1ccccc1C(=O)O")

        assert result["source"] == "chembl"
        assert result["record_count"] == 1
        assert result["records"][0]["chembl_id"] == "CHEMBL25"
        mock_request.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_query_chembl_by_query(self):
        mock_data = {
            "molecules": [
                {"molecule_chembl_id": "CHEMBL25", "pref_name": "Aspirin", "molecule_structures": {}}
            ]
        }
        with patch.object(
            database_tools, "_request_with_retry", new_callable=AsyncMock, return_value=mock_data
        ) as mock_request:
            result = await database_tools.query_chembl(query="aspirin")

        assert result["record_count"] == 1
        call_kwargs = mock_request.await_args.kwargs
        assert "params" in call_kwargs
        assert call_kwargs["params"]["q"] == "aspirin"

    @pytest.mark.asyncio
    async def test_query_chembl_requires_parameter(self):
        with pytest.raises(ValidationException, match="需要提供 smiles 或 query"):
            await database_tools.query_chembl()


class TestQueryPubchem:
    """PubChem 查询测试。"""

    @pytest.mark.asyncio
    async def test_query_pubchem_by_smiles(self):
        mock_data = {
            "PropertyTable": {
                "Properties": [
                    {
                        "CID": 2244,
                        "IsomericSMILES": "CC(=O)Oc1ccccc1C(=O)O",
                        "MolecularFormula": "C9H8O4",
                        "MolecularWeight": 180.16,
                        "IUPACName": "2-acetoxybenzoic acid",
                    }
                ]
            }
        }
        with patch.object(
            database_tools, "_request_with_retry", new_callable=AsyncMock, return_value=mock_data
        ):
            result = await database_tools.query_pubchem(smiles="CC(=O)Oc1ccccc1C(=O)O")

        assert result["source"] == "pubchem"
        assert result["record_count"] == 1
        assert result["records"][0]["cid"] == 2244

    @pytest.mark.asyncio
    async def test_query_pubchem_by_name(self):
        mock_data = {"PropertyTable": {"Properties": [{"CID": 2244}]}}
        with patch.object(
            database_tools, "_request_with_retry", new_callable=AsyncMock, return_value=mock_data
        ):
            result = await database_tools.query_pubchem(query="aspirin")

        assert result["record_count"] == 1


class TestQueryPdbbind:
    """PDBbind 查询测试。"""

    @pytest.mark.asyncio
    async def test_query_pdbbind_returns_metadata(self):
        result = await database_tools.query_pdbbind(protein_pdb_id="3T5G")

        assert result["source"] == "pdbbind"
        assert result["record_count"] == 1
        assert result["records"][0]["protein_pdb_id"] == "3T5G"
        assert "download_page" in result["records"][0]

    @pytest.mark.asyncio
    async def test_query_pdbbind_without_pdb_id(self):
        result = await database_tools.query_pdbbind()

        assert result["source"] == "pdbbind"
        assert result["record_count"] == 0


class TestFeatureFlag:
    """Feature flag 测试。"""

    @pytest.mark.asyncio
    async def test_disabled_flag_raises(self, monkeypatch):
        monkeypatch.setattr(settings, "ENABLE_DATABASE_TOOLS", False)
        with pytest.raises(ValidationException, match="数据库查询工具已禁用"):
            await database_tools.query_chembl(query="aspirin")


class TestRetryAndExceptions:
    """重试与异常封装测试。"""

    @pytest.mark.asyncio
    async def test_timeout_is_wrapped(self):
        with patch.object(
            database_tools,
            "_request_with_retry",
            new_callable=AsyncMock,
            side_effect=APITimeoutException(message="timeout", api_name="ChEMBL"),
        ):
            with pytest.raises(APITimeoutException):
                await database_tools.query_chembl(query="aspirin")

    @pytest.mark.asyncio
    async def test_http_error_is_wrapped(self):
        with patch.object(
            database_tools,
            "_request_with_retry",
            new_callable=AsyncMock,
            side_effect=APIResponseException(
                message="bad request", api_name="PubChem", status_code=400
            ),
        ):
            with pytest.raises(APIResponseException):
                await database_tools.query_pubchem(query="aspirin")
