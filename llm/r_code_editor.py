"""LLM R code editor — patch ggplot scripts without seeing raw data rows."""

from __future__ import annotations

import logging
import re
from typing import Any

from llm.intent_parser import extract_json_object
from llm.llm_client import LLMClient, LLMError

logger = logging.getLogger("sciplot.llm.r_code_editor")

R_EDITOR_SYSTEM_PROMPT = """你是 SCIPlot AI 的 R / ggplot2 代码编辑器。

任务：根据用户自然语言修改请求，在现有 R 脚本上产出一份完整、可运行的新脚本。

你可以：
- 修改 ggplot aes / geom / scale / labs / theme
- 增加数据列变换（例如 y <- -log10(p) 或 aes(y = -log10(.data[[y_col]])））
- 调整坐标轴标签以匹配变换

你不能：
- 索要、编造或打印原始数据数值 / 行内容
- 改变 input_file 路径或写出到任意系统路径
- 删除必要的 library / read.csv / ggsave 结构（除非用户明确要求）
- 输出 Markdown 解释文字

隐私：你只会看到列名、Spec 摘要与当前 R 源码，看不到 CSV 数值。

输出必须是 JSON（不要 Markdown 代码围栏）：
{
  "r_code": "完整 R 脚本字符串",
  "summary": "一句话说明改了什么"
}
"""

SCIENCE_TRANSFORM_RE = re.compile(
    r"-?\s*log\s*10|log10|log2|-log|"
    r"纵轴|横轴|坐标轴|aes\s*\(|变换|transform|"
    r"scale_[xy]_|coord_|geom_|"
    r"改成\s*-?\s*log|变为\s*-?\s*log",
    re.I,
)


def looks_like_science_transform(user_request: str) -> bool:
    text = (user_request or "").strip()
    if not text:
        return False
    return bool(SCIENCE_TRANSFORM_RE.search(text))


def strip_r_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:r|R)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    return stripped.strip()


class RCodeEditor:
    """Edit existing figure R via LLM. Never receives dataframe values."""

    def __init__(self, client: LLMClient | None = None, *, enabled: bool | None = None) -> None:
        self.client = client if client is not None else LLMClient()
        self.enabled = self.client.available if enabled is None else enabled

    def edit(
        self,
        user_request: str,
        current_r: str,
        *,
        spec_summary: dict[str, Any] | None = None,
        column_names: list[str] | None = None,
    ) -> str:
        if not self.enabled:
            raise LLMError("LLM R code editor unavailable (LLM disabled or API_KEY missing)")
        request = (user_request or "").strip()
        if not request:
            raise LLMError("Empty R edit request")
        if not (current_r or "").strip():
            raise LLMError("No current R script to edit")

        columns = [name for name in (column_names or []) if name]
        summary = dict(spec_summary or {})
        # Never pass row payloads even if a caller mistakes them in.
        for forbidden in ("rows", "dataframe", "raw_data", "values", "csv_body"):
            summary.pop(forbidden, None)

        user_payload = (
            "请按用户要求修改下面的 R 脚本，并返回 JSON。\n\n"
            f"用户修改请求：\n{request}\n\n"
            f"可用列表头（仅列名）：\n{', '.join(columns) if columns else '(unknown)'}\n\n"
            f"Figure Spec 摘要（无数据行）：\n{summary}\n\n"
            f"当前 R 脚本：\n{current_r}\n"
        )
        content = self.client.complete(
            [
                {"role": "system", "content": R_EDITOR_SYSTEM_PROMPT},
                {"role": "user", "content": user_payload},
            ]
        )
        try:
            data = extract_json_object(content)
            code = data.get("r_code") or data.get("code") or ""
        except (ValueError, TypeError):
            code = content
        code = strip_r_fences(str(code))
        if not code or "ggplot" not in code.lower() and "ggsave" not in code.lower():
            # Allow scripts that only transform + plot with unusual structure, but require some R signal.
            if "read.csv" not in code and "library" not in code:
                raise LLMError("LLM R editor returned empty or non-R content")
        if any(token in code.lower() for token in ("password", "api_key", "/etc/passwd")):
            raise LLMError("LLM R editor returned unsafe content")
        return code
