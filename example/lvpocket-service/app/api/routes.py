"""
API 路由定义

定义所有 HTTP 端点和请求处理逻辑
"""

import json
import logging
import time
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.api.dependencies import get_model_manager, get_predictor, ModelManager
from app.api.schemas import (
    AvailableModel,
    BatchRequest,
    BatchResponse,
    BatchResult,
    BatchItemResult,
    ConvertRequest,
    ConvertResponse,
    ConvertResult,
    ErrorResponse,
    FormatInfo,
    FormatsResponse,
    FormatsResult,
    HealthResponse,
    ModelInfoResponse,
    ModelInfoResult,
    ModelArchitecture,
    ModelConfig,
    OutputFile,
    PocketInfo,
    PredictRequest,
    PredictResponse,
    PredictResult,
    Coordinate,
    BoundingBox,
    Residue,
    StructureClass,
)
from app.config import settings
from app.core.converters import PocketData, get_converter
from app.core.errors import LVPocketError, ErrorCode, ValidationError
from app.core.file_handler import FileHandler, get_file_handler
from app.core.gpu import get_gpu_info
from app.core.lvpocket import LVPocketPredictor, parse_pdb_simple

logger = logging.getLogger(__name__)

router = APIRouter()


# ==================== 辅助函数 ====================


def _pocket_data_to_info(pocket: PocketData) -> PocketInfo:
    """
    将 PocketData 转换为 PocketInfo (DRY 原则)

    Args:
        pocket: 核心层口袋数据

    Returns:
        PocketInfo: API 响应用口袋信息
    """
    return PocketInfo(
        id=pocket.id,
        rank=pocket.rank,
        score=pocket.score,
        volume=pocket.volume,
        center=Coordinate(x=pocket.center[0], y=pocket.center[1], z=pocket.center[2]),
        bounding_box=BoundingBox(
            min=Coordinate(
                x=pocket.bounding_box[0][0],
                y=pocket.bounding_box[0][1],
                z=pocket.bounding_box[0][2],
            ),
            max=Coordinate(
                x=pocket.bounding_box[1][0],
                y=pocket.bounding_box[1][1],
                z=pocket.bounding_box[1][2],
            ),
        ) if pocket.bounding_box else None,
        residues=[Residue(**r) for r in pocket.residues] if pocket.residues else None,
    )


# ==================== 健康检查 ====================


@router.get("/health", response_model=HealthResponse, tags=["健康检查"])
async def health_check(
    model_manager: ModelManager = Depends(get_model_manager),
):
    """
    健康检查端点

    返回服务运行状态、模型加载状态和 GPU 信息
    """
    gpu_info = get_gpu_info()

    status = "healthy" if model_manager.is_loaded and gpu_info.available else "unhealthy"

    return HealthResponse(
        status=status,
        model_loaded=model_manager.is_loaded,
        gpu_available=gpu_info.available,
        gpu_name=gpu_info.name,
        gpu_memory_total=gpu_info.memory_total,
        gpu_memory_used=gpu_info.memory_used,
        version=settings.APP_VERSION,
        uptime=model_manager.uptime,
    )


# ==================== 模型信息 ====================


@router.get("/model/info", response_model=ModelInfoResponse, tags=["模型信息"])
async def model_info(
    model_manager: ModelManager = Depends(get_model_manager),
):
    """
    获取加载的模型详细信息

    包含当前使用的模型和所有可用的 SCOP 分类模型
    """
    if not model_manager.is_loaded:
        raise HTTPException(status_code=503, detail="Model not loaded")

    predictor = model_manager.predictor
    info = predictor.get_model_info()

    # 构建可用模型列表
    available_models = []
    for class_name, model_info in info.get("available_models", {}).items():
        available_models.append(AvailableModel(
            structure_class=class_name,
            file=model_info["file"],
            path=model_info["path"],
            exists=model_info["exists"],
            description=model_info["description"],
        ))

    return ModelInfoResponse(
        success=True,
        result=ModelInfoResult(
            model_name=info["model_name"],
            model_version=info["model_version"],
            model_path=info["model_path"],
            architecture=ModelArchitecture(**info["architecture"]),
            config=ModelConfig(**info["config"]),
            supported_inputs=info["supported_inputs"],
            supported_outputs=info["supported_outputs"],
            default_structure_class=info.get("default_structure_class", "baseline"),
            available_models=available_models,
        ),
    )


# ==================== 支持的格式 ====================


@router.get("/formats", response_model=FormatsResponse, tags=["格式信息"])
async def supported_formats():
    """
    获取服务支持的输入输出格式
    """
    input_formats = [
        FormatInfo(
            format="pdb",
            extension=".pdb",
            mime_type="chemical/x-pdb",
            description="Protein Data Bank 格式",
        ),
        FormatInfo(
            format="mol2",
            extension=".mol2",
            mime_type="chemical/x-mol2",
            description="Tripos MOL2 格式",
        ),
    ]

    output_formats = [
        FormatInfo(
            format="json",
            extension=".json",
            mime_type="application/json",
            description="JSON 结构化数据",
        ),
        FormatInfo(
            format="mol2",
            extension=".mol2",
            mime_type="chemical/x-mol2",
            description="口袋原子坐标 MOL2 格式",
        ),
        FormatInfo(
            format="cmap",
            extension=".cmap",
            mime_type="application/octet-stream",
            description="Chimera 兼容密度图",
        ),
        FormatInfo(
            format="cube",
            extension=".cube",
            mime_type="chemical/x-gaussian-cube",
            description="Gaussian Cube 格式密度图",
        ),
    ]

    return FormatsResponse(
        success=True,
        result=FormatsResult(
            input_formats=input_formats,
            output_formats=output_formats,
        ),
    )


# ==================== 单个预测 ====================


@router.post(
    "/predict/json",
    response_model=PredictResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    tags=["预测"],
)
async def predict_json(
    request: PredictRequest,
    predictor: LVPocketPredictor = Depends(get_predictor),
    file_handler: FileHandler = Depends(get_file_handler),
):
    """
    执行蛋白质结合口袋预测（纯 JSON 方式）

    通过 JSON 请求体传递参数和文件 URL。

    ## 结构分类 (structure_class)

    根据蛋白质的二级结构选择对应的预训练模型，可获得更好的预测效果：
    - **baseline**: 基线模型（默认），适用于所有蛋白质
    - **alpha**: α 类蛋白质，主要由 α 螺旋组成
    - **beta**: β 类蛋白质，主要由 β 折叠组成
    - **alpha_beta**: α/β 类蛋白质，α 螺旋和 β 折叠交替排列
    - **alpha_plus_beta**: α+β 类蛋白质，α 螺旋和 β 折叠分离排列
    """
    protein_path = None

    try:
        # JSON 请求
        task_id = request.task_id or str(uuid.uuid4())
        threshold = request.params.threshold
        min_size = request.params.min_size
        output_formats = request.params.output_formats
        structure_class = request.params.structure_class.value

        # 下载文件
        protein_path, _ = await file_handler.download_file(
            request.input_files.protein_file
        )

        # 执行预测
        result = predictor.predict(
            protein_file=protein_path,
            threshold=threshold,
            min_size=min_size,
            output_formats=output_formats,
            structure_class=structure_class,
        )

        # 构建响应
        pockets = [_pocket_data_to_info(p) for p in result.pockets]

        # 生成输出文件
        output_files = await _generate_output_files(
            task_id=task_id,
            pockets=result.pockets,
            protein_atoms=result.protein_info.atoms,
            output_formats=output_formats,
            file_handler=file_handler,
            protein_name=result.protein_info.name,
        )

        return PredictResponse(
            success=True,
            result=PredictResult(
                task_id=task_id,
                protein_name=result.protein_info.name,
                num_atoms=result.protein_info.num_atoms,
                num_pockets=len(pockets),
                processing_time=round(result.processing_time, 3),
                structure_class=result.structure_class,
                model_file=result.model_file,
                pockets=pockets,
            ),
            output_files=output_files,
        )

    except LVPocketError:
        raise
    except Exception as e:
        logger.exception(f"预测失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # 清理临时文件
        if protein_path and protein_path.exists():
            await file_handler.cleanup_file(protein_path)


@router.post(
    "/predict",
    response_model=PredictResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    tags=["预测"],
)
async def predict(
    request: Optional[PredictRequest] = None,
    protein_file: Optional[UploadFile] = File(None),
    params: Optional[str] = Form(None),
    predictor: LVPocketPredictor = Depends(get_predictor),
    file_handler: FileHandler = Depends(get_file_handler),
):
    """
    执行蛋白质结合口袋预测

    支持两种请求方式：
    1. JSON 方式：通过 URL 引用文件
    2. Multipart 方式：直接上传文件

    ## 结构分类 (structure_class)

    根据蛋白质的二级结构选择对应的预训练模型，可获得更好的预测效果：
    - **baseline**: 基线模型（默认），适用于所有蛋白质
    - **alpha**: α 类蛋白质，主要由 α 螺旋组成
    - **beta**: β 类蛋白质，主要由 β 折叠组成
    - **alpha_beta**: α/β 类蛋白质，α 螺旋和 β 折叠交替排列
    - **alpha_plus_beta**: α+β 类蛋白质，α 螺旋和 β 折叠分离排列
    """
    task_id = None
    threshold = settings.DEFAULT_THRESHOLD
    min_size = settings.DEFAULT_MIN_SIZE
    output_formats = settings.DEFAULT_OUTPUT_FORMATS.copy()
    structure_class = settings.DEFAULT_STRUCTURE_CLASS
    protein_path = None

    try:
        # 解析请求参数
        if request is not None:
            # JSON 请求
            task_id = request.task_id or str(uuid.uuid4())
            threshold = request.params.threshold
            min_size = request.params.min_size
            output_formats = request.params.output_formats
            # 获取结构分类参数
            structure_class = request.params.structure_class.value

            # 下载文件
            protein_path, _ = await file_handler.download_file(
                request.input_files.protein_file
            )

        elif protein_file is not None:
            # Multipart 请求
            task_id = str(uuid.uuid4())

            # 解析 params JSON
            if params:
                try:
                    params_dict = json.loads(params)
                    threshold = params_dict.get("threshold", threshold)
                    min_size = params_dict.get("min_size", min_size)
                    output_formats = params_dict.get("output_formats", output_formats)
                    # 获取结构分类参数
                    structure_class = params_dict.get("structure_class", structure_class)
                except json.JSONDecodeError:
                    raise ValidationError(
                        message="Invalid params JSON",
                        code=ErrorCode.INVALID_PARAM_VALUE,
                    )

            # 保存上传文件
            protein_path, _ = await file_handler.save_upload_file(protein_file)

        else:
            raise ValidationError(
                message="No protein file provided",
                code=ErrorCode.MISSING_REQUIRED_PARAM,
                details={"suggestion": "Provide protein_file via JSON body or multipart form"},
            )

        # 执行预测（传递结构分类参数）
        result = predictor.predict(
            protein_file=protein_path,
            threshold=threshold,
            min_size=min_size,
            output_formats=output_formats,
            structure_class=structure_class,
        )

        # 构建响应
        pockets = [_pocket_data_to_info(p) for p in result.pockets]

        # 生成输出文件
        output_files = await _generate_output_files(
            task_id=task_id,
            pockets=result.pockets,
            protein_atoms=result.protein_info.atoms,
            output_formats=output_formats,
            file_handler=file_handler,
            protein_name=result.protein_info.name,
        )

        return PredictResponse(
            success=True,
            result=PredictResult(
                task_id=task_id,
                protein_name=result.protein_info.name,
                num_atoms=result.protein_info.num_atoms,
                num_pockets=len(pockets),
                processing_time=round(result.processing_time, 3),
                structure_class=result.structure_class,
                model_file=result.model_file,
                pockets=pockets,
            ),
            output_files=output_files,
        )

    except LVPocketError:
        raise
    except Exception as e:
        logger.exception(f"预测失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # 清理临时文件
        if protein_path and protein_path.exists():
            await file_handler.cleanup_file(protein_path)


# ==================== 批量预测 ====================


@router.post(
    "/batch",
    response_model=BatchResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    tags=["预测"],
)
async def batch_predict(
    request: BatchRequest,
    predictor: LVPocketPredictor = Depends(get_predictor),
    file_handler: FileHandler = Depends(get_file_handler),
):
    """
    批量处理多个蛋白质文件

    ## 结构分类 (structure_class)

    批量预测时，所有蛋白质将使用相同的模型进行预测。
    根据蛋白质的二级结构选择对应的预训练模型：
    - **baseline**: 基线模型（默认），适用于所有蛋白质
    - **alpha**: α 类蛋白质
    - **beta**: β 类蛋白质
    - **alpha_beta**: α/β 类蛋白质
    - **alpha_plus_beta**: α+β 类蛋白质
    """
    task_id = request.task_id or str(uuid.uuid4())
    start_time = time.time()

    # 获取结构分类参数
    structure_class = request.params.structure_class.value

    results = []
    completed = 0
    failed = 0

    for protein_url in request.input_files.protein_files:
        protein_path = None
        try:
            # 下载文件
            protein_path, _ = await file_handler.download_file(protein_url)
            filename = protein_url.split("/")[-1].split("?")[0]

            # 执行预测（使用指定的结构分类模型）
            result = predictor.predict(
                protein_file=protein_path,
                threshold=request.params.threshold,
                min_size=request.params.min_size,
                structure_class=structure_class,
            )

            # 转换口袋信息
            pockets = [_pocket_data_to_info(p) for p in result.pockets]

            results.append(
                BatchItemResult(
                    file=filename,
                    success=True,
                    num_pockets=len(pockets),
                    pockets=pockets,
                )
            )
            completed += 1

        except Exception as e:
            filename = protein_url.split("/")[-1].split("?")[0]
            results.append(
                BatchItemResult(
                    file=filename,
                    success=False,
                    error=str(e),
                )
            )
            failed += 1
            logger.error(f"批量预测失败 {filename}: {e}")

        finally:
            if protein_path and protein_path.exists():
                await file_handler.cleanup_file(protein_path)

    processing_time = time.time() - start_time

    # 保存汇总结果
    output_files = []
    if "json" in request.params.output_formats:
        summary_path = file_handler.create_output_path(task_id, "results.json")
        summary_data = {
            "task_id": task_id,
            "structure_class": structure_class,
            "total": len(results),
            "completed": completed,
            "failed": failed,
            "results": [r.dict() for r in results],
        }
        await file_handler.write_file_content(summary_path, json.dumps(summary_data, indent=2))
        output_files.append(
            OutputFile(
                name="results.json",
                format="json",
                size=summary_path.stat().st_size,
            )
        )

    return BatchResponse(
        success=True,
        result=BatchResult(
            task_id=task_id,
            total=len(results),
            completed=completed,
            failed=failed,
            processing_time=round(processing_time, 3),
            results=results,
        ),
        output_files=output_files,
    )


# ==================== 格式转换 ====================


@router.post(
    "/convert",
    response_model=ConvertResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    tags=["转换"],
)
async def convert_format(
    request: ConvertRequest,
    file_handler: FileHandler = Depends(get_file_handler),
):
    """
    将口袋预测结果转换为不同格式
    """
    task_id = request.task_id or str(uuid.uuid4())
    start_time = time.time()

    prediction_path = None
    protein_path = None

    try:
        # 下载预测结果文件
        prediction_path, _ = await file_handler.download_file(
            request.input_files.prediction_file
        )

        # 读取预测结果
        content = await file_handler.read_file_content_async(prediction_path)
        prediction_data = json.loads(content)

        # 转换为 PocketData
        pockets = []
        for p in prediction_data:
            pocket = PocketData(
                id=p["id"],
                rank=p.get("rank", p["id"]),
                score=p["score"],
                volume=p["volume"],
                center=(p["center"]["x"], p["center"]["y"], p["center"]["z"]),
                bounding_box=(
                    (p["bounding_box"]["min"]["x"], p["bounding_box"]["min"]["y"], p["bounding_box"]["min"]["z"]),
                    (p["bounding_box"]["max"]["x"], p["bounding_box"]["max"]["y"], p["bounding_box"]["max"]["z"]),
                ) if "bounding_box" in p else None,
                residues=p.get("residues"),
            )
            pockets.append(pocket)

        # 加载蛋白质原子（如果需要）
        protein_atoms = None
        if request.params.protein_file and request.params.target_format in ["mol2"]:
            protein_path, _ = await file_handler.download_file(request.params.protein_file)
            # 使用独立函数解析蛋白质
            protein_info = parse_pdb_simple(protein_path)
            protein_atoms = protein_info.atoms

        # 执行转换
        converter = get_converter(request.params.target_format)
        converted_content = converter.convert(pockets, protein_atoms)

        # 保存输出文件
        output_filename = f"converted{converter.file_extension}"
        output_path = file_handler.create_output_path(task_id, output_filename)
        await file_handler.write_file_content(output_path, converted_content)

        conversion_time = time.time() - start_time

        return ConvertResponse(
            success=True,
            result=ConvertResult(
                task_id=task_id,
                source_format=request.params.source_format,
                target_format=request.params.target_format,
                conversion_time=round(conversion_time, 3),
            ),
            output_files=[
                OutputFile(
                    name=output_filename,
                    format=request.params.target_format,
                    size=output_path.stat().st_size,
                )
            ],
        )

    except LVPocketError:
        raise
    except json.JSONDecodeError as e:
        raise ValidationError(
            message=f"Invalid prediction JSON file: {e}",
            code=ErrorCode.FILE_PARSE_FAILED,
        )
    except Exception as e:
        logger.exception(f"格式转换失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if prediction_path and prediction_path.exists():
            await file_handler.cleanup_file(prediction_path)
        if protein_path and protein_path.exists():
            await file_handler.cleanup_file(protein_path)


# ==================== 辅助函数 ====================


async def _generate_output_files(
    task_id: str,
    pockets: List[PocketData],
    protein_atoms: List[dict],
    output_formats: List[str],
    file_handler: FileHandler,
    protein_name: str,
) -> List[OutputFile]:
    """生成输出文件"""
    output_files = []

    for fmt in output_formats:
        try:
            converter = get_converter(fmt)
            content = converter.convert(pockets, protein_atoms)

            filename = f"{protein_name}_pockets{converter.file_extension}"
            output_path = file_handler.create_output_path(task_id, filename)
            await file_handler.write_file_content(output_path, content)

            output_files.append(
                OutputFile(
                    name=filename,
                    format=fmt,
                    size=output_path.stat().st_size,
                )
            )
        except Exception as e:
            logger.warning(f"生成 {fmt} 格式输出失败: {e}")

    return output_files
