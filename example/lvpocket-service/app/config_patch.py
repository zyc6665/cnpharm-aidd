"""
配置修补脚本 - 适配实际的模型文件名

解决问题：
- config.py 中定义的 MODEL_FILES 与实际文件名不匹配
- 实际文件使用 .hdf 扩展名，而配置期望 .h5
- 实际文件在 newbest/new_best/ 子目录中

使用方式：
在 config.py 中导入此模块即可自动适配
"""

# 实际的模型文件映射（相对于 MODEL_DIR）
ACTUAL_MODEL_FILES = {
    # 基线模型
    "baseline": "baseline_model.hdf",
    # α 类蛋白质模型
    "alpha": "α_finetuned_model.hdf",
    # β 类蛋白质模型
    "beta": "β_finetuned_model.hdf",
    # α/β 类蛋白质模型（交替排列）
    "alpha_beta": "α_and_β_finetuned_model.hdf",
    # α+β 类蛋白质模型（分离排列）
    "alpha_plus_beta": "α_or_β_finetuned_model.hdf",
}


def patch_model_files(settings):
    """
    修补 settings.MODEL_FILES

    Args:
        settings: Settings 实例
    """
    settings.MODEL_FILES = ACTUAL_MODEL_FILES.copy()
    return settings
