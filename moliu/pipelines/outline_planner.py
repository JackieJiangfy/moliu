"""
墨流 · 大纲规划助手 — OpenWebUI Pipelines 插件

在 OpenWebUI 中注册为虚拟模型「📐 大纲规划助手」。
用户通过对话式交互规划卷大纲和章节大纲。

安装方式:
  1. 将本文件放入 OpenWebUI 的 pipelines 目录
  2. 在 OpenWebUI 设置中启用此 pipeline
  3. 模型列表中会出现「📐 大纲规划助手」
"""

from typing import Optional

try:
    from pipelines.base import Pipeline as BasePipeline
except ImportError:
    class BasePipeline:
        pass

import httpx
import json


class Pipeline(BasePipeline):
    """大纲规划助手 Pipeline"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = "📐 大纲规划助手"
        self.description = "规划卷结构和章节大纲"
        self.moliu_api_url = "http://host.docker.internal:8000"

    async def on_startup(self, **kwargs):
        import os
        self.moliu_api_url = os.getenv("MOLIU_API_URL", self.moliu_api_url)

    async def pipe(self, body: dict, messages: list[dict], user_message: str, **kwargs) -> str:
        msg = user_message.strip()

        # 解析命令
        if msg.startswith("卷列表") or msg.startswith("list"):
            return await self._list_volumes()
        elif msg.startswith("创建卷") or msg.startswith("create"):
            return await self._create_volume(msg)
        elif msg.startswith("删除卷") or msg.startswith("delete"):
            return await self._delete_volume(msg)
        else:
            return (
                "## 📐 大纲规划助手\n\n"
                "支持以下命令：\n\n"
                "- **卷列表** / list — 查看所有卷\n"
                "- **创建卷: 卷名, 1-30, 摘要** — 创建新卷\n"
                "- **删除卷: 1** — 删除指定卷\n\n"
                "示例：\n"
                "```\n"
                "创建卷: 亡灵银行, 1-30, 沈夜继承亡灵银行\n"
                "```"
            )

    async def _list_volumes(self) -> str:
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(f"{self.moliu_api_url}/api/v1/volumes", timeout=10)
                if r.status_code != 200:
                    return f"请求失败: {r.status_code}"
                volumes = r.json()
                if not volumes:
                    return "暂无卷规划。\n\n使用 `创建卷: 卷名, 1-30, 摘要` 创建第一个卷。"
                lines = ["## 📖 卷列表\n"]
                for v in volumes:
                    lines.append(f"**卷{v['id']}: {v['name'] or '(未命名)'}**")
                    lines.append(f"  - 范围: 第{v['chapter_start']}-{v['chapter_end']}章")
                    lines.append(f"  - 状态: {v['status']}")
                    if v['summary']:
                        lines.append(f"  - 摘要: {v['summary'][:60]}")
                    lines.append("")
                return "\n".join(lines)
        except Exception as e:
            return f"请求失败: {e}"

    async def _create_volume(self, msg: str) -> str:
        # 解析: "创建卷: 卷名, 1-30, 摘要"
        content = msg.replace("创建卷", "").replace(":", "").strip()
        parts = [p.strip() for p in content.split(",")]
        if len(parts) < 2:
            return "格式错误。正确格式：`创建卷: 卷名, 1-30, 摘要`"

        name = parts[0]
        range_parts = parts[1].split("-")
        try:
            ch_start = int(range_parts[0])
            ch_end = int(range_parts[1]) if len(range_parts) > 1 else ch_start
        except ValueError:
            return "章节范围格式错误，应为 `1-30`"

        summary = parts[2] if len(parts) > 2 else ""

        try:
            async with httpx.AsyncClient() as client:
                body = {
                    "name": name,
                    "chapter_start": ch_start,
                    "chapter_end": ch_end,
                    "summary": summary,
                }
                r = await client.post(
                    f"{self.moliu_api_url}/api/v1/volumes",
                    json=body,
                    timeout=10,
                )
                if r.status_code == 201:
                    return f"✅ 卷「{name}」（第{ch_start}-{ch_end}章）已创建！"
                else:
                    return f"创建失败: {r.text}"
        except Exception as e:
            return f"请求失败: {e}"

    async def _delete_volume(self, msg: str) -> str:
        import re
        match = re.search(r"(\d+)", msg)
        if not match:
            return "请指定卷 ID，如：`删除卷: 1`"
        vid = int(match.group(1))
        try:
            async with httpx.AsyncClient() as client:
                r = await client.delete(
                    f"{self.moliu_api_url}/api/v1/volumes/{vid}",
                    timeout=10,
                )
                if r.status_code == 204:
                    return f"🗑 卷 {vid} 已删除"
                else:
                    return f"删除失败: {r.text}"
        except Exception as e:
            return f"请求失败: {e}"