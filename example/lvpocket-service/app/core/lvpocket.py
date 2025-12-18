"""
LVPocket 预测器模块

封装 LV_NET 模型，提供蛋白质结合口袋预测 API
直接引用 LVpocket 源代码，避免代码冗余

支持多模型：
- 根据蛋白质二级结构（SCOP 分类）选择对应的预训练模型
- baseline: 基线模型（默认）
- alpha: α 类蛋白质模型
- beta: β 类蛋白质模型
- alpha_beta: α/β 类蛋白质模型
- alpha_plus_beta: α+β 类蛋白质模型
"""

import logging
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np

from app.config import settings, SCOPClass
from app.core.converters import PocketData
from app.core.errors import ErrorCode, FileError, PredictionError

logger = logging.getLogger(__name__)


# ==================== 初始化 LVpocket 路径 ====================


def setup_lvpocket_path():
    """
    设置 LVpocket 源代码路径到 sys.path

    确保可以正确导入 model.LV_former 和 tfbio.data 模块
    """
    lvpocket_path = settings.LVPOCKET_SOURCE_PATH
    if lvpocket_path and os.path.exists(lvpocket_path):
        if lvpocket_path not in sys.path:
            sys.path.insert(0, lvpocket_path)
            logger.info(f"已添加 LVpocket 源码路径: {lvpocket_path}")
    else:
        logger.warning(f"LVpocket 源码路径不存在: {lvpocket_path}")


# 在模块加载时设置路径
setup_lvpocket_path()


# ==================== 数据类 ====================


@dataclass
class ProteinInfo:
    """蛋白质信息"""
    name: str
    num_atoms: int
    atoms: List[Dict[str, Any]] = field(default_factory=list)
    mol: Any = None  # pybel.Molecule 对象


@dataclass
class PredictionResult:
    """预测结果"""
    protein_info: ProteinInfo
    pockets: List[PocketData]
    processing_time: float
    structure_class: str = "baseline"  # 使用的结构分类
    model_file: str = ""  # 使用的模型文件名
    density_map: Optional[np.ndarray] = None
    grid_origin: Optional[Tuple[float, float, float]] = None
    grid_spacing: float = 0.5


# ==================== 独立工具函数 ====================


def parse_pdb_simple(protein_file: Path) -> ProteinInfo:
    """
    简单的 PDB 文件解析（备用方案，当 pybel 不可用时使用）

    Args:
        protein_file: PDB 文件路径

    Returns:
        ProteinInfo: 蛋白质信息
    """
    atoms = []

    with open(protein_file, "r") as f:
        for line in f:
            if line.startswith(("ATOM", "HETATM")):
                try:
                    atom = {
                        "id": int(line[6:11].strip()),
                        "name": line[12:16].strip(),
                        "resname": line[17:20].strip(),
                        "chain": line[21].strip() or "A",
                        "resid": int(line[22:26].strip()),
                        "x": float(line[30:38].strip()),
                        "y": float(line[38:46].strip()),
                        "z": float(line[46:54].strip()),
                        "element": line[76:78].strip() if len(line) > 76 else line[12:14].strip()[0],
                    }
                    atoms.append(atom)
                except (ValueError, IndexError):
                    continue

    if not atoms:
        raise FileError(
            message="No atoms found in PDB file",
            code=ErrorCode.FILE_PARSE_FAILED,
        )

    return ProteinInfo(
        name=Path(protein_file).stem,
        num_atoms=len(atoms),
        atoms=atoms,
        mol=None,
    )


class LVPocketPredictor:
    """
    LVPocket 蛋白质结合口袋预测器

    封装 LV_NET 双路径架构（3D CNN + Transformer）进行口袋预测

    直接使用 LVpocket 源代码中的模块：
    - model.LV_former.LV_NET: 模型定义
    - tfbio.data.Featurizer: 特征提取器
    - pybel: 分子文件读取

    支持多模型：
    - 根据蛋白质二级结构（SCOP 分类）动态加载对应的预训练模型
    - 模型缓存机制：已加载的模型会被缓存，避免重复加载
    """

    def __init__(
        self,
        model_path: Optional[str] = None,
        scale: float = 0.5,
        max_dist: float = 35.0,
        structure_class: str = "baseline",
    ):
        """
        初始化预测器

        参考 LVpocket/scripts/predict.py 的实现方式

        Args:
            model_path: 模型文件路径 (.h5/.hdf)，为 None 时根据 structure_class 自动选择
            scale: 体素分辨率 (Å)，默认 0.5
            max_dist: 最大距离阈值，默认 35.0
            structure_class: 蛋白质结构分类 (baseline/alpha/beta/alpha_beta/alpha_plus_beta)
        """
        self.scale = scale
        self.max_dist = max_dist

        # 当前使用的结构分类
        self._current_structure_class = structure_class

        # 根据 structure_class 获取模型路径
        if model_path is None:
            self.model_path = settings.get_model_path(structure_class)
        else:
            self.model_path = model_path

        # 获取当前模型文件名
        self._current_model_file = os.path.basename(self.model_path)

        # 模型缓存：{structure_class: model}
        self._model_cache: Dict[str, Any] = {}

        # 当前使用的模型
        self.model = None
        self._pybel = None
        self._openbabel = None
        self._Featurizer = None
        self._LV_NET = None
        self._mock_mode = False

        # 加载依赖模块和初始模型
        self._load_dependencies()
        self._load_model(structure_class)

    def _load_dependencies(self):
        """
        加载 LVpocket 依赖模块

        从 LVpocket 源代码导入所需模块：
        - model.LV_former.LV_NET
        - tfbio.data.Featurizer
        - pybel, openbabel
        """
        try:
            # 配置 TensorFlow 日志级别
            os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"

            # 从 LVpocket 源代码导入所需模块
            # 参考 predict.py 第 16-17 行
            from model.LV_former import LV_NET
            from tfbio.data import Featurizer
            import pybel
            import openbabel

            self._LV_NET = LV_NET
            self._Featurizer = Featurizer
            self._pybel = pybel
            self._openbabel = openbabel

            logger.info("LVpocket 依赖模块加载成功")
            self._mock_mode = False

        except ImportError as e:
            logger.warning(f"无法导入 LVpocket 模块: {e}，启用模拟模式")
            self._mock_mode = True

    def _load_model(self, structure_class: str = "baseline"):
        """
        加载指定结构分类的 LV_NET 模型

        支持模型缓存机制，避免重复加载同一模型

        参考 predict.py 第 106-111 行:
        model = LV_NET.load_model(
            args.model,
            scale=args.scale,
            max_dist=args.max_dist,
            featurizer=Featurizer(save_molecule_codes=False),
        )

        Args:
            structure_class: 蛋白质结构分类
        """
        # 验证结构分类
        if structure_class not in SCOPClass.ALL_CLASSES:
            logger.warning(f"未知的结构分类: {structure_class}，使用默认模型")
            structure_class = settings.DEFAULT_MODEL

        # 检查缓存
        if structure_class in self._model_cache:
            logger.info(f"从缓存加载模型: {structure_class}")
            self.model = self._model_cache[structure_class]
            self._current_structure_class = structure_class
            self._current_model_file = settings.MODEL_FILES.get(structure_class, "scale_0.5_1.h5")
            self.model_path = settings.get_model_path(structure_class)
            return

        # 如果是模拟模式，跳过模型加载
        if self._mock_mode:
            self._current_structure_class = structure_class
            self._current_model_file = settings.MODEL_FILES.get(structure_class, "scale_0.5_1.h5")
            self.model_path = settings.get_model_path(structure_class)
            return

        try:
            # 获取模型路径
            model_path = settings.get_model_path(structure_class)

            # 检查模型文件是否存在
            if not os.path.exists(model_path):
                logger.warning(f"模型文件不存在: {model_path}，尝试使用基线模型")
                model_path = settings.get_model_path("baseline")
                structure_class = "baseline"

                if not os.path.exists(model_path):
                    raise PredictionError(
                        message=f"Model file not found: {model_path}",
                        code=ErrorCode.MODEL_LOAD_FAILED,
                        details={"model_path": model_path},
                    )

            # 加载模型
            logger.info(f"加载模型: {model_path} (structure_class={structure_class})")
            model = self._LV_NET.load_model(
                model_path,
                scale=self.scale,
                max_dist=self.max_dist,
                featurizer=self._Featurizer(save_molecule_codes=False),
            )

            # 缓存模型
            self._model_cache[structure_class] = model
            self.model = model
            self._current_structure_class = structure_class
            self._current_model_file = os.path.basename(model_path)
            self.model_path = model_path

            logger.info(f"LV_NET 模型加载成功: {structure_class} ({self._current_model_file})")

        except Exception as e:
            logger.error(f"模型加载失败: {e}")
            raise PredictionError(
                message=f"Failed to load model: {e}",
                code=ErrorCode.MODEL_LOAD_FAILED,
                details={"model_path": model_path, "structure_class": structure_class, "error": str(e)},
            )

    def switch_model(self, structure_class: str) -> bool:
        """
        切换到指定结构分类的模型

        Args:
            structure_class: 目标结构分类

        Returns:
            切换是否成功
        """
        if structure_class == self._current_structure_class:
            logger.debug(f"已在使用 {structure_class} 模型，无需切换")
            return True

        logger.info(f"切换模型: {self._current_structure_class} -> {structure_class}")
        self._load_model(structure_class)
        return True

    def get_current_model_info(self) -> Dict[str, str]:
        """获取当前使用的模型信息"""
        return {
            "structure_class": self._current_structure_class,
            "model_file": self._current_model_file,
            "model_path": self.model_path,
            "description": SCOPClass.DESCRIPTIONS.get(self._current_structure_class, ""),
        }

    def predict(
        self,
        protein_file: Union[str, Path],
        threshold: float = 0.5,
        min_size: int = 50,
        output_formats: Optional[List[str]] = None,
        structure_class: Optional[str] = None,
    ) -> PredictionResult:
        """
        执行蛋白质结合口袋预测

        参考 predict.py 第 127-137 行的预测流程:
        mol = next(pybel.readfile(args.format, path))
        model.save_pocket_mol2(mol, dirname)
        density, origin, step = model.pocket_density_from_mol(mol)

        Args:
            protein_file: 蛋白质结构文件路径 (PDB/MOL2)
            threshold: 口袋预测阈值 (0-1)
            min_size: 最小口袋体素数
            output_formats: 输出格式列表
            structure_class: 蛋白质结构分类，用于选择对应模型

        Returns:
            PredictionResult: 预测结果
        """
        start_time = time.time()
        protein_file = Path(protein_file)

        # 如果指定了结构分类，切换到对应模型
        if structure_class is not None and structure_class != self._current_structure_class:
            self.switch_model(structure_class)

        # 解析蛋白质文件
        protein_info = self._parse_protein(protein_file)

        # 执行预测
        if self._mock_mode:
            pockets, density_map, origin = self._mock_predict(
                protein_info, threshold, min_size
            )
        else:
            pockets, density_map, origin = self._real_predict(
                protein_info, protein_file, threshold, min_size
            )

        processing_time = time.time() - start_time

        return PredictionResult(
            protein_info=protein_info,
            pockets=pockets,
            processing_time=processing_time,
            structure_class=self._current_structure_class,
            model_file=self._current_model_file,
            density_map=density_map,
            grid_origin=origin,
            grid_spacing=self.scale,
        )

    def _parse_protein(self, protein_file: Path) -> ProteinInfo:
        """
        解析蛋白质结构文件

        使用 pybel.readfile 读取分子（与 predict.py 第 129 行一致）
        """
        suffix = protein_file.suffix.lower()
        file_format = "pdb" if suffix == ".pdb" else "mol2"

        try:
            if self._pybel is not None:
                # 使用 pybel 读取分子（参考 predict.py 第 129 行）
                mol = next(self._pybel.readfile(file_format, str(protein_file)))

                # 提取原子信息
                atoms = []
                for atom in mol.atoms:
                    residue = atom.OBAtom.GetResidue()
                    atoms.append({
                        "id": atom.idx,
                        "name": residue.GetAtomID(atom.OBAtom).strip() if residue else "X",
                        "element": self._openbabel.GetSymbol(atom.atomicnum),
                        "x": atom.coords[0],
                        "y": atom.coords[1],
                        "z": atom.coords[2],
                        "resname": residue.GetName() if residue else "UNK",
                        "resid": residue.GetNum() if residue else 0,
                        "chain": residue.GetChain() if residue else "A",
                    })

                return ProteinInfo(
                    name=protein_file.stem,
                    num_atoms=len(atoms),
                    atoms=atoms,
                    mol=mol,  # 保存 pybel.Molecule 对象，后续预测使用
                )
            else:
                # 备用方案：简单 PDB 解析
                return parse_pdb_simple(protein_file)

        except StopIteration:
            raise FileError(
                message=f"Cannot read molecule from file: {protein_file}",
                code=ErrorCode.FILE_PARSE_FAILED,
            )
        except Exception as e:
            logger.error(f"蛋白质文件解析失败: {e}")
            raise FileError(
                message=f"Failed to parse protein file: {e}",
                code=ErrorCode.FILE_PARSE_FAILED,
                details={"file": str(protein_file), "error": str(e)},
            )

    def _real_predict(
        self,
        protein_info: ProteinInfo,
        protein_file: Path,
        threshold: float,
        min_size: int,
    ) -> Tuple[List[PocketData], Optional[np.ndarray], Optional[Tuple[float, float, float]]]:
        """
        使用真实 LV_NET 模型进行预测

        参考 predict.py 第 132-137 行:
        model.save_pocket_mol2(mol, dirname)
        density, origin, step = model.pocket_density_from_mol(mol)
        model.save_density_as_cmap(density, origin, step, fname=...)
        """
        try:
            mol = protein_info.mol
            if mol is None:
                # 重新读取分子
                suffix = protein_file.suffix.lower()
                file_format = "pdb" if suffix == ".pdb" else "mol2"
                mol = next(self._pybel.readfile(file_format, str(protein_file)))

            # 计算口袋密度（参考 predict.py 第 134 行）
            logger.info("计算口袋密度...")
            density, origin, step = self.model.pocket_density_from_mol(mol)

            # 口袋分割（使用 LV_NET 的 get_pockets_segmentation 方法）
            logger.info(f"口袋分割 (threshold={threshold}, min_size={min_size})...")
            pockets_segmentation = self.model.get_pockets_segmentation(
                density,
                threshold=threshold,
                min_size=min_size,
            )

            # 从分割结果提取口袋信息
            pockets = self._extract_pockets_from_segmentation(
                pockets_segmentation,
                density,
                origin,
                step,
                protein_info.atoms,
            )

            logger.info(f"检测到 {len(pockets)} 个口袋")
            return pockets, density, tuple(origin)

        except Exception as e:
            logger.error(f"预测失败: {e}")
            raise PredictionError(
                message=f"Prediction failed: {e}",
                code=ErrorCode.PREDICTION_FAILED,
                details={"error": str(e)},
            )

    def _extract_pockets_from_segmentation(
        self,
        label_image: np.ndarray,
        density: np.ndarray,
        origin: np.ndarray,
        step: np.ndarray,
        atoms: List[Dict],
    ) -> List[PocketData]:
        """
        从口袋分割结果提取口袋信息

        Args:
            label_image: 分割后的标签图像
            density: 原始密度图
            origin: 网格原点
            step: 网格步长
            atoms: 蛋白质原子列表

        Returns:
            PocketData 列表
        """
        pockets = []
        voxel_size = (1 / self.scale) ** 3

        # 获取所有唯一的口袋标签（排除背景 0）
        unique_labels = np.unique(label_image)
        unique_labels = unique_labels[unique_labels > 0]

        for pocket_label in unique_labels:
            # 获取当前口袋的体素索引
            pocket_mask = label_image == pocket_label
            indices = np.argwhere(pocket_mask)

            if len(indices) == 0:
                continue

            # 计算口袋中心（世界坐标）
            indices_world = indices.astype(np.float32) * step + origin
            center = indices_world.mean(axis=0)

            # 计算边界框
            min_coords = indices_world.min(axis=0)
            max_coords = indices_world.max(axis=0)

            # 计算体积
            volume = len(indices) * voxel_size

            # 计算分数（密度加权平均）
            if density is not None and len(density) > 0:
                density_values = density[0][pocket_mask]
                score = float(np.mean(density_values))
            else:
                score = 1.0 - (pocket_label - 1) * 0.1

            # 获取口袋相关残基
            residues = self._get_pocket_residues(center, atoms, radius=6.0)

            pocket = PocketData(
                id=int(pocket_label),
                rank=int(pocket_label),
                score=round(score, 4),
                volume=round(volume, 2),
                center=(round(center[0], 3), round(center[1], 3), round(center[2], 3)),
                bounding_box=(
                    (round(min_coords[0], 3), round(min_coords[1], 3), round(min_coords[2], 3)),
                    (round(max_coords[0], 3), round(max_coords[1], 3), round(max_coords[2], 3)),
                ),
                residues=residues,
                grid_origin=tuple(origin),
                grid_spacing=float(step[0]) if isinstance(step, np.ndarray) else float(step),
            )
            pockets.append(pocket)

        # 按分数排序
        pockets.sort(key=lambda p: p.score, reverse=True)
        for i, pocket in enumerate(pockets, 1):
            pocket.rank = i

        return pockets

    def _mock_predict(
        self,
        protein_info: ProteinInfo,
        threshold: float,
        min_size: int,
    ) -> Tuple[List[PocketData], Optional[np.ndarray], Optional[Tuple[float, float, float]]]:
        """
        模拟预测（当 LVpocket 模块不可用时使用）
        """
        if not protein_info.atoms:
            return [], None, None

        coords = np.array([[a["x"], a["y"], a["z"]] for a in protein_info.atoms])
        center = coords.mean(axis=0)
        min_coord = coords.min(axis=0)
        max_coord = coords.max(axis=0)

        np.random.seed(hash(protein_info.name) % (2**32))
        num_pockets = np.random.randint(1, 4)

        pockets = []
        for i in range(num_pockets):
            offset = np.random.uniform(-10, 10, 3)
            pocket_center = center + offset
            pocket_center = np.clip(pocket_center, min_coord - 5, max_coord + 5)

            residues = self._get_pocket_residues(pocket_center, protein_info.atoms, radius=8.0)

            pocket = PocketData(
                id=i + 1,
                rank=i + 1,
                score=round(0.9 - i * 0.15 + np.random.uniform(-0.05, 0.05), 3),
                volume=round(300 + np.random.uniform(-100, 200), 1),
                center=tuple(pocket_center.round(2)),
                bounding_box=(
                    tuple((pocket_center - 6).round(2)),
                    tuple((pocket_center + 6).round(2)),
                ),
                residues=residues[:10],
                grid_spacing=self.scale,
            )
            pockets.append(pocket)

        pockets.sort(key=lambda p: p.score, reverse=True)
        for i, pocket in enumerate(pockets, 1):
            pocket.rank = i

        return pockets, None, tuple(min_coord - 5)

    def _get_pocket_residues(
        self,
        center: Union[np.ndarray, Tuple[float, float, float]],
        atoms: List[Dict],
        radius: float = 6.0,
    ) -> List[Dict[str, Any]]:
        """获取口袋附近的残基"""
        center = np.array(center)
        seen_residues = set()
        residues = []

        for atom in atoms:
            atom_coord = np.array([atom["x"], atom["y"], atom["z"]])
            distance = np.linalg.norm(atom_coord - center)

            if distance <= radius:
                res_key = (atom["chain"], atom["resname"], atom["resid"])
                if res_key not in seen_residues:
                    seen_residues.add(res_key)
                    residues.append({
                        "chain": atom["chain"],
                        "resname": atom["resname"],
                        "resid": atom["resid"],
                    })

        return residues

    def save_pocket_mol2(
        self,
        mol: Any,
        output_dir: Union[str, Path],
        threshold: float = 0.5,
        min_size: int = 50,
    ) -> List[Path]:
        """
        保存口袋为 MOL2 文件

        直接调用 LV_NET.save_pocket_mol2 方法
        参考 predict.py 第 132 行: model.save_pocket_mol2(mol, dirname)
        """
        if self._mock_mode or self.model is None:
            logger.warning("模拟模式下无法保存 MOL2 文件")
            return []

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        self.model.save_pocket_mol2(mol, str(output_dir), threshold=threshold, min_size=min_size)

        return list(output_dir.glob("pocket*.mol2"))

    def save_density_cmap(
        self,
        density: np.ndarray,
        origin: Tuple[float, float, float],
        step: Union[float, np.ndarray],
        output_path: Union[str, Path],
        name: str = "protein",
    ):
        """
        保存密度图为 CMAP 格式

        直接调用 LV_NET.save_density_as_cmap 方法
        参考 predict.py 第 135-137 行
        """
        if self._mock_mode or self.model is None:
            logger.warning("模拟模式下无法保存 CMAP 文件")
            return

        if isinstance(step, (int, float)):
            step = np.array([step, step, step])

        self.model.save_density_as_cmap(
            density,
            np.array(origin),
            step,
            fname=str(output_path),
            name=name,
        )

    def get_model_info(self) -> Dict[str, Any]:
        """获取模型信息"""
        # 获取所有可用模型
        available_models = settings.get_available_models()

        return {
            "model_name": "LV_NET",
            "model_version": settings.MODEL_VERSION,
            "model_path": self.model_path,
            "architecture": {
                "type": "LV_NET",
                "v_path": "3D CNN",
                "l_path": "Transformer",
                "total_params": "3.7M",
            },
            "config": {
                "scale": self.scale,
                "max_dist": self.max_dist,
                "input_shape": [36, 36, 36, 18],
                "output_shape": [36, 36, 36, 1],
            },
            "supported_inputs": ["pdb", "mol2"],
            "supported_outputs": ["json", "mol2", "cmap", "cube"],
            "mock_mode": self._mock_mode,
            # 多模型信息
            "current_structure_class": self._current_structure_class,
            "current_model_file": self._current_model_file,
            "default_structure_class": settings.DEFAULT_MODEL,
            "available_models": available_models,
        }

    def close(self):
        """释放资源"""
        self.model = None
        logger.info("预测器资源已释放")
