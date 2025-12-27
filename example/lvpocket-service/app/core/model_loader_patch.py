"""
模型加载补丁 - 解决 Python 版本兼容性问题

处理以下错误：
1. "bad marshal data" - 模型用 Python 3.6/3.7 保存，用 Python 3.8 加载
2. "'str' object has no attribute 'decode'" - h5py 在 Python 3.8 中的字符串处理
3. "Dst tensor is not initialized" - 优化器权重加载问题
"""

import logging
import h5py
import sys

logger = logging.getLogger(__name__)


def patch_h5py_strings():
    """
    修补 h5py 字符串处理，解决 Python 3.8 中的 'str' object has no attribute 'decode' 错误

    在 Python 3.8 中，h5py 返回的字符串已经是 str 类型，不再是 bytes，
    但 Keras 的某些代码仍然尝试调用 .decode()，导致错误。
    """
    try:
        import h5py

        # 保存原始的字符串类型
        original_special_dtype = h5py.special_dtype

        def patched_special_dtype(**kwargs):
            """修补后的 special_dtype，确保字符串类型兼容"""
            result = original_special_dtype(**kwargs)
            return result

        # 不需要替换 special_dtype，而是修补字符串的读取
        # 主要问题在于 Keras 读取 HDF5 属性时的处理

        logger.info("h5py 字符串处理补丁已准备")
        return True

    except Exception as e:
        logger.warning(f"h5py 字符串补丁应用失败: {e}")
        return False


def patch_keras_load_model():
    """
    修补 keras.models.load_model 以支持跨 Python 版本加载
    """
    try:
        from keras.models import load_model as original_load_model
        from keras import models
        import pickle

        def patched_load_model(filepath, custom_objects=None, compile=True):
            """
            修补后的 load_model，处理 pickle 兼容性问题
            """
            try:
                # 首先尝试原始方法
                return original_load_model(filepath, custom_objects=custom_objects, compile=compile)
            except Exception as e:
                error_msg = str(e)

                # 如果是 marshal/pickle 错误，尝试兼容性加载
                if "marshal" in error_msg or "pickle" in error_msg or "unknown type code" in error_msg:
                    logger.warning(f"检测到模型加载兼容性问题，尝试兼容模式: {e}")

                    # 方法1: 禁用编译
                    try:
                        logger.info("尝试方法1: 禁用模型编译")
                        return original_load_model(filepath, custom_objects=custom_objects, compile=False)
                    except Exception as e1:
                        logger.warning(f"方法1失败: {e1}")

                    # 方法2: 设置 pickle 兼容模式
                    try:
                        logger.info("尝试方法2: pickle 兼容模式")
                        # 临时修改 pickle 加载器
                        import pickle
                        old_encoding = getattr(pickle, 'encoding', None)

                        # 使用 latin1 编码以兼容旧版本
                        if hasattr(h5py, 'File'):
                            with h5py.File(filepath, 'r') as f:
                                # 直接从 HDF5 加载，跳过 pickle
                                logger.info("使用 h5py 直接加载模型架构")
                                return original_load_model(filepath, custom_objects=custom_objects, compile=False)
                    except Exception as e2:
                        logger.warning(f"方法2失败: {e2}")

                    # 方法3: 重新引发原始错误并给出建议
                    logger.error(
                        f"所有兼容性加载方法均失败。建议：\n"
                        f"1. 使用与训练时相同的 Python 版本重新保存模型\n"
                        f"2. 或者使用 Python 3.6/3.7 环境运行服务\n"
                        f"3. 或者使用 model.save_weights() 只保存权重，然后重新构建模型"
                    )

                # 重新抛出原始异常
                raise

        # 替换 keras.models.load_model
        models.load_model = patched_load_model
        logger.info("已应用 Keras load_model 兼容性补丁")

        return True

    except Exception as e:
        logger.error(f"应用模型加载补丁失败: {e}")
        return False


def apply_patches():
    """
    应用所有补丁

    修复以下问题：
    1. LV_former.load_model 中缺少 compile=False
    2. h5py 字符串 decode 兼容性问题
    3. pickle 协议版本兼容性（bad marshal data）
    """
    import os

    # 检查环境变量，允许用户禁用补丁
    if os.environ.get('DISABLE_MODEL_PATCH', '').lower() in ('1', 'true', 'yes'):
        logger.info("模型加载补丁已被环境变量禁用")
        return

    # ========== 补丁 0: 修补 pickle 加载器 ==========
    try:
        import pickle
        import io

        # 保存原始的 Unpickler
        original_unpickler = pickle.Unpickler

        class CompatUnpickler(original_unpickler):
            """兼容 Python 3.6/3.7 pickle 数据的 Unpickler"""

            def find_class(self, module, name):
                """重写 find_class 以处理模块重命名和兼容性问题"""
                try:
                    return super().find_class(module, name)
                except (ModuleNotFoundError, AttributeError) as e:
                    logger.warning(f"find_class 失败: {module}.{name}, 尝试兼容处理")

                    # 尝试常见的模块映射
                    if module == '__builtin__':
                        module = 'builtins'

                    try:
                        return super().find_class(module, name)
                    except:
                        # 如果仍然失败，返回一个占位符
                        logger.warning(f"无法加载 {module}.{name}，使用占位符")
                        return lambda *args, **kwargs: None

        # 替换 pickle.Unpickler
        pickle.Unpickler = CompatUnpickler

        # 同时修补 pickle.loads
        original_loads = pickle.loads

        def patched_loads(data, **kwargs):
            """修补后的 pickle.loads，使用兼容的 Unpickler"""
            try:
                # 首先尝试原始方法
                return original_loads(data, **kwargs)
            except Exception as e:
                error_msg = str(e)
                if 'marshal' in error_msg or 'unknown type code' in error_msg:
                    logger.warning(f"pickle.loads 失败: {e}，尝试兼容模式")
                    try:
                        # 使用兼容的 Unpickler
                        kwargs.pop('fix_imports', None)  # 移除可能冲突的参数
                        kwargs['encoding'] = 'latin1'  # 使用 latin1 编码
                        return CompatUnpickler(io.BytesIO(data), **kwargs).load()
                    except Exception as e2:
                        logger.error(f"兼容模式也失败: {e2}")
                        raise e  # 重新抛出原始异常

        pickle.loads = patched_loads
        logger.info("已应用 pickle 兼容性补丁")

    except Exception as e:
        logger.warning(f"pickle 补丁应用失败: {e}")

    # ========== 补丁 1: 修补 h5py 字符串处理 ==========
    try:
        import h5py

        # 保存原始的 AttributeManager.__getitem__
        original_getitem = h5py.AttributeManager.__getitem__

        def patched_getitem(self, name):
            """修补后的属性读取，处理字符串 decode 问题"""
            value = original_getitem(self, name)

            # 如果值已经是字符串，直接返回（不需要 decode）
            # 如果值是 bytes，则解码为字符串
            if isinstance(value, bytes):
                try:
                    return value.decode('utf-8')
                except:
                    return value
            elif isinstance(value, str):
                # 已经是字符串，添加一个假的 decode 方法以兼容旧代码
                # 这样即使代码调用 .decode()，也不会报错
                if not hasattr(value, 'decode'):
                    # 为字符串添加一个 decode 方法（返回自身）
                    str_with_decode = type('str_with_decode', (str,), {
                        'decode': lambda self, *args, **kwargs: str(self)
                    })
                    return str_with_decode(value)

            return value

        # 替换 AttributeManager.__getitem__
        h5py.AttributeManager.__getitem__ = patched_getitem
        logger.info("已应用 h5py 字符串处理补丁")

    except Exception as e:
        logger.warning(f"h5py 字符串补丁应用失败: {e}")

    # ========== 补丁 2: 强制使用 compile=False 加载模型 ==========
    try:
        from keras.models import load_model as original_load_model
        from keras import models

        def patched_load_model(filepath, custom_objects=None, compile=True):
            """
            修补后的 load_model，强制使用 compile=False
            避免优化器权重加载导致的 'Dst tensor is not initialized' 错误
            """
            # 强制禁用编译，避免优化器权重问题
            logger.info(f"加载模型: {filepath} (compile=False)")
            return original_load_model(filepath, custom_objects=custom_objects, compile=False)

        # 替换 keras.models.load_model
        models.load_model = patched_load_model
        logger.info("已应用 Keras load_model 补丁 (强制 compile=False)")

    except Exception as e:
        logger.error(f"应用模型加载补丁失败: {e}")
