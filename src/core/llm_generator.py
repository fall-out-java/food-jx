"""
LLM recipe generation via DashScope (通义千问) API.
Transcription text → structured JSON → formatted markdown tutorial.
"""

import json
import os

DEFAULT_MODEL = "qwen-plus"
DEFAULT_API_KEY_ENV = "DASHSCOPE_API_KEY"

import re

# ─── Default prompts (user can customise in GUI) ────────────

DEFAULT_SYSTEM_PROMPT = """你是一个严格的文档整理工具。将一段美食视频的语音转录文字整理成步骤文档。

## 铁律（必须遵守）
1. 【零编造】只能写转录文字中明确出现的信息。一个字都不能自己编。
2. 【零常识】不要用烹饪常识补充用量、时间、温度、火候。视频没说的，你不能写。
3. 【零推理】不要推断"接下来应该做什么"——只写视频里实际说了什么。
4. 【禁止凭空编号】不能添加转录中没有出现过的数值。如转录说了"两分钟"，duration 应写"两分钟"而非"2分钟"或"120秒"。
5. 【不确定则标注】听不清的地方标注 [转录模糊]。

## 如何让文档更详细（但仍在铁律范围内）
- 转录中提到的事实尽可能全部提取，不要遗漏
- 流程分段要细：转录中自然停顿或换话题的地方就分段
- 每个步骤的 action 尽可能详细描述操作，但只能写转录里出现过的
- detail 字段填入转录中的具体信息：火候描述、现象描述、操作要点
- duration 字段写入转录中明确说的时间，如"煎两分钟"、"约十分钟"
- 如果转录没提到用时，duration 字段不出现

## 输出校验规则（生成后必须执行）
生成完整 JSON 后，逐项检查以下内容。任何一项不合格必须修正后才能输出：

1. 【数值核查】JSON 中每个数字（温度、时间、用量、重量），在转录原文中能找到对应文字
2. 【食材核查】JSON 中每种食材，转录原文中明确提到该食材名称
3. 【步骤核查】JSON 中每一步的操作，转录原文中有对应描述
4. 【因果核查】JSON 中 pitfals 里的 cause/solution，转录原文中明确说了因果关系
5. 【tips核查】JSON 中每条技巧，转录原文中明确说了这个技巧

## 特别注意
- 禁止出现任何转录中没有的数值（温度℃、时间、重量、用量等）
- 禁止使用"适量"、"少许"等没有出现在转录中的表达
- 禁止说"将油温烧至180℃"——转录没讲具体温度就不能写
- 对比色、闻香味等感官描述，仅限转录中明确提到的

请严格按照以下 JSON 格式输出，没有的信息对应字段留空或省略：
{
  "dish_name": "菜名（视频明确说出时填写，否则'未命名'）",
  "prepare": {
    "ingredients": [
      {"name": "食材名", "amount": "视频明确说出用量时填写，否则空字符串", "note": "视频提到预处理方式时填写，否则空字符串", "category": "主料/辅料/调料"}
    ],
    "tools": ["视频明确说出的工具"]
  },
  "steps": [
    {
      "step": 1,
      "title": "步骤标题",
      "action": "详细操作描述（只能写转录原文内容）",
      "detail": "转录中提到的火候、现象、判断标准等具体信息",
      "duration": "转录中明确说的用时，未提及则不出现"
    }
  ],
  "pitfalls": [
    {"problem": "转录明确提到的问题", "cause": "原因（未提及则不出现）", "solution": "解决方法（未提及则不出现）"}
  ],
  "tips": ["转录明确说出的技巧"]
}"""

DEFAULT_USER_TEMPLATE = """以下是一段美食视频的语音转录文字。请严格基于转录文字整理出步骤文档，只写转录中明确出现的信息。可以多分段、详细描述操作，但绝不能添加转录中没有的内容。

转录文字：
{text}"""


def call_llm(
    text: str,
    api_key: str | None = None,
    model: str = DEFAULT_MODEL,
    system_prompt: str | None = None,
    user_template: str | None = None,
) -> str:
    """Call DashScope API and return raw response text."""
    if api_key is None:
        api_key = os.environ.get(DEFAULT_API_KEY_ENV)
    if not api_key:
        raise ValueError(
            f"请设置 {DEFAULT_API_KEY_ENV} 环境变量，或在设置中填写 API Key"
        )

    # Bypass local proxy for Aliyun endpoints (avoids SSL issues)
    os.environ.setdefault("NO_PROXY", "dashscope.aliyuncs.com,aliyuncs.com")

    import dashscope
    dashscope.api_key = api_key

    messages = [
        {"role": "system", "content": system_prompt or DEFAULT_SYSTEM_PROMPT},
        {"role": "user", "content": (user_template or DEFAULT_USER_TEMPLATE).format(text=text)},
    ]

    response = dashscope.Generation.call(
        model=model,
        messages=messages,
        result_format="message",
        temperature=0.05,
        max_tokens=4096,
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"API 请求失败: {response.status_code} {response.message}"
        )

    return response.output.choices[0].message.content


def generate_recipe(
    text: str,
    api_key: str | None = None,
    model: str = DEFAULT_MODEL,
    system_prompt: str | None = None,
    user_template: str | None = None,
) -> dict:
    """Transcription text → structured recipe dict.

    Returns dict with keys: dish_name, prepare, steps, pitfalls, tips.
    On parse failure returns a fallback dict with raw_response.
    """
    raw = call_llm(text, api_key, model, system_prompt, user_template)
    json_str = raw.strip()

    # Strip markdown code fence if present
    if "```" in json_str:
        start = json_str.find("```json\n")
        if start == -1:
            start = json_str.find("```")
            if start != -1:
                start += 3
        else:
            start += 8
        end = json_str.rfind("```")
        if end != -1 and end > start:
            json_str = json_str[start:end].strip()

    try:
        result = json.loads(json_str)
    except json.JSONDecodeError:
        return {"dish_name": "解析失败", "raw_response": raw, "steps": []}

    # 忠实度校验：检测 LLM 是否写了原文没有的内容
    issues = verify_no_hallucination(result, text)
    if issues:
        import warnings
        for issue in issues:
            warnings.warn(f"[food-jx] 可能脑补: {issue}")
        print(f"  ⚠ 检测到 {len(issues)} 处可能脑补的内容，已记录警告")

    return result


def verify_no_hallucination(tutorial: dict, original_text: str) -> list[str]:
    """检查生成的食谱是否有原文未提及的数值/信息，返回所有可疑项。空列表 = 通过。"""
    issues = []
    numbers_in_text = set(re.findall(r'\d+', original_text))

    for step in tutorial.get("steps", []):
        for field in ["detail", "duration", "action"]:
            val = step.get(field, "")
            nums = re.findall(r'\d+', val)
            for n in nums:
                if n not in numbers_in_text:
                    issues.append(
                        f"步骤{step.get('step')} '{field}'中数值 '{n}' 未在原文中出现"
                    )

    for ing in tutorial.get("prepare", {}).get("ingredients", []):
        amt = ing.get("amount", "")
        if amt:
            nums = re.findall(r'\d+', amt)
            for n in nums:
                if n not in numbers_in_text:
                    issues.append(
                        f"食材 '{ing['name']}' 用量中的数值 '{n}' 未在原文中出现"
                    )

    return issues


def render_tutorial_md(tutorial: dict, title: str, url: str, index: int, raw_text: str = "") -> str:
    """Structured recipe dict → formatted markdown tutorial."""
    lines = []

    dish = tutorial.get("dish_name") or title
    lines.append(f"# {dish} 详细操作教程")
    lines.append("")
    lines.append(f"> 来源：{url}")
    lines.append("")

    # ── 准备清单 ──
    prepare = tutorial.get("prepare", {})
    if prepare.get("ingredients") or prepare.get("tools"):
        lines.append("---")
        lines.append("")
        lines.append("## 准备清单")
        lines.append("")

    if ingredients := prepare.get("ingredients"):
        lines.append("### 食材")
        categories = {}
        for item in ingredients:
            cat = item.get("category", "主料")
            categories.setdefault(cat, []).append(item)

        lines.append("")
        lines.append("| 类别 | 食材 | 用量 | 处理备注 |")
        lines.append("|------|------|------|----------|")
        for cat in ["主料", "辅料", "调料"]:
            for item in categories.pop(cat, []):
                lines.append(f"| {cat} | {item.get('name', '')} | {item.get('amount', '')} | {item.get('note', '')} |")
        for cat, items in categories.items():
            for item in items:
                lines.append(f"| {cat} | {item.get('name', '')} | {item.get('amount', '')} | {item.get('note', '')} |")
        lines.append("")

    if tools := prepare.get("tools"):
        lines.append("### 工具")
        lines.append("")
        for t in tools:
            lines.append(f"- {t}")
        lines.append("")

    # ── 操作步骤 ──
    if steps := tutorial.get("steps"):
        lines.append("---")
        lines.append("")
        lines.append("## 操作步骤")
        lines.append("")

        for step in steps:
            num = step.get("step", "")
            stitle = step.get("title", "")
            action = step.get("action", "")
            detail = step.get("detail", "")
            duration = step.get("duration", "")

            heading = f"### 第 {num} 步"
            if stitle:
                heading += f"：{stitle}"
            lines.append(heading)
            lines.append("")

            if action:
                lines.append(action)
                lines.append("")

            if detail:
                lines.append(f"> **关键细节**：{detail}")
                lines.append("")

            if duration:
                lines.append(f"> **用时**：{duration}")
                lines.append("")

    # ── 避坑指南 ──
    if pitfalls := tutorial.get("pitfalls"):
        lines.append("---")
        lines.append("")
        lines.append("## 避坑指南")
        lines.append("")

        for i, p in enumerate(pitfalls, 1):
            problem = p.get("problem", "")
            cause = p.get("cause", "")
            solution = p.get("solution", "")
            lines.append(f"### {i}. {problem}")
            lines.append("")
            if cause:
                lines.append(f"- **原因**：{cause}")
            lines.append(f"- **解决方法**：{solution}")
            lines.append("")

    # ── 小贴士 ──
    if tips := tutorial.get("tips"):
        lines.append("---")
        lines.append("")
        lines.append("## 实用小贴士")
        lines.append("")
        for tip in tips:
            lines.append(f"- {tip}")
        lines.append("")

    lines.append("---")
    lines.append(f"*由 food-jx + 通义千问 自动生成 | 索引 #{index}*")
    lines.append("")

    # ── 原始转录文字 ──
    if raw_text:
        lines.append("---")
        lines.append("")
        lines.append("## 原始转录")
        lines.append("")
        lines.append(raw_text.strip())
        lines.append("")

    return "\n".join(lines)
