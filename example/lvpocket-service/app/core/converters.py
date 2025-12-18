"""
格式转换器模块

将口袋预测结果转换为不同输出格式：MOL2、CMAP、CUBE
"""

import logging
import struct
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from app.core.errors import ConversionError, ErrorCode

logger = logging.getLogger(__name__)


@dataclass
class PocketData:
    """口袋数据结构"""

    id: int
    rank: int
    score: float
    volume: float
    center: Tuple[float, float, float]
    bounding_box: Optional[Tuple[Tuple[float, float, float], Tuple[float, float, float]]] = None
    residues: Optional[List[Dict[str, Any]]] = None
    density_map: Optional[np.ndarray] = None
    grid_origin: Optional[Tuple[float, float, float]] = None
    grid_spacing: float = 0.5


class BaseConverter(ABC):
    """格式转换器基类"""

    @property
    @abstractmethod
    def format_name(self) -> str:
        """格式名称"""
        pass

    @property
    @abstractmethod
    def file_extension(self) -> str:
        """文件扩展名"""
        pass

    @abstractmethod
    def convert(
        self,
        pockets: List[PocketData],
        protein_atoms: Optional[List[Dict]] = None,
        **kwargs,
    ) -> str:
        """
        转换口袋数据

        Args:
            pockets: 口袋数据列表
            protein_atoms: 蛋白质原子列表（某些格式需要）
            **kwargs: 额外参数

        Returns:
            转换后的文件内容字符串
        """
        pass


class MOL2Converter(BaseConverter):
    """MOL2 格式转换器"""

    @property
    def format_name(self) -> str:
        return "mol2"

    @property
    def file_extension(self) -> str:
        return ".mol2"

    def convert(
        self,
        pockets: List[PocketData],
        protein_atoms: Optional[List[Dict]] = None,
        **kwargs,
    ) -> str:
        """
        转换为 MOL2 格式

        生成包含口袋中心位置的 MOL2 文件
        """
        lines = []

        for pocket in pockets:
            # MOLECULE 记录
            lines.append("@<TRIPOS>MOLECULE")
            lines.append(f"Pocket_{pocket.id}")
            lines.append("1 0 0 0 0")  # 原子数、键数等
            lines.append("SMALL")
            lines.append("NO_CHARGES")
            lines.append("")

            # ATOM 记录 - 使用口袋中心作为虚拟原子
            lines.append("@<TRIPOS>ATOM")
            x, y, z = pocket.center
            # 格式: atom_id atom_name x y z atom_type [subst_id subst_name charge]
            lines.append(
                f"      1 C{pocket.id:<4d} {x:10.4f} {y:10.4f} {z:10.4f} "
                f"C.3     1 POC{pocket.id}    {pocket.score:.4f}"
            )
            lines.append("")

        return "\n".join(lines)

    def convert_with_residues(
        self,
        pockets: List[PocketData],
        protein_atoms: List[Dict],
        **kwargs,
    ) -> str:
        """
        转换为包含口袋残基原子的 MOL2 格式

        Args:
            pockets: 口袋数据列表
            protein_atoms: 蛋白质原子列表

        Returns:
            MOL2 格式字符串
        """
        lines = []

        for pocket in pockets:
            if not pocket.residues:
                continue

            # 收集口袋相关残基的原子
            pocket_residue_ids = {
                (r["chain"], r["resid"]) for r in pocket.residues
            }

            pocket_atoms = [
                atom
                for atom in protein_atoms
                if (atom.get("chain"), atom.get("resid")) in pocket_residue_ids
            ]

            if not pocket_atoms:
                continue

            # MOLECULE 记录
            lines.append("@<TRIPOS>MOLECULE")
            lines.append(f"Pocket_{pocket.id}")
            lines.append(f"{len(pocket_atoms)} 0 0 0 0")
            lines.append("PROTEIN")
            lines.append("NO_CHARGES")
            lines.append("")

            # ATOM 记录
            lines.append("@<TRIPOS>ATOM")
            for i, atom in enumerate(pocket_atoms, 1):
                x, y, z = atom["x"], atom["y"], atom["z"]
                atom_name = atom.get("name", "X")
                atom_type = self._get_mol2_atom_type(atom_name)
                resname = atom.get("resname", "UNK")
                resid = atom.get("resid", 1)

                lines.append(
                    f"{i:>7d} {atom_name:<4s} {x:10.4f} {y:10.4f} {z:10.4f} "
                    f"{atom_type:<5s} {resid:>5d} {resname:<4s} 0.0000"
                )
            lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _get_mol2_atom_type(atom_name: str) -> str:
        """根据原子名获取 MOL2 原子类型"""
        element = atom_name[0].upper()
        type_map = {
            "C": "C.3",
            "N": "N.am",
            "O": "O.2",
            "S": "S.3",
            "H": "H",
            "P": "P.3",
        }
        return type_map.get(element, "X")


class CMAPConverter(BaseConverter):
    """CMAP (Chimera) 格式转换器"""

    @property
    def format_name(self) -> str:
        return "cmap"

    @property
    def file_extension(self) -> str:
        return ".cmap"

    def convert(
        self,
        pockets: List[PocketData],
        protein_atoms: Optional[List[Dict]] = None,
        **kwargs,
    ) -> str:
        """
        转换为 CMAP 格式（Chimera 兼容）

        CMAP 是二进制格式，这里返回的是文件内容的十六进制表示
        实际使用时应调用 convert_binary 方法
        """
        raise ConversionError(
            message="CMAP format requires binary output, use convert_binary() method",
            code=ErrorCode.CONVERSION_FAILED,
        )

    def convert_binary(
        self,
        density_map: np.ndarray,
        origin: Tuple[float, float, float],
        spacing: float,
    ) -> bytes:
        """
        转换为 CMAP 二进制格式

        Args:
            density_map: 3D 密度图数组
            origin: 网格原点坐标
            spacing: 网格间距

        Returns:
            二进制数据
        """
        # CMAP 文件头
        header = bytearray(256)

        # 网格维度
        nx, ny, nz = density_map.shape
        struct.pack_into("<3i", header, 0, nx, ny, nz)

        # 模式 (2 = float32)
        struct.pack_into("<i", header, 12, 2)

        # 起始索引
        struct.pack_into("<3i", header, 16, 0, 0, 0)

        # 网格数
        struct.pack_into("<3i", header, 28, nx, ny, nz)

        # 晶胞尺寸
        cell_a = nx * spacing
        cell_b = ny * spacing
        cell_c = nz * spacing
        struct.pack_into("<3f", header, 40, cell_a, cell_b, cell_c)

        # 晶胞角度
        struct.pack_into("<3f", header, 52, 90.0, 90.0, 90.0)

        # 轴映射
        struct.pack_into("<3i", header, 64, 1, 2, 3)

        # 统计信息
        dmin, dmax = float(density_map.min()), float(density_map.max())
        dmean = float(density_map.mean())
        struct.pack_into("<3f", header, 76, dmin, dmax, dmean)

        # 原点
        struct.pack_into("<3f", header, 196, *origin)

        # 组装数据
        data = density_map.astype(np.float32).tobytes()

        return bytes(header) + data


class CUBEConverter(BaseConverter):
    """Gaussian Cube 格式转换器"""

    @property
    def format_name(self) -> str:
        return "cube"

    @property
    def file_extension(self) -> str:
        return ".cube"

    def convert(
        self,
        pockets: List[PocketData],
        protein_atoms: Optional[List[Dict]] = None,
        **kwargs,
    ) -> str:
        """
        转换为 Gaussian Cube 格式

        需要提供密度图数据
        """
        # 获取第一个口袋的密度图（如果有）
        pocket_with_density = None
        for pocket in pockets:
            if pocket.density_map is not None:
                pocket_with_density = pocket
                break

        if pocket_with_density is None:
            raise ConversionError(
                message="No density map data available for CUBE conversion",
                code=ErrorCode.CONVERSION_FAILED,
            )

        return self.convert_from_density(
            density_map=pocket_with_density.density_map,
            origin=pocket_with_density.grid_origin or (0.0, 0.0, 0.0),
            spacing=pocket_with_density.grid_spacing,
            atoms=protein_atoms,
        )

    def convert_from_density(
        self,
        density_map: np.ndarray,
        origin: Tuple[float, float, float],
        spacing: float,
        atoms: Optional[List[Dict]] = None,
    ) -> str:
        """
        从密度图生成 Cube 格式

        Args:
            density_map: 3D 密度数组
            origin: 网格原点 (Å)
            spacing: 网格间距 (Å)
            atoms: 原子列表（可选）

        Returns:
            Cube 格式字符串
        """
        lines = []

        # 注释行
        lines.append("LVPocket density map")
        lines.append(f"Generated with spacing {spacing} Angstrom")

        # 转换为 Bohr (1 Å = 1.8897259886 Bohr)
        ANGSTROM_TO_BOHR = 1.8897259886
        origin_bohr = tuple(o * ANGSTROM_TO_BOHR for o in origin)
        spacing_bohr = spacing * ANGSTROM_TO_BOHR

        nx, ny, nz = density_map.shape
        n_atoms = len(atoms) if atoms else 0

        # 原子数和原点（正数表示密度值，负数表示轨道）
        lines.append(
            f"{n_atoms:5d} {origin_bohr[0]:12.6f} {origin_bohr[1]:12.6f} {origin_bohr[2]:12.6f}"
        )

        # 网格向量
        lines.append(f"{nx:5d} {spacing_bohr:12.6f} {0.0:12.6f} {0.0:12.6f}")
        lines.append(f"{ny:5d} {0.0:12.6f} {spacing_bohr:12.6f} {0.0:12.6f}")
        lines.append(f"{nz:5d} {0.0:12.6f} {0.0:12.6f} {spacing_bohr:12.6f}")

        # 原子坐标
        if atoms:
            for atom in atoms:
                atomic_num = self._get_atomic_number(atom.get("element", atom.get("name", "C")[0]))
                x = atom["x"] * ANGSTROM_TO_BOHR
                y = atom["y"] * ANGSTROM_TO_BOHR
                z = atom["z"] * ANGSTROM_TO_BOHR
                lines.append(f"{atomic_num:5d} {0.0:12.6f} {x:12.6f} {y:12.6f} {z:12.6f}")

        # 密度数据
        # Cube 格式: 外层循环 x, 中层循环 y, 内层循环 z
        values = []
        for ix in range(nx):
            for iy in range(ny):
                for iz in range(nz):
                    values.append(density_map[ix, iy, iz])

        # 每行 6 个值
        for i in range(0, len(values), 6):
            row = values[i : i + 6]
            lines.append(" ".join(f"{v:13.5E}" for v in row))

        return "\n".join(lines)

    @staticmethod
    def _get_atomic_number(element: str) -> int:
        """获取原子序数"""
        atomic_numbers = {
            "H": 1, "C": 6, "N": 7, "O": 8, "F": 9,
            "P": 15, "S": 16, "CL": 17, "BR": 35, "I": 53,
            "FE": 26, "ZN": 30, "MG": 12, "CA": 20, "NA": 11,
            "K": 19, "MN": 25, "CO": 27, "CU": 29, "NI": 28,
        }
        return atomic_numbers.get(element.upper(), 6)  # 默认返回碳


class JSONConverter(BaseConverter):
    """JSON 格式转换器（用于标准输出）"""

    @property
    def format_name(self) -> str:
        return "json"

    @property
    def file_extension(self) -> str:
        return ".json"

    def convert(
        self,
        pockets: List[PocketData],
        protein_atoms: Optional[List[Dict]] = None,
        **kwargs,
    ) -> str:
        """转换为 JSON 格式"""
        import json

        result = []
        for pocket in pockets:
            pocket_dict = {
                "id": pocket.id,
                "rank": pocket.rank,
                "score": pocket.score,
                "volume": pocket.volume,
                "center": {"x": pocket.center[0], "y": pocket.center[1], "z": pocket.center[2]},
            }

            if pocket.bounding_box:
                pocket_dict["bounding_box"] = {
                    "min": {
                        "x": pocket.bounding_box[0][0],
                        "y": pocket.bounding_box[0][1],
                        "z": pocket.bounding_box[0][2],
                    },
                    "max": {
                        "x": pocket.bounding_box[1][0],
                        "y": pocket.bounding_box[1][1],
                        "z": pocket.bounding_box[1][2],
                    },
                }

            if pocket.residues:
                pocket_dict["residues"] = pocket.residues

            result.append(pocket_dict)

        return json.dumps(result, indent=2)


# 转换器注册表
CONVERTERS: Dict[str, BaseConverter] = {
    "mol2": MOL2Converter(),
    "cmap": CMAPConverter(),
    "cube": CUBEConverter(),
    "json": JSONConverter(),
}


def convert_output(
    pockets: List[PocketData],
    output_format: str,
    protein_atoms: Optional[List[Dict]] = None,
    **kwargs,
) -> str:
    """
    统一格式转换接口

    Args:
        pockets: 口袋数据列表
        output_format: 目标格式
        protein_atoms: 蛋白质原子列表
        **kwargs: 额外参数

    Returns:
        转换后的内容字符串

    Raises:
        ConversionError: 转换失败
    """
    converter = CONVERTERS.get(output_format.lower())
    if converter is None:
        raise ConversionError(
            message=f"Unsupported output format: {output_format}",
            code=ErrorCode.UNSUPPORTED_OUTPUT_FORMAT,
            details={
                "requested": output_format,
                "supported": list(CONVERTERS.keys()),
            },
        )

    try:
        return converter.convert(pockets, protein_atoms, **kwargs)
    except ConversionError:
        raise
    except Exception as e:
        logger.error(f"格式转换失败: {output_format}, {e}")
        raise ConversionError(
            message=f"Conversion to {output_format} failed: {e}",
            code=ErrorCode.CONVERSION_FAILED,
            details={"format": output_format, "error": str(e)},
        )


def get_converter(output_format: str) -> BaseConverter:
    """获取指定格式的转换器"""
    converter = CONVERTERS.get(output_format.lower())
    if converter is None:
        raise ConversionError(
            message=f"Unsupported output format: {output_format}",
            code=ErrorCode.UNSUPPORTED_OUTPUT_FORMAT,
            details={"requested": output_format, "supported": list(CONVERTERS.keys())},
        )
    return converter
