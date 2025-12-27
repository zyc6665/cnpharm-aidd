#!/usr/bin/env python3
"""
模型转换脚本 - Python 3.6 to Python 3.8 兼容
将 Python 3.6 保存的 Keras 模型转换为 Python 3.8 兼容格式
"""

import os
import sys
import glob
from pathlib import Path

def convert_model(model_path, output_path):
    """
    转换单个模型文件

    Args:
        model_path: 原始模型文件路径
        output_path: 输出模型文件路径
    """
    print(f"\n{'='*80}")
    print(f"转换模型: {model_path}")
    print(f"输出路径: {output_path}")
    print(f"{'='*80}")

    try:
        # 禁用 GPU（转换只需要 CPU）
        os.environ['CUDA_VISIBLE_DEVICES'] = '-1'
        # 设置 TensorFlow 日志级别
        os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

        # 导入 TensorFlow 和 Keras（必须在最开始）
        import tensorflow as tf
        tf.compat.v1.logging.set_verbosity(tf.compat.v1.logging.ERROR)

        from keras.models import load_model
        import keras.backend as K
        import math
        import numpy as np

        # 确保 tf, K, math, np 在全局作用域中
        globals()['tf'] = tf
        globals()['K'] = K
        globals()['math'] = math
        globals()['np'] = np

        # 导入 LVpocket 自定义层和函数
        print("📦 加载自定义层...")
        script_dir = Path(__file__).parent
        lvpocket_model_dir = script_dir / "model" / "LVpocket" / "model"
        sys.path.insert(0, str(lvpocket_model_dir.parent))

        try:
            # 先注入所有必要的模块到 builtins，确保所有模块都能访问
            import builtins
            builtins.tf = tf
            builtins.K = K
            builtins.math = math
            builtins.np = np
            builtins.numpy = np

            # 导入 LV_former 中的所有自定义类和函数
            import model.LV_former as lv_former
            import inspect

            # 获取所有导出的对象
            custom_objects = {}
            for name in lv_former.__all__:
                custom_objects[name] = getattr(lv_former, name)

            # 自动添加所有 Layer 子类（LayerNorm, PositionEncoding, EncoderLayer 等）
            for name, obj in inspect.getmembers(lv_former, inspect.isclass):
                # 检查是否是 Layer 的子类
                if hasattr(obj, '__bases__'):
                    from keras.layers import Layer
                    if Layer in obj.__mro__ and obj != Layer:
                        custom_objects[name] = obj

            print(f"✅ 自定义层加载成功 ({len(custom_objects)} 个对象)")
        except Exception as e:
            print(f"⚠️  自定义层加载失败: {e}")
            import traceback
            traceback.print_exc()
            custom_objects = {}

        print("📥 加载模型...")
        # 使用 compile=False 避免优化器状态导致的兼容性问题
        model = load_model(model_path, custom_objects=custom_objects, compile=False)

        print(f"✅ 模型加载成功")
        print(f"   - 层数: {len(model.layers)}")

        # 获取模型摘要
        try:
            model.summary()
        except Exception as e:
            print(f"   ⚠️  无法显示模型摘要: {e}")

        print("\n💾 重新保存模型...")
        # 重新保存模型（使用当前 Python 版本的 pickle 协议）
        # Keras 2.2.x 不支持 save_format 参数
        model.save(output_path, include_optimizer=False)

        print(f"✅ 模型转换成功！")

        # 验证保存的模型
        print("\n🔍 验证保存的模型...")
        test_model = load_model(output_path, compile=False)
        print(f"✅ 验证成功 - 层数: {len(test_model.layers)}")

        return True

    except Exception as e:
        print(f"❌ 转换失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def find_model_files(model_dir):
    """
    查找所有模型文件

    Args:
        model_dir: 模型目录

    Returns:
        模型文件路径列表
    """
    patterns = ['**/*.hdf', '**/*.hdf5', '**/*.h5']
    model_files = []

    for pattern in patterns:
        model_files.extend(glob.glob(os.path.join(model_dir, pattern), recursive=True))

    # 去重
    model_files = list(set(model_files))

    # 排除测试数据文件
    model_files = [f for f in model_files if 'test_data' not in f]

    return sorted(model_files)


def main():
    """主函数"""
    print("""
╔════════════════════════════════════════════════════════════════════════════╗
║                      LVPocket 模型转换工具                                 ║
║                   Python 3.6 → Python 3.8 兼容                             ║
╚════════════════════════════════════════════════════════════════════════════╝
    """)

    # 检查 Python 版本
    py_version = sys.version_info
    print(f"🐍 Python 版本: {py_version.major}.{py_version.minor}.{py_version.micro}")

    if py_version.major != 3 or py_version.minor != 6:
        print("⚠️  警告: 建议使用 Python 3.6 环境运行此脚本")

    # 检查依赖
    try:
        import tensorflow as tf
        import keras
        import h5py
        print(f"✅ TensorFlow: {tf.__version__}")
        print(f"✅ Keras: {keras.__version__}")
        print(f"✅ h5py: {h5py.__version__}")
    except ImportError as e:
        print(f"❌ 缺少依赖: {e}")
        sys.exit(1)

    # 模型目录
    script_dir = Path(__file__).parent
    model_dir = script_dir / "model" / "LVpocket"

    if not model_dir.exists():
        print(f"❌ 模型目录不存在: {model_dir}")
        sys.exit(1)

    print(f"\n📁 模型目录: {model_dir}")

    # 查找所有模型文件
    print("\n🔍 查找模型文件...")
    model_files = find_model_files(str(model_dir))

    if not model_files:
        print("❌ 未找到任何模型文件")
        sys.exit(1)

    print(f"✅ 找到 {len(model_files)} 个模型文件:\n")
    for i, f in enumerate(model_files, 1):
        rel_path = os.path.relpath(f, model_dir)
        print(f"   {i:2d}. {rel_path}")

    # 确认转换
    print(f"\n{'='*80}")
    response = input("是否开始转换？(y/N): ").strip().lower()
    if response not in ['y', 'yes']:
        print("❌ 取消转换")
        sys.exit(0)

    # 创建输出目录
    output_dir = script_dir / "model_converted"
    output_dir.mkdir(exist_ok=True)
    print(f"\n📁 输出目录: {output_dir}")

    # 转换所有模型
    success_count = 0
    failed_count = 0

    for i, model_file in enumerate(model_files, 1):
        print(f"\n\n[{i}/{len(model_files)}] ", end='')

        # 构建输出路径（保持相对目录结构）
        rel_path = os.path.relpath(model_file, model_dir)
        output_path = output_dir / rel_path

        # 创建输出子目录
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # 转换模型
        if convert_model(model_file, str(output_path)):
            success_count += 1
        else:
            failed_count += 1

    # 转换总结
    print(f"\n\n{'='*80}")
    print("转换完成！")
    print(f"{'='*80}")
    print(f"✅ 成功: {success_count}")
    print(f"❌ 失败: {failed_count}")
    print(f"📁 输出目录: {output_dir}")

    if success_count > 0:
        print(f"\n💡 下一步:")
        print(f"   1. 验证转换后的模型在 Python 3.8 环境中可以加载")
        print(f"   2. 将转换后的模型文件替换到 lvpocket-service/model/LVpocket/")
        print(f"   3. 重新构建 Docker 镜像")


if __name__ == "__main__":
    main()
