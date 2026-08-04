"""生成引擎 — 组装上下文 + 调用 LLM 生成正文"""

from __future__ import annotations

import re
from pathlib import Path

from moliu.config import Config
from moliu.data.schemas import ChapterMeta, ChapterResult, CharacterCard, NarratorCard, WorldSetting
from moliu.engines.gateway import DeepSeekGateway
from moliu.prompts.manager import PromptManager


def count_words(text: str) -> int:
    """统计中英文混排字数。

    中文字符使用 Unicode CJK 统一表意文字范围，
    不包含中文标点符号。
    英文单词按空格/标点分隔的连续字母计算。
    HTML 标签会被忽略。
    """
    # 先移除 HTML 标签
    text = re.sub(r"<[^>]+>", "", text)
    
    # CJK 统一表意文字 (U+4E00–U+9FFF)
    # CJK 扩展 A (U+3400–U+4DBF)
    cjk = len(re.findall(r"[一-鿿㐀-䶿]", text))
    
    # 英文单词 (连续的字母，前后有非字母边界)
    english = len(re.findall(r"(?<![a-zA-Z])[a-zA-Z]+(?![a-zA-Z])", text))
    
    return cjk + english


class Generator:
    """章节生成器 — Phase 1：单次调用，不分段"""

    def __init__(self, config: Config, gateway: DeepSeekGateway, prompts: PromptManager):
        self.config = config
        self.gateway = gateway
        self.prompts = prompts

    def load_recent_chapters(self, chapter_num: int, max_chapters: int = 3) -> str:
        """
        自动回灌前文 - 从之前章节的 meta.json 提取摘要

        Args:
            chapter_num: 当前章节号
            max_chapters: 最多回灌前几章

        Returns:
            前文回顾文本，用于注入 User Prompt
        """
        if chapter_num <= 1:
            return ""

        output_dir = self.config.resolve_output_dir()
        recent_chapters = []
        start_chapter = max(1, chapter_num - max_chapters)

        for num in range(start_chapter, chapter_num):
            meta_path = output_dir / f"第{num}章" / "meta.json"
            if meta_path.exists():
                try:
                    meta = ChapterMeta.from_json(meta_path)
                    recent_chapters.append(meta.to_context())
                except Exception:
                    # 如果 meta.json 解析失败，尝试从正文提取
                    text_path = output_dir / f"第{num}章" / "正文.md"
                    if text_path.exists():
                        content = text_path.read_text(encoding="utf-8")
                        summary = self._extract_summary_from_text(content, num)
                        recent_chapters.append(summary)

        if recent_chapters:
            return "\n\n".join(recent_chapters)
        return ""

    def _extract_summary_from_text(self, content: str, chapter_num: int) -> str:
        """从正文中简单提取摘要（备用方案）"""
        # 提取前几个和后几个句子
        sentences = content.replace("\n", "。").split("。")
        sentences = [s.strip() for s in sentences if s.strip()]

        if len(sentences) >= 2:
            first_part = "。".join(sentences[:2])
            last_part = "。".join(sentences[-2:]) if len(sentences) >= 4 else sentences[-1]
            return f"第{chapter_num}章【摘要】{first_part}...{last_part}"
        elif content:
            # 取前100字
            return f"第{chapter_num}章【摘要】{content[:100]}..."
        return ""

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
        narrator_card: NarratorCard | None = None,
        temperature: float | None = None,
        auto_recent: bool = True,
    ) -> ChapterResult:
        """
        生成一章正文

        Args:
            chapter_num: 章节号
            beat: 本章节拍（一句话描述本章发生什么）
            characters: 本章出场角色的人设卡列表
            world: 世界观设定
            last_emotion: 上一章收尾情绪标签
            recent_chapters: 前几章的摘要/回顾文本（手动指定）
            narrator_guide: 叙述者风格指南（字符串格式，向后兼容）
            narrator_card: 叙述者人设卡（推荐使用，支持动态注入禁用套话）
            temperature: 覆盖默认 temperature
            auto_recent: 是否自动回灌前文（从 meta.json 提取）
        """
        # 自动回灌前文
        if auto_recent and not recent_chapters:
            recent_chapters = self.load_recent_chapters(chapter_num)

        # 组装角色上下文
        character_context = "\n\n".join(
            c.to_context() for c in characters
        )

        # 准备叙述者相关变量
        narrator_context = ""
        banned_phrases: list[str] = []

        if narrator_card:
            # 使用 NarratorCard 渲染上下文
            narrator_context = narrator_card.to_context()
            # 动态提取禁用套话
            if narrator_card.banned_phrases:
                banned_phrases = narrator_card.banned_phrases
        elif narrator_guide:
            # 向后兼容：使用字符串格式的叙述者指南
            narrator_context = narrator_guide

        # 渲染 System Prompt
        system_prompt = self.prompts.render(
            "chapter_generate.system.j2",
            world_setting=world.to_context(),
            narrator_card=narrator_context if narrator_card else "",
            narrator_guide=narrator_context if not narrator_card else "",
            character_context=character_context,
            banned_phrases=banned_phrases,
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

    def _get_next_version(self, chapter_num: int) -> int:
        """
        获取下一版本号

        Args:
            chapter_num: 章节号

        Returns:
            下一个版本号
        """
        output_dir = self.config.resolve_output_dir() / f"第{chapter_num}章"
        versions_dir = output_dir / "versions"

        if not versions_dir.exists():
            return 1

        # 查找已有的版本目录
        version_dirs = sorted(versions_dir.glob("v*"))
        if not version_dirs:
            return 1

        # 提取最大版本号
        max_version = 0
        for v_dir in version_dirs:
            try:
                version = int(v_dir.name[1:])  # 去掉 'v' 前缀
                max_version = max(max_version, version)
            except ValueError:
                continue

        return max_version + 1

    def save_chapter(self, result: ChapterResult, emotion: str = "", summary: str = "", characters: list[CharacterCard] | None = None, version: int | None = None) -> Path:
        """
        保存章节到文件，支持多版本管理

        Args:
            result: 章节生成结果
            emotion: 章节情绪标签
            summary: 章节摘要（可选，若未提供则自动提取）
            characters: 本章出场角色列表（用于状态更新和备份）
            version: 指定版本号（None 表示自动递增）

        Returns:
            正文文件路径
        """
        import datetime

        output_dir = self.config.resolve_output_dir() / f"第{result.chapter_num}章"
        output_dir.mkdir(parents=True, exist_ok=True)

        # 确定版本号
        if version is None:
            version = self._get_next_version(result.chapter_num)
        else:
            # 如果指定了版本号，检查是否已存在
            versions_dir = output_dir / "versions"
            if versions_dir.exists() and (versions_dir / f"v{version}").exists():
                # 如果版本已存在，自动递增
                current_max = self._get_next_version(result.chapter_num)
                version = max(version, current_max)

        # 保存到版本目录
        versions_dir = output_dir / "versions"
        versions_dir.mkdir(parents=True, exist_ok=True)
        version_dir = versions_dir / f"v{version}"
        version_dir.mkdir(parents=True, exist_ok=True)

        # 提取首尾句
        content = result.content
        sentences = content.replace("\n", "。").split("。")
        sentences = [s.strip() for s in sentences if s.strip()]

        first_sentence = sentences[0] if sentences else ""
        last_sentence = sentences[-1] if sentences else ""

        # 如果没有提供摘要，自动提取
        if not summary:
            summary = self._extract_summary_from_text(content, result.chapter_num).replace(f"第{result.chapter_num}章【摘要】", "")

        # 提取出场角色
        key_characters = []
        if characters:
            key_characters = [c.name for c in characters]
            # 更新角色状态并备份
            self._update_and_backup_characters(characters, content, result.chapter_num)

        # 生成版本目录中的 meta.json
        meta = ChapterMeta(
            chapter_num=result.chapter_num,
            word_count=result.word_count,
            tokens_used=result.tokens_used,
            emotion=emotion,
            summary=summary,
            key_characters=key_characters,
            key_events=[],
            first_sentence=first_sentence,
            last_sentence=last_sentence,
            created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            updated_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        )

        # 保存版本目录中的文件
        version_content_path = version_dir / "正文.md"
        version_content_path.write_text(content, encoding="utf-8")
        meta.to_json(version_dir / "meta.json")

        # 更新根目录的正文和 meta（指向当前版本）
        root_content_path = output_dir / "正文.md"
        root_content_path.write_text(content, encoding="utf-8")
        meta.to_json(output_dir / "meta.json")

        # 更新版本历史记录
        self._update_version_history(result.chapter_num, version, emotion, summary)

        return root_content_path

    def _update_version_history(self, chapter_num: int, version: int, emotion: str, summary: str) -> None:
        """
        更新版本历史记录

        Args:
            chapter_num: 章节号
            version: 版本号
            emotion: 情绪标签
            summary: 摘要
        """
        import datetime

        output_dir = self.config.resolve_output_dir() / f"第{chapter_num}章"
        history_file = output_dir / "version_history.json"

        # 读取现有历史
        history = []
        if history_file.exists():
            try:
                import json
                with open(history_file, "r", encoding="utf-8") as f:
                    history = json.load(f)
            except Exception:
                history = []

        # 添加新版本记录
        history.append({
            "version": version,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "emotion": emotion,
            "summary": summary[:100] if summary else "",
        })

        # 写入历史记录
        import json
        with open(history_file, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)

    def list_versions(self, chapter_num: int) -> list[tuple[int, str, str]]:
        """
        列出章节的所有版本

        Args:
            chapter_num: 章节号

        Returns:
            版本列表 [(版本号, 时间戳, 摘要), ...]
        """
        output_dir = self.config.resolve_output_dir() / f"第{chapter_num}章"
        history_file = output_dir / "version_history.json"

        if not history_file.exists():
            return []

        try:
            import json
            with open(history_file, "r", encoding="utf-8") as f:
                history = json.load(f)
            return [(h["version"], h["timestamp"], h.get("summary", "")) for h in history]
        except Exception:
            return []

    def restore_version(self, chapter_num: int, version: int) -> bool:
        """
        恢复指定版本为当前版本

        Args:
            chapter_num: 章节号
            version: 版本号

        Returns:
            是否恢复成功
        """
        output_dir = self.config.resolve_output_dir() / f"第{chapter_num}章"
        version_dir = output_dir / "versions" / f"v{version}"

        if not version_dir.exists():
            return False

        # 检查版本文件是否存在
        version_content = version_dir / "正文.md"
        version_meta = version_dir / "meta.json"

        if not version_content.exists() or not version_meta.exists():
            return False

        # 复制到根目录
        content = version_content.read_text(encoding="utf-8")
        (output_dir / "正文.md").write_text(content, encoding="utf-8")

        meta_data = version_meta.read_text(encoding="utf-8")
        (output_dir / "meta.json").write_text(meta_data, encoding="utf-8")

        return True

    def _update_and_backup_characters(self, characters: list[CharacterCard], content: str, chapter_num: int) -> None:
        """
        更新角色状态并创建备份

        Args:
            characters: 角色列表
            content: 章节正文
            chapter_num: 章节号
        """
        # 设置备份路径
        backup_path = self.config.resolve_output_dir()

        for character in characters:
            # 设置备份路径
            character.set_backup_path(backup_path)

            # 先备份当前状态（保存更新前的状态）
            character.backup(chapter_num)

            # 从正文中提取状态变化并更新
            character.update_state_from_text(content)

            # 保存更新后的角色卡到角色目录
            self._save_character(character)

    def _save_character(self, character: CharacterCard) -> None:
        """
        保存角色卡到角色目录

        Args:
            character: 角色卡
        """
        output_dir = self.config.resolve_output_dir() / "characters"
        output_dir.mkdir(parents=True, exist_ok=True)
        character.to_yaml(output_dir / f"{character.name}.yaml")
