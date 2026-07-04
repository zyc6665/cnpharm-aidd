# backend/app/tools/schema_validator.py
"""工具参数Schema验证器

根据详细设计说明书 3.3 节实现。
负责验证工具输入参数和生成前端表单配置。
"""

from typing import Any, Dict, List, Optional
import logging

try:
    from jsonschema import validate, ValidationError as JSONSchemaValidationError
    from jsonschema import Draft7Validator
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False

logger = logging.getLogger(__name__)


class SchemaValidationError(Exception):
    """Schema验证错误"""

    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        schema_path: Optional[str] = None,
        value: Any = None
    ):
        self.message = message
        self.field = field
        self.schema_path = schema_path
        self.value = value
        super().__init__(message)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message": self.message,
            "field": self.field,
            "schema_path": self.schema_path,
            "value": self.value
        }


class ToolSchemaValidator:
    """工具参数Schema验证器

    负责：
    1. 验证输入参数是否符合Schema
    2. 根据Schema生成前端表单配置
    3. 提取参数的默认值
    """

    # 支持的JSON Schema类型到前端组件的映射
    TYPE_WIDGET_MAP = {
        "string": "input",
        "number": "number",
        "integer": "number",
        "boolean": "checkbox",
        "array": "array",
        "object": "object",
    }

    # 支持的格式到前端组件的映射
    FORMAT_WIDGET_MAP = {
        "email": "email",
        "uri": "url",
        "date": "date",
        "date-time": "datetime",
        "time": "time",
        "password": "password",
        "textarea": "textarea",
        "file": "file",
    }

    @classmethod
    def validate_input_params(
        cls,
        params: Dict[str, Any],
        schema: Dict[str, Any],
        raise_exception: bool = True
    ) -> List[SchemaValidationError]:
        """验证输入参数

        Args:
            params: 输入参数字典
            schema: JSON Schema定义
            raise_exception: 是否在验证失败时抛出异常

        Returns:
            List[SchemaValidationError]: 验证错误列表

        Raises:
            SchemaValidationError: 当raise_exception=True且验证失败时
        """
        errors = []

        if not HAS_JSONSCHEMA:
            # 如果没有jsonschema库，执行基本验证
            errors = cls._basic_validation(params, schema)
        else:
            try:
                validate(instance=params, schema=schema)
            except JSONSchemaValidationError as e:
                error = SchemaValidationError(
                    message=e.message,
                    field=".".join(str(p) for p in e.path) if e.path else None,
                    schema_path=".".join(str(p) for p in e.schema_path) if e.schema_path else None,
                    value=e.instance
                )
                errors.append(error)

                # 收集所有错误
                validator = Draft7Validator(schema)
                for err in validator.iter_errors(params):
                    if err.message != e.message:  # 避免重复
                        errors.append(SchemaValidationError(
                            message=err.message,
                            field=".".join(str(p) for p in err.path) if err.path else None,
                            schema_path=".".join(str(p) for p in err.schema_path) if err.schema_path else None,
                            value=err.instance
                        ))

        if errors and raise_exception:
            raise errors[0]

        return errors

    @classmethod
    def _basic_validation(
        cls,
        params: Dict[str, Any],
        schema: Dict[str, Any]
    ) -> List[SchemaValidationError]:
        """基本验证（不使用jsonschema库）"""
        errors = []
        properties = schema.get("properties", {})
        required = schema.get("required", [])

        # 检查必填字段
        for field_name in required:
            if field_name not in params or params[field_name] is None:
                errors.append(SchemaValidationError(
                    message=f"'{field_name}' is a required property",
                    field=field_name
                ))

        # 检查类型
        for field_name, value in params.items():
            if field_name not in properties:
                continue

            field_schema = properties[field_name]
            expected_type = field_schema.get("type")

            if expected_type and not cls._check_type(value, expected_type):
                errors.append(SchemaValidationError(
                    message=f"'{field_name}' has invalid type, expected {expected_type}",
                    field=field_name,
                    value=value
                ))

        return errors

    @staticmethod
    def _check_type(value: Any, expected_type: str) -> bool:
        """检查值类型"""
        if value is None:
            return True  # None值的验证由required处理

        type_map = {
            "string": str,
            "number": (int, float),
            "integer": int,
            "boolean": bool,
            "array": list,
            "object": dict,
        }

        expected = type_map.get(expected_type)
        if expected:
            return isinstance(value, expected)
        return True

    @classmethod
    def generate_form_config(
        cls,
        schema: Dict[str, Any],
        include_advanced: bool = True
    ) -> List[Dict[str, Any]]:
        """根据Schema生成前端表单配置

        Args:
            schema: JSON Schema定义
            include_advanced: 是否包含高级配置项

        Returns:
            List[Dict[str, Any]]: 表单字段配置列表
        """
        form_fields = []
        properties = schema.get("properties", {})
        required = schema.get("required", [])

        for field_name, field_schema in properties.items():
            # 跳过隐藏字段
            if field_schema.get("hidden", False) and not include_advanced:
                continue

            field_config = cls._generate_field_config(
                field_name,
                field_schema,
                field_name in required
            )
            form_fields.append(field_config)

        # 按照order属性排序
        form_fields.sort(key=lambda x: x.get("order", 999))

        return form_fields

    @classmethod
    def _generate_field_config(
        cls,
        field_name: str,
        field_schema: Dict[str, Any],
        is_required: bool
    ) -> Dict[str, Any]:
        """生成单个字段配置"""
        field_type = field_schema.get("type", "string")
        field_format = field_schema.get("format")

        # 基础配置
        field_config = {
            "name": field_name,
            "label": field_schema.get("title", cls._to_label(field_name)),
            "description": field_schema.get("description", ""),
            "required": is_required,
            "type": field_type,
            "order": field_schema.get("order", 999),
        }

        # 确定组件类型
        widget = cls._determine_widget(field_schema)
        field_config["widget"] = widget

        # 处理字符串类型
        if field_type == "string":
            cls._handle_string_field(field_config, field_schema)

        # 处理数字类型
        elif field_type in ("number", "integer"):
            cls._handle_number_field(field_config, field_schema)

        # 处理布尔类型
        elif field_type == "boolean":
            field_config["widget"] = "switch"

        # 处理数组类型
        elif field_type == "array":
            cls._handle_array_field(field_config, field_schema)

        # 处理对象类型
        elif field_type == "object":
            cls._handle_object_field(field_config, field_schema)

        # 默认值
        if "default" in field_schema:
            field_config["default"] = field_schema["default"]

        # 示例值
        if "examples" in field_schema:
            field_config["examples"] = field_schema["examples"]

        # 占位符
        if "placeholder" in field_schema:
            field_config["placeholder"] = field_schema["placeholder"]

        # 只读
        if field_schema.get("readOnly"):
            field_config["readOnly"] = True

        # 禁用
        if field_schema.get("disabled"):
            field_config["disabled"] = True

        # 提示
        if "hint" in field_schema:
            field_config["hint"] = field_schema["hint"]

        return field_config

    @classmethod
    def _determine_widget(cls, field_schema: Dict[str, Any]) -> str:
        """确定组件类型"""
        # 优先使用显式指定的widget
        if "widget" in field_schema:
            return field_schema["widget"]

        field_type = field_schema.get("type", "string")
        field_format = field_schema.get("format")

        # 根据format确定
        if field_format and field_format in cls.FORMAT_WIDGET_MAP:
            return cls.FORMAT_WIDGET_MAP[field_format]

        # 枚举类型
        if "enum" in field_schema:
            enum_count = len(field_schema["enum"])
            if enum_count <= 3:
                return "radio"
            return "select"

        # 根据type确定
        return cls.TYPE_WIDGET_MAP.get(field_type, "input")

    @classmethod
    def _handle_string_field(
        cls,
        field_config: Dict[str, Any],
        field_schema: Dict[str, Any]
    ) -> None:
        """处理字符串类型字段"""
        # 枚举选项
        if "enum" in field_schema:
            field_config["options"] = [
                {"label": opt, "value": opt}
                for opt in field_schema["enum"]
            ]

        # 长度限制
        if "minLength" in field_schema:
            field_config["minLength"] = field_schema["minLength"]
        if "maxLength" in field_schema:
            field_config["maxLength"] = field_schema["maxLength"]

        # 正则模式
        if "pattern" in field_schema:
            field_config["pattern"] = field_schema["pattern"]

        # 多行文本
        if field_schema.get("format") == "textarea" or field_schema.get("maxLength", 0) > 200:
            field_config["widget"] = "textarea"
            field_config["rows"] = field_schema.get("rows", 4)

    @classmethod
    def _handle_number_field(
        cls,
        field_config: Dict[str, Any],
        field_schema: Dict[str, Any]
    ) -> None:
        """处理数字类型字段"""
        if "minimum" in field_schema:
            field_config["min"] = field_schema["minimum"]
        if "maximum" in field_schema:
            field_config["max"] = field_schema["maximum"]
        if "multipleOf" in field_schema:
            field_config["step"] = field_schema["multipleOf"]
        else:
            field_config["step"] = 1 if field_schema.get("type") == "integer" else 0.1

        # 滑块组件
        if "slider" in field_schema.get("widget", ""):
            field_config["widget"] = "slider"

    @classmethod
    def _handle_array_field(
        cls,
        field_config: Dict[str, Any],
        field_schema: Dict[str, Any]
    ) -> None:
        """处理数组类型字段"""
        items = field_schema.get("items", {})
        field_config["items"] = items

        if "minItems" in field_schema:
            field_config["minItems"] = field_schema["minItems"]
        if "maxItems" in field_schema:
            field_config["maxItems"] = field_schema["maxItems"]

        # 标签选择器
        if items.get("type") == "string" and "enum" in items:
            field_config["widget"] = "tags"
            field_config["options"] = items["enum"]

    @classmethod
    def _handle_object_field(
        cls,
        field_config: Dict[str, Any],
        field_schema: Dict[str, Any]
    ) -> None:
        """处理对象类型字段"""
        properties = field_schema.get("properties", {})
        required = field_schema.get("required", [])

        # 递归生成子字段配置
        sub_fields = []
        for sub_name, sub_schema in properties.items():
            sub_config = cls._generate_field_config(
                sub_name, sub_schema, sub_name in required
            )
            sub_fields.append(sub_config)

        field_config["properties"] = sub_fields

    @staticmethod
    def _to_label(field_name: str) -> str:
        """将字段名转换为标签"""
        # snake_case -> Title Case
        return field_name.replace("_", " ").replace("-", " ").title()

    @classmethod
    def extract_defaults(cls, schema: Dict[str, Any]) -> Dict[str, Any]:
        """从Schema中提取默认值

        Args:
            schema: JSON Schema定义

        Returns:
            Dict[str, Any]: 默认值字典
        """
        defaults = {}
        properties = schema.get("properties", {})

        for field_name, field_schema in properties.items():
            if "default" in field_schema:
                defaults[field_name] = field_schema["default"]
            elif field_schema.get("type") == "object":
                # 递归提取嵌套对象的默认值
                nested_defaults = cls.extract_defaults(field_schema)
                if nested_defaults:
                    defaults[field_name] = nested_defaults

        return defaults

    @classmethod
    def merge_with_defaults(
        cls,
        params: Dict[str, Any],
        schema: Dict[str, Any]
    ) -> Dict[str, Any]:
        """将参数与默认值合并

        Args:
            params: 用户输入参数
            schema: JSON Schema定义

        Returns:
            Dict[str, Any]: 合并后的参数
        """
        defaults = cls.extract_defaults(schema)

        # 深度合并
        result = defaults.copy()
        for key, value in params.items():
            if isinstance(value, dict) and isinstance(result.get(key), dict):
                result[key] = {**result[key], **value}
            else:
                result[key] = value

        return result
