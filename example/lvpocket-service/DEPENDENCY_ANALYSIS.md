# Python 版本依赖兼容性分析

## 当前情况
- **当前镜像**: `nvcr.io/nvidia/tensorflow:21.02-tf1-py3` (Python 3.8)
- **问题**: 模型文件用 Python 3.6/3.7 保存，无法在 Python 3.8 加载
- **错误**: `bad marshal data (unknown type code)`

## Python 版本回退影响分析

### 1. 官方 TensorFlow 镜像版本对比

| 镜像 | Python 版本 | CUDA | cuDNN | 备注 |
|------|------------|------|-------|------|
| `tensorflow/tensorflow:1.15.5-gpu-py3` | **3.6** | 10.0 | 7 | 官方最新 1.15 版本 |
| `nvcr.io/nvidia/tensorflow:21.02-tf1-py3` | **3.8** | 11.2 | 8.1 | NGC 镜像（当前） |

**结论**: 官方镜像只提供 Python 3.6，没有 Python 3.7 版本。

### 2. requirements.txt 依赖 Python 版本要求

| 依赖包 | 版本 | Python 3.6 | Python 3.7 | Python 3.8 | 备注 |
|--------|------|-----------|-----------|-----------|------|
| **Web 框架** |
| fastapi | 0.95.2 | ❌ | ✅ | ✅ | **需要 Python 3.7+** |
| uvicorn | 0.22.0 | ❌ | ✅ | ✅ | **需要 Python 3.7+** |
| python-multipart | 0.0.6 | ✅ | ✅ | ✅ | |
| **数据验证** |
| pydantic | 1.10.13 | ✅ | ✅ | ✅ | Python 3.6+ |
| **异步 IO** |
| aiofiles | 23.1.0 | ❌ | ✅ | ✅ | **需要 Python 3.7+** |
| aiohttp | 3.8.4 | ❌ | ✅ | ✅ | **需要 Python 3.7+** |
| **科学计算** |
| numpy | 1.19.5 | ✅ | ✅ | ✅ | Python 3.6+ |
| scipy | 1.5.4 | ✅ | ✅ | ✅ | Python 3.6+ |
| scikit-image | 0.17.2 | ✅ | ✅ | ✅ | Python 3.6+ |
| h5py | 2.10.0 | ✅ | ✅ | ✅ | Python 3.6+ |
| pandas | 1.1.5 | ✅ | ✅ | ✅ | Python 3.6+ |
| **深度学习** |
| keras | 2.2.5 | ✅ | ✅ | ✅ | Python 3.6+ |
| **生物信息学** |
| biopython | 1.78 | ✅ | ✅ | ✅ | Python 3.6+ |
| **可视化** |
| seaborn | 0.11.2 | ✅ | ✅ | ✅ | Python 3.6+ |
| matplotlib | 3.5.3 | ❌ | ✅ | ✅ | **需要 Python 3.7+** |
| **工具库** |
| tqdm | 4.64.1 | ✅ | ✅ | ✅ | Python 3.6+ |

### 3. 兼容性总结

#### 回退到 Python 3.6 (官方 TF 1.15 镜像)
**❌ 不可行** - 以下依赖不兼容：
- fastapi 0.95.2
- uvicorn 0.22.0
- aiofiles 23.1.0
- aiohttp 3.8.4
- matplotlib 3.5.3

需要降级这些包的版本，可能导致功能缺失或新的兼容性问题。

#### 使用 Python 3.7
**✅ 理论可行** - 所有依赖均支持

**问题**:
- 官方没有 Python 3.7 的 TensorFlow 1.15 GPU 镜像
- 需要自己构建或寻找第三方镜像（不推荐）

#### 保持 Python 3.8 (当前方案)
**✅ 依赖完全兼容**

**问题**:
- 无法加载旧模型文件

## 解决方案对比

### 方案 1: 降级 Web 框架依赖 (Python 3.6)

**修改 requirements.txt**:
```txt
fastapi==0.68.2          # 最后支持 Python 3.6 的版本
uvicorn[standard]==0.15.0
aiofiles==0.8.0
aiohttp==3.7.4
matplotlib==3.3.4
```

**优点**:
- 使用官方镜像，稳定性好
- 可以直接加载现有模型

**缺点**:
- Web 框架版本较旧（2021年），可能缺少新特性
- 未来维护困难（Python 3.6 已 EOL）

### 方案 2: 使用 Python 3.7 自定义镜像

**基于 `python:3.7-slim` 手动安装 TensorFlow**:
```dockerfile
FROM python:3.7-slim
RUN pip install tensorflow-gpu==1.15.5
```

**优点**:
- 所有依赖完全兼容
- 可加载现有模型

**缺点**:
- 需要手动配置 CUDA/cuDNN（复杂）
- GPU 支持不确定
- 镜像构建复杂度高

### 方案 3: 重新保存模型 (推荐 ⭐)

**在 Python 3.8 环境下重新保存模型**:
```python
# 在 Python 3.6 环境
from keras.models import load_model
model = load_model('baseline_model.hdf')
model.save_weights('baseline_weights.h5')

# 在 Python 3.8 环境
from keras.models import load_model
model = load_model('baseline_model.hdf', compile=False)
model.save('baseline_model_py38.h5')  # 或
model.save_weights('baseline_weights_py38.h5')
```

**优点**:
- 保持现代化依赖栈
- 长期可维护
- 性能最优（CUDA 11.x）

**缺点**:
- 需要 Python 3.6/3.7 环境重新保存模型（一次性操作）
- 可能需要模型提供者协助

### 方案 4: 使用 Keras 2.3.x compile=False

**尝试禁用编译加载**:
```python
from keras.models import load_model
model = load_model(filepath, compile=False)
```

**优点**:
- 无需修改环境
- 可能绕过 pickle 问题

**缺点**:
- 已尝试但失败（权限问题）
- 不能保证成功

## 推荐方案

### 短期方案（立即可用）: 方案 1 - 降级依赖到 Python 3.6
适合快速上线，但长期不推荐。

### 长期方案（推荐）: 方案 3 - 重新保存模型
1. 在 Python 3.6 环境下加载模型并保存为权重文件
2. 在 Python 3.8 环境下重建模型并加载权重
3. 保存为 Python 3.8 兼容的模型文件

## 实施建议

如果**无法重新保存模型**，选择**方案 1**（降级依赖）
如果**可以重新保存模型**，选择**保持 Python 3.8**（方案 3）

---
生成时间: 2025-12-22
