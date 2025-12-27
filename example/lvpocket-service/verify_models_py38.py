#!/usr/bin/env python3
"""
在 Python 3.8 环境中验证所有转换后的模型
"""

import os
import sys
from pathlib import Path

# 禁用 GPU
os.environ['CUDA_VISIBLE_DEVICES'] = '-1'
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

print("=" * 80)
print("模型验证脚本 - Python 3.8 环境")
print("=" * 80)

print(f"\nPython 版本: {sys.version}")

try:
    import tensorflow as tf
    print(f"TensorFlow 版本: {tf.__version__}")

    from keras.models import load_model
    import keras
    print(f"Keras 版本: {keras.__version__}")
except ImportError as e:
    print(f"❌ 导入失败: {e}")
    sys.exit(1)

# 查找所有转换后的模型
model_dir = Path("model_converted/trained_model/newbest/new_best")
model_files = sorted(model_dir.glob("*.hdf"))

if not model_files:
    print(f"\n❌ 未找到转换后的模型文件: {model_dir}")
    sys.exit(1)

print(f"\n找到 {len(model_files)} 个模型文件\n")

# 验证每个模型
success_count = 0
failed_count = 0
results = []

for i, model_path in enumerate(model_files, 1):
    model_name = model_path.name
    print(f"[{i}/{len(model_files)}] 验证: {model_name}")

    try:
        # 尝试加载模型（不编译）
        model = load_model(str(model_path), compile=False)

        # 获取模型信息
        num_layers = len(model.layers)
        input_shape = model.input_shape
        output_shape = model.output_shape

        # 计算参数数量
        trainable_params = sum([tf.keras.backend.count_params(w) for w in model.trainable_weights])
        non_trainable_params = sum([tf.keras.backend.count_params(w) for w in model.non_trainable_weights])
        total_params = trainable_params + non_trainable_params

        print(f"  ✅ 加载成功")
        print(f"     - 层数: {num_layers}")
        print(f"     - 输入形状: {input_shape}")
        print(f"     - 输出形状: {output_shape}")
        print(f"     - 总参数: {total_params:,}")
        print(f"     - 可训练参数: {trainable_params:,}")
        print(f"     - 不可训练参数: {non_trainable_params:,}")

        success_count += 1
        results.append((model_name, "✅", num_layers, total_params))

    except Exception as e:
        print(f"  ❌ 加载失败: {e}")
        failed_count += 1
        results.append((model_name, "❌", 0, 0))

    print()

# 打印总结
print("=" * 80)
print("验证总结")
print("=" * 80)
print(f"\n总计: {len(model_files)} 个模型")
print(f"✅ 成功: {success_count}")
print(f"❌ 失败: {failed_count}")

if success_count > 0:
    print(f"\n成功率: {success_count / len(model_files) * 100:.1f}%")

# 打印详细结果表
print("\n" + "=" * 80)
print("详细结果")
print("=" * 80)
print(f"\n{'模型名称':<40} {'状态':<6} {'层数':<8} {'参数数量':<15}")
print("-" * 80)
for name, status, layers, params in results:
    params_str = f"{params:,}" if params > 0 else "-"
    layers_str = str(layers) if layers > 0 else "-"
    print(f"{name:<40} {status:<6} {layers_str:<8} {params_str:<15}")

if success_count == len(model_files):
    print("\n" + "=" * 80)
    print("🎉 所有模型验证通过！可以在 Python 3.8 环境中正常使用。")
    print("=" * 80)
    sys.exit(0)
else:
    print("\n" + "=" * 80)
    print(f"⚠️  有 {failed_count} 个模型验证失败，请检查。")
    print("=" * 80)
    sys.exit(1)
