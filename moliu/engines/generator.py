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

    async def _generate_summary_with_llm(self, content: str, chapter_num: int) -> str:
        """
        使用 LLM 生成高质量摘要（主要方案）
        
        Args:
            content: 章节正文
            chapter_num: 章节号
            
        Returns:
            200字左右的高质量摘要
        """
        system_prompt = """你是一位专业的小说编辑。请为以下章节生成一篇200字左右的摘要。
        
摘要要求：
1. 包含本章主要事件和转折点
2. 保持故事连贯性和可读性
3. 使用简洁的语言
4. 保留关键角色的行动和动机
5. 不要加入个人评价或分析
6. 语言风格与原文保持一致

输出格式：直接输出摘要内容，不需要额外说明。
"""

        user_prompt = f"第{chapter_num}章正文：\n\n{content[:3000]}\n\n---\n请为此章节生成200字左右的摘要："

        try:
            summary, _ = await self.gateway.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.3,
                max_tokens=512,
            )
            return f"第{chapter_num}章【摘要】{summary.strip()}"
        except Exception as e:
            # 失败时回退到启发式方法，并输出 warning
            import warnings
            warnings.warn(f"LLM 摘要生成失败，回退到启发式方法。章节: {chapter_num}, 错误: {str(e)[:100]}")
            return self._extract_summary_from_text(content, chapter_num)

    def _extract_summary_from_text(self, content: str, chapter_num: int) -> str:
        """从正文中提取摘要（备用方案/降级方案）"""
        # 使用正则表达式按多种句末符号切分
        # 支持：句号。、感叹号！、问号？、省略号…、换行符
        sentences = re.split(r"[。！？…]+", content)
        sentences = [s.strip() for s in sentences if s.strip()]

        if len(sentences) >= 2:
            first_part = "。".join(sentences[:2])
            last_part = "。".join(sentences[-2:]) if len(sentences) >= 4 else sentences[-1]
            return f"第{chapter_num}章【摘要】{first_part}。{last_part}"
        elif content:
            # 取前100字（去除多余空白）
            clean_content = re.sub(r"\s+", " ", content.strip())
            return f"第{chapter_num}章【摘要】{clean_content[:100]}..."
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
        segmented: bool = True,
        chapter_type: str = "normal",
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
            segmented: 是否使用分段生成（三幕结构：opening/middle/ending）
            chapter_type: 章节类型 (normal/opening/climax/transition/epilogue)
        """
        # 自动回灌前文
        if auto_recent and not recent_chapters:
            recent_chapters = self.load_recent_chapters(chapter_num)

        # 解析章节类型
        chapter_type = self._resolve_chapter_type(chapter_num, chapter_type)

        if segmented:
            return await self._generate_chapter_segmented(
                chapter_num=chapter_num,
                beat=beat,
                characters=characters,
                world=world,
                last_emotion=last_emotion,
                recent_chapters=recent_chapters,
                narrator_guide=narrator_guide,
                narrator_card=narrator_card,
                temperature=temperature,
                chapter_type=chapter_type,
            )
        else:
            return await self._generate_chapter_single(
                chapter_num=chapter_num,
                beat=beat,
                characters=characters,
                world=world,
                last_emotion=last_emotion,
                recent_chapters=recent_chapters,
                narrator_guide=narrator_guide,
                narrator_card=narrator_card,
                temperature=temperature,
                chapter_type=chapter_type,
            )

    def _resolve_chapter_type(self, chapter_num: int, chapter_type: str) -> str:
        """
        解析章节类型，支持自动检测和手动指定

        Args:
            chapter_num: 章节号
            chapter_type: 用户指定的章节类型

        Returns:
            解析后的章节类型
        """
        # 自动检测章节类型（如果用户没有指定或指定为 auto）
        if chapter_type == "auto":
            if chapter_num == 1:
                return "opening"  # 第一章通常是开场
            elif chapter_num <= 3:
                return "setup"  # 前三章是铺垫
            else:
                return "normal"  # 默认是普通章节

        # 验证章节类型
        valid_types = ["normal", "opening", "setup", "climax", "transition", "epilogue"]
        if chapter_type not in valid_types:
            # 无效类型，回退到 normal
            return "normal"

        return chapter_type

    def _get_chapter_guidance(self, chapter_type: str) -> str:
        """
        根据章节类型获取写作指导

        Args:
            chapter_type: 章节类型

        Returns:
            针对该类型章节的写作指导文本
        """
        guidance_map = {
            "opening": """【章节类型：开场章】
- 目标：引人入胜，建立世界观和主角
- 节奏：缓慢铺垫，逐步展开
- 重点：展示主角的日常/困境，埋下伏笔
- 结尾：留下悬念或钩子""",
            "setup": """【章节类型：铺垫章】
- 目标：介绍配角、展开冲突
- 节奏：平稳推进，信息交代
- 重点：人物关系、背景设定
- 结尾：为后续冲突做准备""",
            "normal": """【章节类型：普通章】
- 目标：推进主线剧情
- 节奏：张弛有度
- 重点：角色成长、情节发展
- 结尾：自然过渡到下一章""",
            "climax": """【章节类型：高潮章】
- 目标：爆发冲突，达到顶点
- 节奏：紧凑紧张，快速推进
- 重点：战斗、对决、重大抉择
- 结尾：给出阶段性结果或反转""",
            "transition": """【章节类型：过渡章】
- 目标：承上启下，转换场景
- 节奏：相对舒缓
- 重点：总结前情、铺垫后续
- 结尾：明确下一段剧情方向""",
            "epilogue": """【章节类型：收尾章】
- 目标：收束故事或卷末
- 节奏：缓慢收束
- 重点：交代结局、展示成长
- 结尾：留下回味空间""",
        }
        return guidance_map.get(chapter_type, guidance_map["normal"])

    async def _generate_chapter_single(
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
        chapter_type: str = "normal",
    ) -> ChapterResult:
        """
        单次调用生成一章（原始模式）
        """
        # 组装角色上下文
        character_context = "\n\n".join(
            c.to_context() for c in characters
        )

        # 准备叙述者相关变量
        narrator_context = ""
        banned_phrases: list[str] = []

        if narrator_card:
            narrator_context = narrator_card.to_context()
            if narrator_card.banned_phrases:
                banned_phrases = narrator_card.banned_phrases
        elif narrator_guide:
            narrator_context = narrator_guide

        # 根据章节类型获取写作指导
        chapter_guidance = self._get_chapter_guidance(chapter_type)

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
            chapter_guidance=chapter_guidance,
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

        word_count = count_words(content)

        return ChapterResult(
            chapter_num=chapter_num,
            content=content,
            word_count=word_count,
            model_used=self.config.deepseek_model,
            tokens_used=tokens,
        )

    async def _generate_chapter_segmented(
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
        chapter_type: str = "normal",
    ) -> ChapterResult:
        """
        分段生成一章（三幕结构：opening/middle/ending）
        """
        # 组装角色上下文
        character_context = "\n\n".join(
            c.to_context() for c in characters
        )

        # 准备叙述者相关变量
        # 获取章节类型写作指导
        chapter_guidance = self._get_chapter_guidance(chapter_type)
        narrator_context = ""
        banned_phrases: list[str] = []

        if narrator_card:
            narrator_context = narrator_card.to_context()
            if narrator_card.banned_phrases:
                banned_phrases = narrator_card.banned_phrases
        elif narrator_guide:
            narrator_context = narrator_guide

        total_tokens = 0

        # ========== Part 1: Opening (开场) ==========
        opening_system = self.prompts.render(
            "chapter_generate.opening.system.j2",
            world_setting=world.to_context(),
            narrator_card=narrator_context if narrator_card else "",
            narrator_guide=narrator_context if not narrator_card else "",
            character_context=character_context,
            banned_phrases=banned_phrases,
            chapter_guidance=chapter_guidance,
        )

        opening_user = self.prompts.render(
            "chapter_generate.user.j2",
            chapter_num=chapter_num,
            beat=f"{beat} — 开场部分",
            last_emotion=last_emotion,
            recent_chapters=recent_chapters,
        )

        opening_content, opening_tokens = await self.gateway.generate(
            system_prompt=opening_system,
            user_prompt=opening_user,
            temperature=temperature,
            max_tokens=2048,
        )
        total_tokens += opening_tokens

        # ========== Part 2: Middle (发展) ==========
        middle_system = self.prompts.render(
            "chapter_generate.middle.system.j2",
            world_setting=world.to_context(),
            narrator_card=narrator_context if narrator_card else "",
            narrator_guide=narrator_context if not narrator_card else "",
            character_context=character_context,
            banned_phrases=banned_phrases,
            previous_content=opening_content,
            chapter_guidance=chapter_guidance,
        )

        # 发展部分：使用开场内容的情绪（从开场提取或默认），不传前文（这是本章内部）
        opening_emotion = self._extract_emotion_from_text(opening_content) or last_emotion
        middle_user = self.prompts.render(
            "chapter_generate.user.j2",
            chapter_num=chapter_num,
            beat=f"{beat} — 发展部分",
            last_emotion=opening_emotion,
            recent_chapters="",  # 本章内部分段，不传前文
        )

        middle_content, middle_tokens = await self.gateway.generate(
            system_prompt=middle_system,
            user_prompt=middle_user,
            temperature=temperature,
            max_tokens=2048,
        )
        total_tokens += middle_tokens

        # ========== Part 3: Ending (结尾) ==========
        ending_system = self.prompts.render(
            "chapter_generate.ending.system.j2",
            world_setting=world.to_context(),
            narrator_card=narrator_context if narrator_card else "",
            narrator_guide=narrator_context if not narrator_card else "",
            character_context=character_context,
            banned_phrases=banned_phrases,
            previous_content=opening_content + "\n\n" + middle_content,
            chapter_guidance=chapter_guidance,
        )

        # 结尾部分：使用发展部分的情绪，不传前文
        middle_emotion = self._extract_emotion_from_text(middle_content) or opening_emotion
        ending_user = self.prompts.render(
            "chapter_generate.user.j2",
            chapter_num=chapter_num,
            beat=f"{beat} — 结尾部分",
            last_emotion=middle_emotion,
            recent_chapters="",  # 本章内部分段，不传前文
        )

        ending_content, ending_tokens = await self.gateway.generate(
            system_prompt=ending_system,
            user_prompt=ending_user,
            temperature=temperature,
            max_tokens=2048,
        )
        total_tokens += ending_tokens

        # 合并三部分内容
        full_content = self._merge_segments(opening_content, middle_content, ending_content)
        word_count = count_words(full_content)

        return ChapterResult(
            chapter_num=chapter_num,
            content=full_content,
            word_count=word_count,
            model_used=self.config.deepseek_model,
            tokens_used=total_tokens,
        )

    def _extract_emotion_from_text(self, content: str) -> str | None:
        """
        从文本中简单提取情绪标签（用于分段生成时的情绪传递）
        
        Args:
            content: 文本内容
            
        Returns:
            情绪标签（如"紧张"、"轻松"等），无法提取则返回 None
        """
        # 简单的情绪词匹配
        emotion_keywords = {
            "紧张": ["紧张", "焦急", "急切", "焦虑", "不安", "慌张", "急促", "紧迫", "危机"],
            "轻松": ["轻松", "悠闲", "惬意", "愉快", "欢乐", "开心", "温馨", "平静"],
            "悲伤": ["悲伤", "难过", "伤心", "悲痛", "失落", "哀伤", "哭泣", "沮丧"],
            "愤怒": ["愤怒", "生气", "恼怒", "暴怒", "愤慨", "火大", "暴跳如雷"],
            "惊喜": ["惊喜", "惊讶", "震惊", "意外", "喜出望外", "大吃一惊"],
            "危险": ["危险", "危机", "凶险", "紧急", "千钧一发", "命悬一线"],
            "神秘": ["神秘", "诡异", "离奇", "不可思议", "扑朔迷离"],
        }
        
        # 匹配情绪词
        for emotion, keywords in emotion_keywords.items():
            for keyword in keywords:
                if keyword in content:
                    return emotion
        
        return None

    def _merge_segments(self, opening: str, middle: str, ending: str) -> str:
        """
        合并三部分内容，处理重复和过渡

        Args:
            opening: 开场部分
            middle: 发展部分
            ending: 结尾部分

        Returns:
            合并后的完整章节内容
        """
        segments = [opening.strip(), middle.strip(), ending.strip()]

        # 移除每段末尾的换行
        segments = [s.rstrip("\n") for s in segments]

        # 检查重复（如果某段的开头与前一段的结尾重复，进行去重）
        result = []
        for i, segment in enumerate(segments):
            if i == 0:
                result.append(segment)
            else:
                # 检查当前段是否与前一段有重复
                prev_end = result[-1][-50:] if len(result[-1]) > 50 else result[-1]
                curr_start = segment[:50] if len(segment) > 50 else segment

                if prev_end and curr_start and curr_start in prev_end:
                    # 当前段开头与前段结尾重复，跳过重复部分
                    result.append(segment[len(curr_start):].strip())
                elif prev_end and curr_start and prev_end in curr_start:
                    # 前段结尾在当前段开头中，跳过重复
                    overlap = len(prev_end)
                    result.append(segment[overlap:].strip())
                else:
                    result.append(segment)

        # 用两个换行连接各段
        return "\n\n\n".join([s for s in result if s])

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

    async def async_save_chapter(self, result: ChapterResult, emotion: str = "", summary: str = "", characters: list[CharacterCard] | None = None, version: int | None = None, use_llm_summary: bool = True) -> Path:
        """
        异步保存章节到文件，支持多版本管理和 LLM 摘要

        Args:
            result: 章节生成结果
            emotion: 章节情绪标签
            summary: 章节摘要（可选，若未提供则自动提取）
            characters: 本章出场角色列表（用于状态更新和备份）
            version: 指定版本号（None 表示自动递增）
            use_llm_summary: 是否使用 LLM 生成摘要（True=LLM, False=启发式）

        Returns:
            正文文件路径
        """
        # 如果没有提供摘要，使用 LLM 生成（或回退到启发式）
        if not summary:
            if use_llm_summary:
                llm_summary = await self._generate_summary_with_llm(result.content, result.chapter_num)
                summary = llm_summary.replace(f"第{result.chapter_num}章【摘要】", "")
            else:
                summary = self._extract_summary_from_text(result.content, result.chapter_num).replace(f"第{result.chapter_num}章【摘要】", "")

        return self.save_chapter(result, emotion, summary, characters, version)

    def save_chapter(self, result: ChapterResult, emotion: str = "", summary: str = "", characters: list[CharacterCard] | None = None, version: int | None = None) -> Path:
        """
        保存章节到文件，支持多版本管理（同步版本，使用启发式摘要）

        Args:
            result: 章节生成结果
            emotion: 章节情绪标签
            summary: 章节摘要（可选，若未提供则使用启发式提取）
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

        # 如果没有提供摘要，使用启发式方法自动提取（同步回退）
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

    def _update_version_history(self, chapter_num: int, version: int, emotion: str, summary: str, action: str = "create") -> None:
        """
        更新版本历史记录

        Args:
            chapter_num: 章节号
            version: 版本号
            emotion: 情绪标签
            summary: 摘要
            action: 动作类型 (create/restore)
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

        # 添加新记录
        record = {
            "version": version,
            "action": action,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        if action == "create":
            record["emotion"] = emotion
            record["summary"] = summary[:100] if summary else ""
        elif action == "restore":
            record["from_version"] = version
            record["summary"] = f"恢复到版本 v{version}"

        history.append(record)

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

        # 记录恢复动作到版本历史
        self._update_version_history(chapter_num, version, "", "", action="restore")

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

            # 从正文中提取状态变化并更新（使用严格模式，减少误判）
            character.update_state_from_text(content, strict=True)

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
