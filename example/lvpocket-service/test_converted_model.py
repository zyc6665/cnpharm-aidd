#!/usr/bin/env python3
"""
测试转换后的模型是否可以在 Python 3.8 中加载
"""

import os
import sys

# 禁用 GPU
os.environ['CUDA_VISIBLE_DEVICES'] = '-1'
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

print("Python 版本:", sys.version)

try:
    import tensorflow as tf
    print(f"TensorFlow 版本: {tf.__version__}")

    from keras.models import load_model
    print(f"Keras 版本: {tf.keras.__version__}")

    # 测试加载转换后的模型
    model_path = "model_converted/trained_model/newbest/new_best/artifacts.hdf"

    print(f"\n正在加载模型: {model_path}")
    model = load_model(model_path, compile=False)

    print(f"✅ 模型加载成功！")
    print(f"   - 层数: {len(model.layers)}")
    print(f"   - 输入形状: {model.input_shape}")
    print(f"   - 输出形状: {model.output_shape}")

    print("\n✅ 转换成功！模型可以在 Python 3.8 环境中正常加载。")

except Exception as e:
    print(f"\n❌ 模型加载失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
