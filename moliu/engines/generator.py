"""生成引擎 — 组装上下文 + 调用 LLM 生成正文"""

from __future__ import annotations

import re
from pathlib import Path

from moliu.config import Config
from moliu.data.schemas import ChapterResult, CharacterCard, WorldSetting
from moliu.engines.gateway import DeepSeekGateway
from moliu.prompts.manager import PromptManager


def count_words(text: str) -> int:
    """统计中英文混排字数。

    中文字符使用 Unicode CJK 统一表意文字范围，
    不包含中文标点符号。
    """
    # CJK 统一表意文字 (U+4E00–U+9FFF)
    # CJK 扩展 A (U+3400–U+4DBF)
    cjk = len(re.findall(r"[一-鿿㐀-䶿]", text))
    # 英文单词 (连续的字母)
    english = len(re.findall(r"[a-zA-Z]+", text))
    return cjk + english


class Generator:
    """章节生成器 — Phase 1：单次调用，不分段"""

    def __init__(self, config: Config, gateway: DeepSeekGateway, prompts: PromptManager):
        self.config = config
        self.gateway = gateway
        self.prompts = prompts

    async def generate_chapter(
        self,
        chapter_num: int,
        beat: str,
        characters: list[CharacterCard],
        world: WorldSetting,
        *,
        last_emotion: str = "轻松",
        recent_chapters: str = "",
        narrator_guide: str = "",
        temperature: float | None = None,
    ) -> ChapterResult:
        """
        生成一章正文

        Args:
            chapter_num: 章节号
            beat: 本章节拍（一句话描述本章发生什么）
            characters: 本章出场角色的人设卡列表
            world: 世界观设定
            last_emotion: 上一章收尾情绪标签
            recent_chapters: 前几章的摘要/回顾文本
            narrator_guide: 叙述者风格指南
            temperature: 覆盖默认 temperature
        """
        # 组装角色上下文
        character_context = "\n\n".join(
            c.to_context() for c in characters
        )

        # 渲染 System Prompt
        system_prompt = self.prompts.render(
            "chapter_generate.system.j2",
            world_setting=world.to_context(),
            narrator_guide=narrator_guide,
            character_context=character_context,
            min_words=self.config.chapter_min_words,
            max_words=self.config.chapter_max_words,
        )

        # 渲染 User Prompt
        user_prompt = self.prompts.render(
            "chapter_generate.user.j2",
            chapter_num=chapter_num,
            beat=beat,
            last_emotion=last_emotion,
            recent_chapters=recent_chapters,
        )

        # 调用 API
        content, tokens = await self.gateway.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
        )

        # 中英文混排字数统计
        word_count = count_words(content)

        return ChapterResult(
            chapter_num=chapter_num,
            content=content,
            word_count=word_count,
            model_used=self.config.deepseek_model,
            tokens_used=tokens,
        )

    def save_chapter(self, result: ChapterResult) -> Path:
        """保存章节到文件"""
        output_dir = self.config.resolve_output_dir() / f"第{result.chapter_num}章"
        output_dir.mkdir(parents=True, exist_ok=True)
        filepath = output_dir / "正文.md"
        filepath.write_text(result.content, encoding="utf-8")
        return filepath
