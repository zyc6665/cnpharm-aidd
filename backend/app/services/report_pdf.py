"""结果分析报告 PDF 渲染（docs/12 TC-M7-04 / TC-M7-08）。

为什么单独一个模块
------------------
`app/services/traceability.py` 负责回答「这份结果由什么产生」（结构化 JSON，
机器可读），本模块负责回答「给人看的报告长什么样」（PDF，含图表/结论/版本
信息）。两者共享同一份数据源——调用方把 :func:`build_traceability_package`
的产物整个传进来，本模块**不再查库**：报告里出现的每个字段都能在追溯包里
找到对应项，否则审计时无法把纸面报告与记录对上。

中文字体
--------
离线交付不允许下载字体，仓库里也没有 CJK TTF，所以使用 reportlab 自带的
CID 字体 ``STSong-Light``（``UnicodeCIDFont``）。CID 字体不带 ToUnicode 表，
``pypdf`` 仍能正确解出中文（实测见 ``test/test_result_report_pdf.py``），
但这依赖阅读器/库的 CMap 实现，属于已知取舍：体积与离线可用性优先。

超长内容
--------
参数 JSON 不截断行、不丢字段：按行 + 按像素宽度重排（:func:`_wrap_to_width`），
只有在字符数超过 :data:`MAX_PARAM_CHARS` 时才截断，并在报告里显式写出
「已截断，完整内容见追溯包」——报告不能假装完整。
"""

from __future__ import annotations

import io
import json
from datetime import datetime
from typing import Any, Iterable, Iterator, Mapping, Sequence
from xml.sax.saxutils import escape

from reportlab.graphics.charts.barcharts import HorizontalBarChart
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas as pdf_canvas
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
    XPreformatted,
)

#: 报告模板版本。TC-M7-04 要求报告元数据含「模板版本」，改动版式时递增；
#: 同时写进 PDF 页脚与响应头，纸面文件才能自证是哪一代模板渲染的。
REPORT_TEMPLATE_VERSION = "report.v1"

#: reportlab 自带的中日韩 CID 字体，无需外部字体文件（离线交付约束）。
CJK_FONT_NAME = "STSong-Light"
LATIN_FONT_NAME = "Helvetica"

#: 参数 JSON 的字符上限。超过后截断并在正文写明，避免 300 页的报告。
MAX_PARAM_CHARS = 20000

_PAGE_MARGIN = 15 * mm
_CONTENT_WIDTH = A4[0] - 2 * _PAGE_MARGIN

_font_ready = False


def _ensure_cjk_font() -> None:
    """注册 CJK 字体（幂等：reportlab 允许覆盖同名注册）。"""
    global _font_ready
    if not _font_ready:
        pdfmetrics.registerFont(UnicodeCIDFont(CJK_FONT_NAME))
        _font_ready = True


def _style(name: str, **kwargs: Any) -> ParagraphStyle:
    base = {"fontName": CJK_FONT_NAME, "wordWrap": "CJK", "fontSize": 9, "leading": 13}
    base.update(kwargs)
    return ParagraphStyle(name, **base)


def _text(value: Any, default: str = "-") -> str:
    """空值统一渲染成 ``-``，不要出现 ``None`` / ``null``。"""
    if value is None:
        return default
    if isinstance(value, str):
        stripped = value.strip()
        return stripped if stripped else default
    if isinstance(value, bool):
        return "是" if value else "否"
    return str(value)


def _text_scalar(value: Any, default: str = "-") -> str:
    """``_text`` 的 JSON 友好版：dict/list 走 JSON 而不是 Python repr。"""
    if isinstance(value, (Mapping, list, tuple)):
        return json.dumps(value, ensure_ascii=False, default=str)
    return _text(value, default)


def _paragraph(value: Any, style: ParagraphStyle, default: str = "-") -> Paragraph:
    return Paragraph(escape(_text_scalar(value, default)), style)


def _wrap_to_width(text: str, *, max_width: float, font: str, size: float) -> list[str]:
    """按渲染宽度折行，保留原有换行。

    逐字符累加 ``stringWidth`` 而不是按固定字符数切：中文是全角、SHA256 是
    半角，用同一个字符阈值会让某一行溢出页面或被过早折断。
    """
    lines: list[str] = []
    for raw_line in text.split("\n"):
        if not raw_line:
            lines.append("")
            continue
        current = ""
        width = 0.0
        for char in raw_line:
            char_width = pdfmetrics.stringWidth(char, font, size)
            if current and width + char_width > max_width:
                lines.append(current)
                current, width = char, char_width
            else:
                current += char
                width += char_width
        lines.append(current)
    return lines


def _json_block(data: Any, *, limit: int = MAX_PARAM_CHARS) -> tuple[str, bool]:
    """把任意 JSON 值渲染成缩进文本，返回 ``(文本, 是否截断)``。"""
    if data is None or data == {} or data == []:
        return "-", False
    try:
        text = json.dumps(data, ensure_ascii=False, indent=2, default=str)
    except (TypeError, ValueError):
        text = str(data)
    if len(text) <= limit:
        return text, False
    head = text[:limit]
    cut = head.rsplit("\n", 1)[0] if "\n" in head else head
    return f"{cut}\n…", True


# ---------------------------------------------------------------------------
# 结论提取
# ---------------------------------------------------------------------------

#: 工具/产物把结构化指标放在这些键下（历史实现不统一，全部认）。
_METRIC_CONTAINER_KEYS = (
    "metrics",
    "key_metrics",
    "keyMetrics",
    "summary",
    "conclusion",
    "conclusions",
    "results",
)

#: 一条结论最多多长，避免把整个 PDB 头部塞进表格。
_MAX_CONCLUSION_ROWS = 40
_MAX_CONCLUSION_VALUE_CHARS = 240


def _flatten_scalars(value: Any, *, prefix: str = "") -> Iterator[tuple[str, Any]]:
    """摊平成 ``点分路径 -> 标量``；容器只下探、不保留整块。"""
    if isinstance(value, Mapping):
        for key in value:
            path = f"{prefix}.{key}" if prefix else str(key)
            yield from _flatten_scalars(value[key], prefix=path)
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            yield from _flatten_scalars(item, prefix=f"{prefix}[{index}]")
        return
    yield prefix, value


def _scalar_text(value: Any) -> str:
    if isinstance(value, (str, int, float, bool)) or value is None:
        text = _text(value)
    else:
        text = json.dumps(value, ensure_ascii=False, default=str)
    if len(text) > _MAX_CONCLUSION_VALUE_CHARS:
        text = text[: _MAX_CONCLUSION_VALUE_CHARS - 1] + "…"
    return text


def extract_conclusions(
    output_result: Any,
    *,
    artifact_summaries: Iterable[tuple[str, Mapping[str, Any]]] = (),
) -> list[dict[str, str]]:
    """从任务输出与产物摘要里提取关键指标，**不编造任何数值**。

    取数顺序：``TaskOutput.result`` 里已知的指标容器 → 各产物版本的
    ``metrics`` / ``summary``。都没有则返回空列表，由渲染层写
    「本任务未产出结构化指标」。
    """
    rows: list[dict[str, str]] = []
    seen: set[str] = set()

    def _collect(source: str, container: Any) -> None:
        if not isinstance(container, Mapping):
            return
        for path, value in _flatten_scalars(container):
            if not path:
                continue
            if path in seen or len(rows) >= _MAX_CONCLUSION_ROWS:
                continue
            seen.add(path)
            rows.append({"source": source, "path": path, "value": _scalar_text(value)})

    if isinstance(output_result, Mapping):
        containers = [key for key in _METRIC_CONTAINER_KEYS if key in output_result]
        if containers:
            for key in containers:
                _collect("output", output_result[key])
        else:
            # 没有显式指标容器时，退回「整块都是标量」的扁平输出；但只认数值/布尔
            # ——自由文本通常是 PDB 头部这类 payload，放进结论表只会挤掉真指标。
            numbers = [
                (key, value)
                for key, value in output_result.items()
                if isinstance(value, (int, float, bool)) and not isinstance(value, str)
            ]
            if numbers and len(numbers) == len(output_result) and len(numbers) <= 20:
                _collect("output", dict(numbers))

    for name, container in artifact_summaries:
        _collect(_text(name, "artifact"), container)

    return rows


# ---------------------------------------------------------------------------
# 图表
# ---------------------------------------------------------------------------


def _bar_chart(
    *,
    categories: Sequence[str],
    values: Sequence[float],
    unit_suffix: str = "",
    width: float = _CONTENT_WIDTH,
    height: float = 96,
) -> Drawing:
    """横向条形图：STSong-Light 标签 + 数值标注。

    TC-M7-08 要求「PDF 报告含图表」，用时间线/产物体量这类**真实取数**作图，
    而不是装饰性占位图——图上的每个数字都能在表格里复核。
    """
    drawing = Drawing(width, height)
    chart = HorizontalBarChart()
    chart.x = 96
    chart.y = 16
    chart.width = width - 130
    chart.height = height - 26
    chart.data = [list(values)]
    chart.categoryAxis.categoryNames = list(categories)
    chart.categoryAxis.labels.fontName = CJK_FONT_NAME
    chart.categoryAxis.labels.fontSize = 8
    chart.valueAxis.labels.fontName = LATIN_FONT_NAME
    chart.valueAxis.labels.fontSize = 7
    chart.valueAxis.valueMin = 0
    chart.bars[0].fillColor = colors.HexColor("#2f6fdb")
    chart.barLabels.fontName = LATIN_FONT_NAME
    chart.barLabels.fontSize = 7
    chart.barLabels.nudge = 6
    chart.barLabelFormat = f"%0.1f{unit_suffix}"
    drawing.add(chart)
    return drawing


def _chart_caption(text: str) -> Paragraph:
    """图表标题用 Paragraph 承载，避开 Drawing 内嵌文本的字体陷阱。"""
    return Paragraph(
        escape(text),
        _style("caption", fontSize=8, leading=10, textColor=colors.HexColor("#4b5563"), spaceBefore=4),
    )


# ---------------------------------------------------------------------------
# 页面框架
# ---------------------------------------------------------------------------


class _NumberedCanvas(pdf_canvas.Canvas):
    """两遍绘制：先记页，收尾时补「第 N / M 页」与模板版本页脚。"""

    def __init__(self, *args: Any, footer_note: str = "", **kwargs: Any) -> None:
        self._footer_note = footer_note
        self._page_states: list[dict[str, Any]] = []
        pdf_canvas.Canvas.__init__(self, *args, **kwargs)

    def showPage(self) -> None:  # noqa: N802 - reportlab 的驼峰约定
        self._page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        total = len(self._page_states)
        footer_note = self._footer_note
        for state in self._page_states:
            self.__dict__.update(state)
            self._draw_footer(footer_note, total)
            pdf_canvas.Canvas.showPage(self)
        pdf_canvas.Canvas.save(self)

    def _draw_footer(self, footer_note: str, total: int) -> None:
        self.saveState()
        self.setStrokeColor(colors.HexColor("#c9ced6"))
        self.setLineWidth(0.4)
        self.line(_PAGE_MARGIN, _PAGE_MARGIN + 8, A4[0] - _PAGE_MARGIN, _PAGE_MARGIN + 8)
        self.setFont(CJK_FONT_NAME, 7)
        self.setFillColor(colors.HexColor("#6b7280"))
        self.drawString(_PAGE_MARGIN, _PAGE_MARGIN, f"{REPORT_TEMPLATE_VERSION} · {footer_note}")
        page_label = f"第 {self._pageNumber} 页 / 共 {total} 页"
        self.drawRightString(A4[0] - _PAGE_MARGIN, _PAGE_MARGIN, page_label)
        self.restoreState()


def _header(canvas_obj: pdf_canvas.Canvas, doc: Any) -> None:
    canvas_obj.saveState()
    canvas_obj.setFont(CJK_FONT_NAME, 7)
    canvas_obj.setFillColor(colors.HexColor("#6b7280"))
    canvas_obj.drawString(_PAGE_MARGIN, A4[1] - _PAGE_MARGIN + 4, "中国医药 AIDD 平台 · 结果分析报告")
    canvas_obj.restoreState()


# ---------------------------------------------------------------------------
# 版块
# ---------------------------------------------------------------------------


def _section_title(text: str) -> Paragraph:
    return Paragraph(
        escape(text),
        _style(
            "section",
            fontSize=11,
            leading=15,
            spaceBefore=10,
            spaceAfter=5,
            textColor=colors.HexColor("#1f2a44"),
        ),
    )


def _kv_table(rows: Sequence[tuple[str, Any]], *, value_style: ParagraphStyle) -> Table:
    data = [
        [
            Paragraph(escape(label), _style("kv-label", fontSize=8.5, leading=12, textColor=colors.HexColor("#4b5563"))),
            _paragraph(value, value_style),
        ]
        for label, value in rows
    ]
    table = Table(data, colWidths=[34 * mm, _CONTENT_WIDTH - 34 * mm], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, -2), 0.25, colors.HexColor("#e5e7eb")),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return table


def _matrix_table(
    headers: Sequence[str],
    rows: Sequence[Sequence[Any]],
    *,
    col_widths: Sequence[float],
    body_style: ParagraphStyle,
) -> Table:
    data = [[Paragraph(escape(header), _style("th", fontSize=8, leading=10, textColor=colors.white)) for header in headers]]
    for row in rows:
        data.append([_paragraph(cell, body_style) for cell in row])
    table = Table(data, colWidths=list(col_widths), hAlign="LEFT", repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2a44")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d1d5db")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9fafb")]),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return table


def _code_block(text: str, body_style: ParagraphStyle) -> XPreformatted:
    wrapped = _wrap_to_width(
        text,
        max_width=_CONTENT_WIDTH - 8,
        font=CJK_FONT_NAME,
        size=body_style.fontSize,
    )
    return XPreformatted(escape("\n".join(wrapped)), body_style)


def _status_banner(status: str, error_message: str | None) -> Paragraph | None:
    """失败/取消任务加一条显式横幅：报告可以导出，但读者必须先看到状态。"""
    normalized = str(status or "").upper()
    if normalized in {"SUCCESS", ""}:
        return None
    label = {"FAILURE": "任务失败", "CANCELED": "任务已取消", "TIMEOUT": "任务超时"}.get(
        normalized, f"任务状态：{normalized}"
    )
    detail = f"：{error_message}" if error_message else ""
    return Paragraph(
        escape(f"{label}{detail} —— 本报告用于复盘，结论段可能为空。"),
        _style(
            "banner",
            fontSize=9,
            leading=13,
            textColor=colors.HexColor("#8a1c1c"),
            backColor=colors.HexColor("#fdecec"),
            borderPadding=6,
            spaceBefore=6,
            spaceAfter=6,
        ),
    )


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


def build_result_report_pdf(
    package: Mapping[str, Any],
    *,
    conclusions: Sequence[Mapping[str, str]] = (),
    package_sha256: str = "",
    generated_at: datetime | None = None,
) -> bytes:
    """把一个追溯包渲染成 PDF 报告字节串。

    纯函数式：同入参 + 同 ``generated_at`` 得到逐字节相同的输出（便于测试与
    「历史记录不可变」的复核），不访问数据库、不写文件。
    """
    _ensure_cjk_font()

    body = _style("body", fontSize=8.5, leading=12)
    mono = _style("mono", fontSize=7.2, leading=9.2)
    stamp = generated_at.isoformat(sep=" ", timespec="seconds") if generated_at else "-"

    environment = package.get("environment") or {}
    tool = environment.get("tool") or {}
    model = environment.get("model") or {}
    timeline = package.get("timeline") or {}
    params = package.get("params") or {}
    service_process = package.get("process") or {}
    submitted_by = package.get("submittedBy") or {}

    story: list[Any] = []
    story.append(
        Paragraph(
            escape("中国医药 AIDD 平台"),
            _style("platform", fontSize=9, leading=12, textColor=colors.HexColor("#2f6fdb")),
        )
    )
    story.append(
        Paragraph(
            escape(f"结果分析报告 · {_text(package.get('taskName'), '未命名任务')}"),
            _style("title", fontSize=17, leading=22, spaceBefore=2, spaceAfter=2),
        )
    )
    story.append(
        Paragraph(
            escape(
                f"生成时间 {stamp} · 报告模板 {REPORT_TEMPLATE_VERSION} · "
                f"追溯包版本 {_text(package.get('packageVersion'))}"
            ),
            _style("meta", fontSize=8, leading=11, textColor=colors.HexColor("#6b7280")),
        )
    )
    story.append(Spacer(1, 6))

    banner = _status_banner(str(package.get("status") or ""), service_process.get("exitMessage"))
    if banner is not None:
        story.append(banner)

    # 1) 任务身份 -------------------------------------------------------
    story.append(_section_title("一、任务身份"))
    model_label = (
        f"{_text(model.get('name'))} / {_text(model.get('version'))}"
        if isinstance(model, Mapping)
        else _text(model)
    )
    story.append(
        _kv_table(
            [
                ("任务 ID", package.get("taskId")),
                ("任务名称", package.get("taskName")),
                ("任务状态", package.get("status")),
                ("任务类型", package.get("taskType")),
                ("提交人", submitted_by.get("displayName") or submitted_by.get("email")),
                ("提交人 ID", submitted_by.get("userId")),
                ("归属项目", package.get("projectId")),
                (
                    "工具",
                    f"{_text(tool.get('name'))} / {_text(tool.get('version'))}"
                    if isinstance(tool, Mapping)
                    else _text(tool),
                ),
                ("模型", model_label),
                ("运行镜像", environment.get("image")),
                ("执行器类型", environment.get("executorType")),
                ("资源快照", environment.get("resourceSnapshot")),
            ],
            value_style=body,
        )
    )

    # 2) 时间线 ---------------------------------------------------------
    story.append(_section_title("二、时间线"))
    story.append(
        _kv_table(
            [
                ("创建时间", timeline.get("created")),
                ("开始时间", timeline.get("started")),
                ("结束时间", timeline.get("finished")),
                ("执行时长（秒）", timeline.get("executionSeconds")),
                ("重试次数", timeline.get("retryCount")),
            ],
            value_style=body,
        )
    )

    execution_seconds = timeline.get("executionSeconds")
    if isinstance(execution_seconds, (int, float)) and execution_seconds > 0:
        story.append(Spacer(1, 6))
        story.append(_chart_caption("图 1 · 执行时长（秒）"))
        story.append(
            _bar_chart(
                categories=["本次执行"],
                values=[float(execution_seconds)],
                unit_suffix="s",
            )
        )

    # 3) 运行参数 -------------------------------------------------------
    story.append(_section_title("三、运行参数（requested）"))
    param_text, param_truncated = _json_block(params.get("requested"))
    if param_text == "-":
        story.append(Paragraph(escape("本任务未记录运行参数。"), body))
    else:
        story.append(_code_block(param_text, mono))
    if param_truncated:
        story.append(
            Paragraph(
                escape(
                    f"参数 JSON 超过 {MAX_PARAM_CHARS} 字符，已截断；"
                    f"完整内容见追溯包导出（POST /api/v1/results/{_text(package.get('taskId'))}:export）。"
                ),
                _style("note", fontSize=7.5, leading=10, textColor=colors.HexColor("#8a6d1c")),
            )
        )

    # 4) 输入 -----------------------------------------------------------
    story.append(_section_title("四、输入"))
    inputs = list(package.get("inputs") or [])
    if not inputs:
        story.append(Paragraph(escape("无冻结输入记录。"), body))
    else:
        story.append(
            _matrix_table(
                ["角色", "序号", "URN", "SHA256", "数据版本"],
                [
                    [
                        item.get("inputRole"),
                        item.get("ordinal"),
                        item.get("urn"),
                        item.get("sha256"),
                        item.get("dataVersion"),
                    ]
                    for item in inputs
                ],
                col_widths=[22 * mm, 12 * mm, _CONTENT_WIDTH - 22 * mm - 12 * mm - 34 * mm - 16 * mm, 34 * mm, 16 * mm],
                body_style=body,
            )
        )

    # 5) 产物 -----------------------------------------------------------
    story.append(_section_title("五、产物"))
    outputs = list(package.get("outputs") or [])
    if not outputs:
        story.append(Paragraph(escape("无产物记录。"), body))
    else:
        story.append(
            _matrix_table(
                ["类型", "URN", "SHA256", "大小（字节）", "文件名"],
                [
                    [
                        item.get("semanticType") or item.get("artifactType"),
                        item.get("urn"),
                        item.get("sha256"),
                        item.get("sizeBytes"),
                        item.get("filename"),
                    ]
                    for item in outputs
                ],
                col_widths=[30 * mm, _CONTENT_WIDTH - 30 * mm - 32 * mm - 20 * mm - 36 * mm, 32 * mm, 20 * mm, 36 * mm],
                body_style=body,
            )
        )
        sized = [
            (str(item.get("filename") or item.get("semanticType") or "产物"), float(item.get("sizeBytes") or 0) / 1024.0)
            for item in outputs
            if isinstance(item.get("sizeBytes"), (int, float)) and item.get("sizeBytes")
        ]
        if sized:
            story.append(Spacer(1, 6))
            story.append(_chart_caption("图 2 · 各产物大小（KB）"))
            story.append(
                _bar_chart(
                    categories=[name[:18] for name, _ in sized][:8],
                    values=[value for _, value in sized][:8],
                    unit_suffix="KB",
                    height=42 + 16 * min(len(sized), 8),
                )
            )

    # 6) 结论 -----------------------------------------------------------
    story.append(_section_title("六、结论与关键指标"))
    if conclusions:
        story.append(
            _matrix_table(
                ["来源", "指标", "值"],
                [
                    [row.get("source"), row.get("path"), row.get("value")]
                    for row in conclusions
                ],
                col_widths=[26 * mm, _CONTENT_WIDTH - 26 * mm - 52 * mm, 52 * mm],
                body_style=body,
            )
        )
    else:
        story.append(
            Paragraph(
                escape("本任务未产出结构化指标。"),
                _style("empty", fontSize=8.5, leading=12, textColor=colors.HexColor("#6b7280")),
            )
        )

    # 7) 版本信息 -------------------------------------------------------
    story.append(_section_title("七、版本信息"))
    story.append(
        _kv_table(
            [
                ("报告模板版本", REPORT_TEMPLATE_VERSION),
                ("追溯包版本", package.get("packageVersion")),
                ("追溯包 SHA256", package_sha256),
                ("追溯包导出时间", package.get("exportedAt")),
                ("契约版本", environment.get("contractVersion")),
            ],
            value_style=body,
        )
    )

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=_PAGE_MARGIN,
        rightMargin=_PAGE_MARGIN,
        topMargin=_PAGE_MARGIN + 8,
        bottomMargin=_PAGE_MARGIN + 14,
        title=f"结果分析报告 {_text(package.get('taskName'), '')}".strip(),
        author="中国医药 AIDD 平台",
        subject=f"taskId={_text(package.get('taskId'))} template={REPORT_TEMPLATE_VERSION}",
        creator="AIDD platform report renderer",
    )
    footer_note = f"traceability sha256: {package_sha256 or '-'}"
    doc.build(
        story,
        onFirstPage=_header,
        onLaterPages=_header,
        canvasmaker=lambda *args, **kwargs: _NumberedCanvas(
            *args, footer_note=footer_note, **kwargs
        ),
    )
    return buffer.getvalue()


__all__ = [
    "CJK_FONT_NAME",
    "MAX_PARAM_CHARS",
    "REPORT_TEMPLATE_VERSION",
    "build_result_report_pdf",
    "extract_conclusions",
]
