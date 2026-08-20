# LLM Natural Language Understanding Layer

LLM **只**把自然语言变成 `FigureIntent` JSON。

禁止：生成 R、执行绘图、改 QC 规则、改数据。

LLM 不可用时自动回退到规则解析，保证 Demo 可跑。

## 文件

```
llm/
├── README.md
├── __init__.py
├── llm_client.py
├── prompt_templates.py
└── intent_parser.py
```

## 环境变量（写入 `.env`，不要提交）

```
LLM_ENABLED=false
LLM_PROVIDER=openai
API_KEY=
MODEL_NAME=gpt-4o-mini
LLM_BASE_URL=
```

`LLM_PROVIDER` 可为 `openai` / `deepseek` / `qwen` / `claude` / `openai_compatible`。Claude 需 OpenAI 兼容网关的 `LLM_BASE_URL`。

## 调用

```python
from llm import IntentParser

intent = IntentParser().parse("我有RNA-seq差异分析结果，想做Nature风格火山图")
# intent.figure_type == volcano
```
