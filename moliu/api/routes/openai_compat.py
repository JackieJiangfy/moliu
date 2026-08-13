"""OpenAI 兼容接口 — 让 OpenWebUI 直接连接墨流后端

OpenWebUI 把墨流当作一个 OpenAI 兼容 API:
  - GET  /v1/models       → 返回虚拟模型列表
  - POST /v1/chat/completions → 对话式创作（章节生成/大纲规划/元数据回填）

用户在 OpenWebUI 中:
  1. 设置 → 外部链接 → 添加 OpenAI 兼容 API → URL 填 http://host.docker.internal:8000/v1
  2. 模型选择器中出现 "📝 章节生成助手" 等虚拟模型
  3. 选择模型后直接对话创作
"""

from __future__ import annotations

import json
import re
import asyncio
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel

router = APIRouter()


# --- 虚拟模型定义 ---

VIRTUAL_MODELS = [
    {
        "id": "moliu-chapter-generator",
        "name": "📝 章节生成助手",
        "description": "对话式生成小说章节。输入章节号和节拍，自动执行 Gatekeeper 预检 + 完整生成管线。",
    },
    {
        "id": "moliu-outline-planner",
        "name": "📐 大纲规划助手",
        "description": "规划卷结构和章节大纲。创建卷、查看卷列表、批量生成大纲。",
    },
    {
        "id": "moliu-metadata-backfill",
        "name": "🔧 元数据回填助手",
        "description": "批量补全章节元数据（标题/情绪/关键事件）。",
    },
]


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    stream: bool = False
    temperature: float | None = None


@router.get("/v1/models")
async def list_models():
    """返回虚拟模型列表（OpenAI 兼容格式）"""
    return {
        "object": "list",
        "data": [
            {
                "id": m["id"],
                "object": "model",
                "name": m["name"],
                "description": m["description"],
                "created": 1700000000,
                "owned_by": "moliu",
            }
            for m in VIRTUAL_MODELS
        ],
    }


@router.post("/v1/chat/completions")
async def chat_completions(request: Request, body: ChatCompletionRequest):
    """对话式创作 — 根据选择的虚拟模型执行不同操作"""

    # 获取最后一条用户消息
    user_messages = [m for m in body.messages if m.role == "user"]
    if not user_messages:
        return JSONResponse(
            status_code=400,
            content={"error": {"message": "没有用户消息"}},
        )
    user_input = user_messages[-1].content.strip()

    # 根据模型分发
    if body.model == "moliu-chapter-generator":
        response_text = await _handle_chapter_generation(request, user_input)
    elif body.model == "moliu-outline-planner":
        response_text = await _handle_outline_planning(request, user_input)
    elif body.model == "moliu-metadata-backfill":
        response_text = await _handle_metadata_backfill(request, user_input)
    else:
        response_text = f"未知模型: {body.model}。请选择墨流虚拟模型。"

    # 返回 OpenAI 兼容格式
    if body.stream:
        return StreamingResponse(
            _stream_response(body.model, response_text),
            media_type="text/event-stream",
        )
    else:
        return {
            "id": f"chatcmpl-moliu-{id(body):x}",
            "object": "chat.completion",
            "created": 1700000000,
            "model": body.model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": response_text},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        }


async def _stream_response(model: str, text: str):
    """流式返回（逐段推送）"""
    # 按段落分割，逐段推送
    chunks = text.split("\n")
    for chunk in chunks:
        data = {
            "id": f"chatcmpl-moliu-stream",
            "object": "chat.completion.chunk",
            "created": 1700000000,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "delta": {"content": chunk + "\n"},
                    "finish_reason": None,
                }
            ],
        }
        yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
        await asyncio.sleep(0.02)

    # 结束标记
    yield "data: [DONE]\n\n"


# --- 章节生成 ---

async def _handle_chapter_generation(request: Request, user_input: str) -> str:
    """处理章节生成对话"""
    cfg = request.app.state.config
    import httpx

    # 解析用户输入
    parsed = _parse_chapter_input(user_input)

    if not parsed.get("chapter_num"):
        return (
            "## 📝 章节生成助手\n\n"
            "我可以帮你生成小说章节。请告诉我：\n\n"
            "**格式示例：**\n"
            "```\n"
            "生成第126章\n"
            "节拍：沈夜发现验钞机56%的真相\n"
            "情绪：紧张\n"
            "```\n\n"
            "或者更简单：\n"
            "```\n"
            "126 沈夜发现验钞机56%的真相\n"
            "```\n\n"
            "我会自动执行：\n"
            "1. Gatekeeper 强制信息收集校验\n"
            "2. 上下文组装（前文+角色+世界观+伏笔）\n"
            "3. 三段式生成（开场→发展→结尾）\n"
            "4. 去AI味改写\n"
            "5. 一致性检查 + 读者评估\n"
            "6. 落盘保存 + 记忆存储\n"
        )

    chapter_num = parsed["chapter_num"]
    beat = parsed.get("beat", "")
    emotion = parsed.get("emotion", "轻松")

    if not beat:
        return f"请提供第 {chapter_num} 章的节拍描述（一句话描述本章发生的事情）。\n\n例如：`{chapter_num} 沈夜发现验钞机56%的真相`"

    # Step 1: Gatekeeper 预检
    from moliu.cli.utils import load_characters
    from moliu.engines.gatekeeper import Gatekeeper

    all_chars = load_characters(cfg)
    gatekeeper = Gatekeeper(cfg)
    gk = await gatekeeper.check(
        chapter_num, all_chars,
        beat=beat, emotion=emotion,
        force_check=True,
    )

    if not gk.passed:
        lines = ["## ❌ 预检未通过\n"]
        lines.append("以下信息缺失，请补充后重试：\n")
        for item in gk.missing_items:
            lines.append(f"- {item}")
        if gk.warnings:
            lines.append("\n**警告：**")
            for w in gk.warnings:
                lines.append(f"- ⚠ {w}")
        return "\n".join(lines)

    # Step 2: 执行生成
    from moliu.api.routes.chapters import _run_generation

    try:
        gen = await _run_generation(
            cfg,
            chapter_num=chapter_num,
            beat=beat,
            emotion=emotion,
            characters_filter=[],
            chapter_type="auto",
            temperature=None,
        )
    except Exception as e:
        return f"## ❌ 生成失败\n\n错误: {str(e)[:300]}"

    result = gen["result"]
    qr = gen["quality"]

    lines = [
        f"## ✅ 第 {chapter_num} 章生成完成！\n",
        f"**字数**: {result.word_count}",
        f"**Token**: {result.tokens_used}",
        f"**保存**: `{gen['filepath']}`\n",
    ]

    if gk.warnings:
        lines.append("**预检警告：**")
        for w in gk.warnings:
            lines.append(f"- ⚠ {w}")
        lines.append("")

    if gk.context_hints:
        lines.append("**提示：**")
        for h in gk.context_hints:
            lines.append(f"- 💡 {h}")
        lines.append("")

    lines.append("**正文预览：**\n")
    lines.append(f"```\n{result.content[:500]}...\n```")

    lines.append(f"\n**质检报告：**\n```\n{qr.summary()}\n```")

    return "\n".join(lines)


# --- 大纲规划 ---

async def _handle_outline_planning(request: Request, user_input: str) -> str:
    """处理大纲规划对话"""
    cfg = request.app.state.config

    # 解析命令
    if "列表" in user_input or "查看" in user_input or "list" in user_input.lower():
        return await _list_volumes(cfg)
    elif "创建" in user_input or "新建" in user_input or "create" in user_input.lower():
        return await _create_volume(cfg, user_input)
    else:
        return (
            "## 📐 大纲规划助手\n\n"
            "我可以帮你管理卷结构和大纲。支持以下操作：\n\n"
            "- **查看卷列表**：输入「列表」或「查看」\n"
            "- **创建新卷**：输入「创建 卷名 第1-30章 摘要」\n"
            "- **生成大纲**：输入「生成大纲 第31-50章」\n\n"
            "当前卷结构：\n"
            + await _list_volumes(cfg)
        )


async def _list_volumes(cfg) -> str:
    """列出所有卷"""
    import json
    from pathlib import Path

    index_path = cfg.resolve_data_dir() / "volumes" / "index.json"
    if not index_path.exists():
        return "卷索引不存在。请先创建卷。"

    data = json.loads(index_path.read_text(encoding="utf-8"))
    lines = [f"## 📖 {data.get('novel_title', '未命名')} — 卷列表\n"]

    for vol in data.get("volumes", []):
        status_emoji = {"completed": "✅", "active": "🔵", "planned": "⚪"}.get(vol["status"], "⚪")
        lines.append(f"{status_emoji} **卷 {vol['id']}：{vol['name']}**")
        lines.append(f"   - 章节: {vol['chapter_start']}-{vol['chapter_end']}")
        lines.append(f"   - 摘要: {vol.get('summary', '无')}")
        lines.append("")

    return "\n".join(lines)


async def _create_volume(cfg, user_input: str) -> str:
    """创建新卷"""
    import json
    from pathlib import Path
    from datetime import datetime

    index_path = cfg.resolve_data_dir() / "volumes" / "index.json"
    if not index_path.exists():
        return "卷索引不存在。"

    data = json.loads(index_path.read_text(encoding="utf-8"))

    # 尝试解析用户输入
    # 格式: 创建 卷名 第31-80章 摘要
    match = re.search(r'创建\s+(.+?)\s+第(\d+)-(\d+)章\s*(.*)', user_input)
    if not match:
        return (
            "创建卷的格式：\n```\n"
            "创建 功德币风云 第31-80章 银行业务扩展，功德币体系引入\n"
            "```"
        )

    name = match.group(1).strip()
    start = int(match.group(2))
    end = int(match.group(3))
    summary = match.group(4).strip() or "待补充"

    new_id = max(v["id"] for v in data["volumes"]) + 1 if data["volumes"] else 1
    data["volumes"].append({
        "id": new_id,
        "name": name,
        "subtitle": "",
        "chapter_start": start,
        "chapter_end": end,
        "summary": summary,
        "arcs": [],
        "chapters": [],
        "status": "planned",
        "created_at": datetime.utcnow().isoformat() + "Z",
        "updated_at": datetime.utcnow().isoformat() + "Z",
    })

    index_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    return f"## ✅ 卷 {new_id} 创建成功\n\n**名称**: {name}\n**范围**: 第{start}-{end}章\n**摘要**: {summary}"


# --- 元数据回填 ---

async def _handle_metadata_backfill(request: Request, user_input: str) -> str:
    """处理元数据回填对话"""
    cfg = request.app.state.config

    # 解析范围
    match = re.search(r'第(\d+)-(\d+)章', user_input)
    if match:
        start = int(match.group(1))
        end = int(match.group(2))
    elif "全部" in user_input or "all" in user_input.lower():
        # 统计缺失
        from pathlib import Path
        output_dir = cfg.resolve_output_dir()
        missing_count = 0
        total = 0
        for ch_dir in sorted(output_dir.iterdir()):
            if ch_dir.is_dir() and ch_dir.name.startswith("第"):
                meta_path = ch_dir / "meta.json"
                if meta_path.exists():
                    total += 1
                    import json
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                    if not meta.get("emotion") or not meta.get("key_events") or meta.get("title", "").startswith("第"):
                        missing_count += 1
        return (
            f"## 🔧 元数据回填助手\n\n"
            f"共 {total} 章，其中 {missing_count} 章缺少元数据。\n\n"
            f"要开始回填，请在终端运行：\n"
            f"```\nmo backfill all --dry-run\n```\n"
            f"预览后再运行：\n"
            f"```\nmo backfill all\n```\n"
            f"或指定范围：\n"
            f"```\nmo backfill 16-125\n```\n"
        )
    else:
        return (
            "## 🔧 元数据回填助手\n\n"
            "我可以帮你批量补全章节元数据（标题/情绪/关键事件）。\n\n"
            "**使用方式：**\n"
            "- 输入「全部」查看缺失统计\n"
            "- 输入「第16-125章」指定范围\n\n"
            "回填操作需要调用 LLM，请在终端运行：\n"
            "```\n"
            "mo backfill all          # 补全所有缺失\n"
            "mo backfill 16-125       # 补全指定范围\n"
            "mo backfill all --dry-run # 预览不修改\n"
            "```"
        )


# --- 输入解析 ---

def _parse_chapter_input(user_input: str) -> dict:
    """解析用户输入，提取章节号、节拍、情绪

    支持格式：
    - "生成第126章 节拍：xxx 情绪：紧张"
    - "126 沈夜发现验钞机56%的真相"
    - "第126章\n节拍：xxx\n情绪：紧张"
    """
    result = {}

    # 提取章节号
    ch_match = re.search(r'第?(\d+)章', user_input)
    if ch_match:
        result["chapter_num"] = int(ch_match.group(1))
    else:
        # 尝试开头纯数字
        num_match = re.match(r'^(\d+)\s', user_input)
        if num_match:
            result["chapter_num"] = int(num_match.group(1))

    if not result.get("chapter_num"):
        return result

    # 提取节拍
    beat_match = re.search(r'节拍[：:]\s*(.+?)(?:\n|$|情绪)', user_input)
    if beat_match:
        result["beat"] = beat_match.group(1).strip()
    else:
        # 去掉章节号后剩余的内容作为节拍
        text = re.sub(r'第?\d+章', '', user_input)
        text = re.sub(r'^\d+\s', '', text)
        text = re.sub(r'生成|节拍[：:]|情绪[：:].*', '', text)
        text = text.strip()
        if text:
            result["beat"] = text

    # 提取情绪
    emotion_match = re.search(r'情绪[：:]\s*(\S+)', user_input)
    if emotion_match:
        result["emotion"] = emotion_match.group(1).strip()

    return result
