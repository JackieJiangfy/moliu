"""元数据回填 — 批量补全章节元数据（标题/情绪/关键事件）

通用模块，不绑定具体小说。通过 LLM 读取章节正文，自动生成缺失的元数据字段。
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Optional

from moliu.config import Config
from moliu.data.schemas import ChapterMeta
from moliu.engines.gateway import DeepSeekGateway

logger = logging.getLogger(__name__)


# --- LLM Prompt 模板 ---

PROMPT_TITLE = """你是一个小说编辑助手。请根据以下章节正文，生成一个简洁有力的标题（不超过15个字）。

要求：
- 标题要概括本章核心事件或情绪
- 不要使用"第X章"格式
- 不要加书名号
- 直接输出标题，不要多余文字

正文：
{content}
"""

PROMPT_EMOTION = """你是一个小说编辑助手。请分析以下章节正文的情感基调。

输出格式：一个词语或多个词语用"→"连接，表示情绪变化。
例如：紧张→愤怒→释然 或 平静→好奇 或 悲伤

要求：
- 使用中文情感词
- 2-5个词为佳
- 反映情绪变化轨迹而非单一情绪

正文（前200字+后200字）：
{content}
"""

PROMPT_EVENTS = """你是一个小说编辑助手。请从以下章节正文中提取1-3个关键事件。

每个事件用一句话概括（不超过25字）。
输出格式：每行一个事件，不要编号。

正文：
{content}
"""


class MetadataBackfiller:
    """元数据回填器 — 通用，不绑定具体小说"""

    def __init__(self, config: Config):
        self.config = config

    async def backfill_chapter(
        self,
        chapter_num: int,
        fields: Optional[list[str]] = None,
    ) -> dict[str, str | list[str]]:
        """
        回填单个章节的元数据

        Args:
            chapter_num: 章节号
            fields: 要回填的字段列表，可选 title/emotion/events，留空则全部

        Returns:
            dict: 回填后的字段值
        """
        output_dir = self.config.resolve_output_dir()
        chapter_dir = output_dir / Config.chapter_dir_name(chapter_num)
        content_path = chapter_dir / "正文.md"
        if not content_path.exists():
            raise FileNotFoundError(f"第{chapter_num}章正文不存在: {content_path}")

        content = content_path.read_text(encoding="utf-8")
        if not content.strip():
            raise ValueError(f"第{chapter_num}章正文为空")

        meta_path = chapter_dir / "meta.json"
        meta = ChapterMeta.from_json(meta_path) if meta_path.exists() else ChapterMeta(chapter_num=chapter_num)

        if fields is None:
            fields = ["title", "emotion", "events"]

        result = {}

        async with DeepSeekGateway(self.config) as gateway:
            if "title" in fields and (not meta.title or meta.title == f"第{chapter_num}章"):
                title = await self._generate_title(gateway, content)
                meta.title = title
                result["title"] = title
                logger.info(f"第{chapter_num}章 标题: {title}")

            if "emotion" in fields and not meta.emotion:
                # 取前200字+后200字
                truncated = (content[:200] + "\n...\n" + content[-200:]) if len(content) > 500 else content
                emotion = await self._generate_emotion(gateway, truncated)
                meta.emotion = emotion
                result["emotion"] = emotion
                logger.info(f"第{chapter_num}章 情绪: {emotion}")

            if "events" in fields and not meta.key_events:
                events = await self._generate_events(gateway, content)
                meta.key_events = events
                result["key_events"] = events
                logger.info(f"第{chapter_num}章 事件: {events}")

        meta.to_json(meta_path)
        return result

    async def backfill_range(
        self,
        start: int,
        end: int,
        fields: Optional[list[str]] = None,
        concurrency: int = 3,
        progress_callback=None,
    ) -> dict[int, dict]:
        """
        批量回填章节元数据

        Args:
            start: 起始章节号
            end: 结束章节号（含）
            fields: 要回填的字段
            concurrency: 并发数
            progress_callback: 进度回调函数 fn(chapter_num, result)

        Returns:
            dict: {chapter_num: {回填字段}}
        """
        semaphore = asyncio.Semaphore(concurrency)

        async def _backfill_one(ch: int) -> tuple[int, dict]:
            async with semaphore:
                try:
                    result = await self.backfill_chapter(ch, fields)
                    return ch, result
                except (FileNotFoundError, ValueError) as e:
                    logger.warning(f"第{ch}章 跳过: {e}")
                    return ch, {}
                except Exception as e:
                    logger.error(f"第{ch}章 失败: {e}")
                    return ch, {}

        tasks = [_backfill_one(ch) for ch in range(start, end + 1)]
        results = {}

        for coro in asyncio.as_completed(tasks):
            ch, result = await coro
            results[ch] = result
            if progress_callback:
                progress_callback(ch, result)

        return results

    async def _generate_title(self, gateway: DeepSeekGateway, content: str) -> str:
        """通过 LLM 生成章节标题"""
        text = content[:1500]
        title, _ = await gateway.generate(
            system_prompt="你是小说编辑助手。生成简洁有力的章节标题（不超过15字）。只输出标题。",
            user_prompt=PROMPT_TITLE.format(content=text),
            max_tokens=30,
            temperature=0.5,
        )
        return title.strip().strip('"').strip('「').strip('」')

    async def _generate_emotion(self, gateway: DeepSeekGateway, content: str) -> str:
        """通过 LLM 生成情绪标签"""
        text = (content[:200] + "\n...\n" + content[-200:]) if len(content) > 500 else content
        emotion, _ = await gateway.generate(
            system_prompt="你是小说编辑助手。分析章节情感基调，输出情绪变化标签。只输出标签。",
            user_prompt=PROMPT_EMOTION.format(content=text),
            max_tokens=30,
            temperature=0.3,
        )
        return emotion.strip()

    async def _generate_events(self, gateway: DeepSeekGateway, content: str) -> list[str]:
        """通过 LLM 提取关键事件"""
        text = content[:2000]
        response, _ = await gateway.generate(
            system_prompt="你是小说编辑助手。提取1-3个关键事件，每行一个。",
            user_prompt=PROMPT_EVENTS.format(content=text),
            max_tokens=150,
            temperature=0.3,
        )
        events = [line.strip().lstrip("0123456789.、- ") for line in response.strip().split("\n") if line.strip()]
        return events[:3]


# --- 辅助函数 ---

def scan_missing_metadata(output_dir: Path) -> list[dict]:
    """
    扫描所有章节，列出缺失元数据的情况

    Returns:
        list[dict]: [{chapter_num, missing_title, missing_emotion, missing_events}]
    """
    results = []
    for chapter_dir in sorted(output_dir.iterdir()):
        if not chapter_dir.is_dir():
            continue
        ch_num = Config.parse_chapter_num(chapter_dir.name)
        if ch_num is None:
            continue

        meta_path = chapter_dir / "meta.json"
        info = {"chapter_num": ch_num}

        if meta_path.exists():
            meta = ChapterMeta.from_json(meta_path)
            info["missing_title"] = not bool(meta.title) or meta.title == f"第{ch_num}章"
            info["missing_emotion"] = not bool(meta.emotion)
            info["missing_events"] = not bool(meta.key_events)
        else:
            info["missing_title"] = True
            info["missing_emotion"] = True
            info["missing_events"] = True

        results.append(info)

    return results


def print_missing_summary(results: list[dict]) -> None:
    """打印缺失统计摘要"""
    total = len(results)
    missing_title = sum(1 for r in results if r["missing_title"])
    missing_emotion = sum(1 for r in results if r["missing_emotion"])
    missing_events = sum(1 for r in results if r["missing_events"])

    print(f"=== 元数据缺失统计 ===")
    print(f"总章节数: {total}")
    print(f"缺标题:   {missing_title} 章")
    print(f"缺情绪:   {missing_emotion} 章")
    print(f"缺事件:   {missing_events} 章")
    print(f"完整:     {total - sum(1 for r in results if r['missing_title'] or r['missing_emotion'] or r['missing_events'])} 章")