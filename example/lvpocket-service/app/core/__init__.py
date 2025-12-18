"""
核心业务逻辑模块

包含模型推理、文件处理、格式转换等核心功能

注意: 使用延迟导入避免循环依赖
"""

from app.core.errors import (
    LVPocketError,
    ValidationError,
    PredictionError,
    ConversionError,
    FileError,
    ErrorCode,
)
from app.core.gpu import get_gpu_info, is_gpu_available

__all__ = [
    # 错误处理
    "LVPocketError",
    "ValidationError",
    "PredictionError",
    "ConversionError",
    "FileError",
    "ErrorCode",
    # GPU
    "get_gpu_info",
    "is_gpu_available",
    # 以下模块按需导入，避免循环依赖
    # from app.core.file_handler import FileHandler
    # from app.core.converters import convert_output, MOL2Converter, CMAPConverter, CUBEConverter
    # from app.core.lvpocket import LVPocketPredictor, parse_pdb_simple
]


def __getattr__(name: str):
    """延迟导入，避免循环依赖"""
    if name == "FileHandler":
        from app.core.file_handler import FileHandler
        return FileHandler
    elif name == "convert_output":
        from app.core.converters import convert_output
        return convert_output
    elif name == "MOL2Converter":
        from app.core.converters import MOL2Converter
        return MOL2Converter
    elif name == "CMAPConverter":
        from app.core.converters import CMAPConverter
        return CMAPConverter
    elif name == "CUBEConverter":
        from app.core.converters import CUBEConverter
        return CUBEConverter
    elif name == "LVPocketPredictor":
        from app.core.lvpocket import LVPocketPredictor
        return LVPocketPredictor
    elif name == "parse_pdb_simple":
        from app.core.lvpocket import parse_pdb_simple
        return parse_pdb_simple
    raise AttributeError(f"module 'app.core' has no attribute '{name}'")
