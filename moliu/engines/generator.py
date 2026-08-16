"""生成引擎 — 组装上下文 + 调用 LLM 生成正文"""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path

from moliu.config import Config
from moliu.data.schemas import ChapterMeta, ChapterResult, CharacterCard, NarratorCard, WorldSetting
from moliu.engines.gateway import DeepSeekGateway
from moliu.prompts.manager import PromptManager


logger = logging.getLogger(__name__)


class SegmentGenerationError(Exception):
    """分段生成中某段调用失败(已保存前序段,可用 resume_from 恢复)

    Attributes:
        chapter_num: 失败的章节号
        failed_segment: 失败的段名 ("middle" / "ending")
        resume_from: 下次重试应传入的 resume_from 值
    """

    def __init__(self, chapter_num: int, failed_segment: str, cause: Exception) -> None:
        self.chapter_num = chapter_num
        self.failed_segment = failed_segment
        # 失败段就是下次重试的起点(前序段已落盘)
        self.resume_from = failed_segment
        self.__cause__ = cause
        super().__init__(
            f"第{chapter_num}章 {failed_segment} 段生成失败: {cause}. "
            f"前序段已保存,可用 resume_from=\"{failed_segment}\" 或 `mo resume` 恢复."
        )


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

    def __init__(self, config: Config, gateway: DeepSeekGateway, prompts: PromptManager, *, novel_id: int = 1):
        self.config = config
        self.novel_id = novel_id
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

        output_dir = self.config.resolve_output_dir(self.novel_id)
        recent_chapters = []
        start_chapter = max(1, chapter_num - max_chapters)

        for num in range(start_chapter, chapter_num):
            meta_path = output_dir / Config.chapter_dir_name(num) / "meta.json"
            if meta_path.exists():
                try:
                    meta = ChapterMeta.from_json(meta_path)
                    recent_chapters.append(meta.to_context())
                except Exception:
                    # 如果 meta.json 解析失败，尝试从正文提取
                    text_path = output_dir / Config.chapter_dir_name(num) / "正文.md"
                    if text_path.exists():
                        content = text_path.read_text(encoding="utf-8")
                        summary = self._extract_summary_from_text(content, num)
                        recent_chapters.append(summary)

        if recent_chapters:
            return "\n\n".join(recent_chapters)
        return ""

    def _build_global_progress(self, chapter_num: int) -> str:
        """构造全局进度感知块(问题10)

        从 NovelIndex 加载本书的 target_chapters 与已完成章节数,
        生成一段提示,让 LLM 意识到"现在是全书第 X 章,共 Y 章"。

        失败时返回空字符串(优雅降级,不阻断生成)。
        """
        try:
            from moliu.data.schemas import NovelIndex
            index_path = self.config.resolve_novel_index_path()
            if not index_path.exists():
                return ""
            index = NovelIndex.from_json(index_path)
            novel = index.get(self.novel_id)
            if novel is None or novel.target_chapters <= 0:
                return ""

            total = novel.target_chapters
            # 统计已完成章节数(目录存在即视为已生成)
            output_dir = self.config.resolve_output_dir(self.novel_id)
            done = 0
            if output_dir.exists():
                done = sum(
                    1 for d in output_dir.iterdir()
                    if d.is_dir() and Config.parse_chapter_num(d.name) is not None
                )

            pct = round(done / total * 100, 1)
            remaining = max(0, total - chapter_num)

            # 进度提示语
            phase = "开篇阶段"
            if chapter_num >= total * 0.8:
                phase = "收尾阶段"
            elif chapter_num >= total * 0.5:
                phase = "下半场"
            elif chapter_num >= total * 0.25:
                phase = "中段推进"

            lines = [
                f"【全局进度感知】当前是全书第 {chapter_num} 章,计划共 {total} 章。",
                f"已完成约 {done} 章({pct}%),当前处于 {phase},距全书结束还有 {remaining} 章。",
                "请据此把握节奏:开篇阶段重点建立世界观与角色,中段推进主线与冲突,收尾阶段收束伏笔与悬念。",
            ]
            return "\n".join(lines)
        except Exception as e:
            import logging
            logging.getLogger(__name__).debug(
                "全局进度感知加载失败 novel=%s ch=%d: %s", self.novel_id, chapter_num, e,
            )
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

        import logging
        logger = logging.getLogger(__name__)
        
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
            logger.warning(f"LLM 摘要生成失败，回退到启发式方法。章节: {chapter_num}, 错误: {str(e)[:100]}")
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
        resume_from: str | None = None,  # 用于分段重试
        memory_context: str = "",  # 分层记忆(P0-1)
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
            resume_from: 分段重试时从哪里继续 ("middle" 或 "ending")
            memory_context: 分层记忆上下文(中期阶段摘要 + 长期 Story Bible)
        """
        # 自动回灌前文
        if auto_recent and not recent_chapters:
            recent_chapters = self.load_recent_chapters(chapter_num)

        # 全局进度感知(问题10):注入章节数/总目标/进度百分比到 LLM
        global_progress = self._build_global_progress(chapter_num)

        # 解析章节类型 (LLM 优先，回退启发式)
        chapter_type = await self._resolve_chapter_type_with_llm(chapter_num, chapter_type, beat)

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
                resume_from=resume_from,
                memory_context=memory_context,
                global_progress=global_progress,
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
                memory_context=memory_context,
                global_progress=global_progress,
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
        # 手动指定的类型直接返回
        if chapter_type != "auto":
            valid_types = ["normal", "opening", "setup", "climax", "transition", "epilogue"]
            if chapter_type in valid_types:
                return chapter_type
            # 无效类型，回退到 normal
            return "normal"

        # auto 模式：使用启发式规则（快速路径）
        # 第一章通常是开场
        if chapter_num == 1:
            return "opening"
        # 前三章是铺垫
        elif chapter_num <= 3:
            return "setup"
        # 默认是普通章节
        else:
            return "normal"

    async def _resolve_chapter_type_with_llm(self, chapter_num: int, chapter_type: str, beat: str) -> str:
        """
        解析章节类型，支持 LLM 智能判断

        Args:
            chapter_num: 章节号
            chapter_type: 用户指定的章节类型
            beat: 本章节拍（用于 LLM 判断）

        Returns:
            解析后的章节类型
        """
        # 手动指定的类型直接返回
        if chapter_type != "auto":
            valid_types = ["normal", "opening", "setup", "climax", "transition", "epilogue"]
            if chapter_type in valid_types:
                return chapter_type
            return "normal"

        # 第一章固定为开场（不需要 LLM 判断）
        if chapter_num == 1:
            return "opening"

        # 最后一章固定为收尾
        # （这里我们不知道总章节数，所以使用 LLM 判断）

        # 使用 LLM 判断章节类型
        try:
            system_prompt = """你是一个小说编辑专家，请根据章节节拍判断章节类型。

章节类型说明：
- opening: 开场章，介绍世界观和主要人物
- setup: 铺垫章，为后续冲突做准备
- normal: 普通章，推进主线剧情
- climax: 高潮章，爆发重大冲突
- transition: 过渡章，承上启下
- epilogue: 收尾章，收束故事或卷末

请只输出章节类型名称，不需要其他解释。
"""

            user_prompt = f"章节号: {chapter_num}\n章节节拍: {beat}\n\n请判断这个章节的类型:"

            result, _ = await self.gateway.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.1,
                max_tokens=10,
            )

            result = result.strip()
            valid_types = ["normal", "opening", "setup", "climax", "transition", "epilogue"]
            if result in valid_types:
                return result
        except Exception as e:
            # LLM 调用失败，回退到启发式规则
            import logging
            logger = logging.getLogger(__name__)
            logger.debug(f"LLM 章节类型判断失败，回退到启发式规则: {str(e)[:50]}")
            pass

        # 回退到启发式规则
        if chapter_num == 1:
            return "opening"
        elif chapter_num <= 3:
            return "setup"
        else:
            return "normal"

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
        memory_context: str = "",
        global_progress: str = "",
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

        # 分层记忆(P0-1):拼接到 chapter_guidance 之前,作为前文记忆
        full_guidance = ""
        if memory_context:
            full_guidance += memory_context + "\n\n"
        full_guidance += chapter_guidance

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
            chapter_guidance=full_guidance,
        )

        # 渲染 User Prompt
        user_prompt = self.prompts.render(
            "chapter_generate.user.j2",
            chapter_num=chapter_num,
            beat=beat,
            last_emotion=last_emotion,
            recent_chapters=recent_chapters,
            global_progress=global_progress,
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
        resume_from: str | None = None,  # "middle" 或 "ending"，用于重试
        memory_context: str = "",
        global_progress: str = "",
    ) -> ChapterResult:
        """
        分段生成一章（三幕结构：opening/middle/ending）

        支持中间结果落盘和重试：
        - 每段生成完成后自动保存到临时文件
        - 如果某段失败，下次可以从失败位置继续
        """
        # 组装角色上下文
        character_context = "\n\n".join(
            c.to_context() for c in characters
        )

        # 准备叙述者相关变量
        # 获取章节类型写作指导
        chapter_guidance = self._get_chapter_guidance(chapter_type)
        # 分层记忆(P0-1):拼接到 chapter_guidance 之前
        if memory_context:
            chapter_guidance = memory_context + "\n\n" + chapter_guidance
        narrator_context = ""
        banned_phrases: list[str] = []

        if narrator_card:
            narrator_context = narrator_card.to_context()
            if narrator_card.banned_phrases:
                banned_phrases = narrator_card.banned_phrases
        elif narrator_guide:
            narrator_context = narrator_guide

        total_tokens = 0
        
        # 检查是否有需要恢复的中间结果
        opening_content = ""
        middle_content = ""
        
        # 尝试从临时文件恢复
        if resume_from:
            opening_content = self._load_segment(chapter_num, "opening")
            if resume_from == "ending":
                middle_content = self._load_segment(chapter_num, "middle")
        else:
            # 新生成时保存 beat 和 chapter_type
            self._save_segment(chapter_num, "beat", beat)
            self._save_segment(chapter_num, "chapter_type", chapter_type)

        # ========== Part 1: Opening (开场) ==========
        if not opening_content:  # 只有在没有恢复内容时才生成
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
                global_progress=global_progress,
            )

            opening_content, opening_tokens = await self.gateway.generate(
                system_prompt=opening_system,
                user_prompt=opening_user,
                temperature=temperature,
                max_tokens=4096,
            )
            total_tokens += opening_tokens
            
            # 保存中间结果
            self._save_segment(chapter_num, "opening", opening_content)

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

        if not middle_content:  # 只有在没有恢复内容时才生成
            # 发展部分：使用开场内容的情绪（问题4: 优先 LLM 提取,失败降级规则版）
            opening_emotion = await self._extract_emotion_with_llm(opening_content) \
                or self._extract_emotion_from_text(opening_content) \
                or last_emotion
            middle_user = self.prompts.render(
                "chapter_generate.user.j2",
                chapter_num=chapter_num,
                beat=f"{beat} — 发展部分",
                last_emotion=opening_emotion,
                recent_chapters="",  # 本章内部分段，不传前文
            )
            # 问题2: middle 段失败时自动重试 1 次,仍失败则抛 SegmentGenerationError
            # opening 已落盘,后续可用 resume_from="middle" 恢复
            middle_content, middle_tokens = await self._generate_segment_with_retry(
                segment_name="middle",
                chapter_num=chapter_num,
                system_prompt=middle_system,
                user_prompt=middle_user,
                temperature=temperature,
            )
            total_tokens += middle_tokens

            # 保存中间结果
            self._save_segment(chapter_num, "middle", middle_content)

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

        # 结尾部分：使用发展部分的情绪（问题4: 优先 LLM 提取）
        middle_emotion = await self._extract_emotion_with_llm(middle_content) \
            or self._extract_emotion_from_text(middle_content) \
            or opening_emotion
        ending_user = self.prompts.render(
            "chapter_generate.user.j2",
            chapter_num=chapter_num,
            beat=f"{beat} — 结尾部分",
            last_emotion=middle_emotion,
            recent_chapters="",  # 本章内部分段，不传前文
        )

        ending_content, ending_tokens = await self._generate_segment_with_retry(
            segment_name="ending",
            chapter_num=chapter_num,
            system_prompt=ending_system,
            user_prompt=ending_user,
            temperature=temperature,
        )
        total_tokens += ending_tokens

        # 保存中间结果
        self._save_segment(chapter_num, "ending", ending_content)

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

    async def _generate_segment_with_retry(
        self,
        *,
        segment_name: str,
        chapter_num: int,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
        max_retries: int = 1,
        retry_delay: float = 1.0,
    ) -> tuple[str, int]:
        """问题2: 分段生成调用 LLM,失败时自动重试 1 次

        - 失败原因多为网络抖动/限流/服务端 5xx,短暂等待后重试通常能成功
        - 仍失败时抛 SegmentGenerationError,前序段已落盘,可 resume_from 恢复
        - opening 段不在此方法内(因为 opening 失败时无前序段,直接抛原异常即可)
        """
        last_exc: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                content, tokens = await self.gateway.generate(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    temperature=temperature,
                    max_tokens=4096,
                )
                return content, tokens
            except Exception as e:
                last_exc = e
                if attempt < max_retries:
                    logger.warning(
                        "第%d章 %s 段生成失败(第%d次尝试): %s,%.1fs 后重试",
                        chapter_num, segment_name, attempt + 1, e, retry_delay,
                    )
                    await asyncio.sleep(retry_delay)
                else:
                    logger.error(
                        "第%d章 %s 段生成失败(已重试%d次): %s",
                        chapter_num, segment_name, max_retries, e,
                    )
        # 重试耗尽,抛出带 resume_from 信息的异常
        assert last_exc is not None
        raise SegmentGenerationError(chapter_num, segment_name, last_exc)

    def _get_segment_dir(self, chapter_num: int) -> Path:
        """获取分段临时文件目录"""
        segment_dir = self.config.resolve_data_dir(self.novel_id) / f"chapter_{chapter_num:03d}" / "segments"
        segment_dir.mkdir(parents=True, exist_ok=True)
        return segment_dir

    def _save_segment(self, chapter_num: int, segment_name: str, content: str) -> None:
        """保存分段内容到临时文件"""
        segment_dir = self._get_segment_dir(chapter_num)
        segment_file = segment_dir / f"{segment_name}.txt"
        segment_file.write_text(content, encoding="utf-8")

    def _load_segment(self, chapter_num: int, segment_name: str) -> str:
        """从临时文件加载分段内容"""
        segment_file = self._get_segment_dir(chapter_num) / f"{segment_name}.txt"
        if segment_file.exists():
            return segment_file.read_text(encoding="utf-8")
        return ""

    def _list_saved_segments(self, chapter_num: int) -> list[str]:
        """列出已保存的分段"""
        segment_dir = self._get_segment_dir(chapter_num)
        if not segment_dir.exists():
            return []
        segments = []
        for segment_name in ["opening", "middle", "ending"]:
            if (segment_dir / f"{segment_name}.txt").exists():
                segments.append(segment_name)
        return segments

    def _load_beat(self, chapter_num: int) -> str:
        """从临时文件加载原始 beat"""
        segment_file = self._get_segment_dir(chapter_num) / "beat.txt"
        if segment_file.exists():
            return segment_file.read_text(encoding="utf-8")
        return ""

    def _load_chapter_type(self, chapter_num: int) -> str:
        """从临时文件加载原始 chapter_type"""
        segment_file = self._get_segment_dir(chapter_num) / "chapter_type.txt"
        if segment_file.exists():
            return segment_file.read_text(encoding="utf-8")
        return "auto"

    def _clear_segments(self, chapter_num: int) -> None:
        """清理分段临时文件（章节生成完成后调用）"""
        segment_dir = self._get_segment_dir(chapter_num)
        if segment_dir.exists():
            import shutil
            shutil.rmtree(segment_dir, ignore_errors=True)

    async def _extract_emotion_with_llm(self, content: str) -> str | None:
        """问题4: 用 LLM 提取情绪标签(更精准),失败时返回 None 降级到规则版

        优势:
        - 规则版只能识别预定义关键词,无法处理隐喻/情境情绪
        - LLM 能理解上下文(如"他攥紧拳头,指节发白"→愤怒)
        - 支持复合情绪(如"紧张→愤怒→释然")

        Returns:
            情绪标签字符串,LLM 调用失败时返回 None(由调用方降级)
        """
        # 只取末尾 400 字(反映段落收尾情绪,用于衔接下一段)
        text = content[-400:] if len(content) > 400 else content
        try:
            resp, _ = await self.gateway.generate(
                system_prompt=(
                    "你是小说编辑助手。分析文本的情感基调。"
                    "只输出一个中文情绪词(如紧张/轻松/悲伤/愤怒/惊喜/危险/神秘),"
                    "或用'→'连接的情绪变化轨迹(2-3个词)。不要输出其他内容。"
                ),
                user_prompt=f"分析以下文本的情绪:\n\n{text}",
                max_tokens=30,
                temperature=0.3,
            )
            emotion = resp.strip().strip(""""'""")
            # 简单校验:非空且长度合理(1-30字)
            if emotion and 1 <= len(emotion) <= 30:
                return emotion
            return None
        except Exception as e:
            logger.debug("LLM 情绪提取失败,降级到规则版: %s", e)
            return None

    def _extract_emotion_from_text(self, content: str) -> str | None:
        """
        从文本中提取情绪标签（用于分段生成时的情绪传递）
        
        改进版：
        - 只分析文本最后 200 字（更能反映当前情绪状态）
        - 统计每种情绪的命中次数
        - 返回命中次数最多的情绪
        
        Args:
            content: 文本内容
            
        Returns:
            情绪标签（如"紧张"、"轻松"等），无法提取则返回 None
        """
        # 只看最后 200 字
        content = content[-200:] if len(content) > 200 else content
        
        # 情绪关键词映射
        emotion_keywords = {
            "紧张": ["紧张", "焦急", "急切", "焦虑", "不安", "慌张", "急促", "紧迫", "危机"],
            "轻松": ["轻松", "悠闲", "惬意", "愉快", "欢乐", "开心", "温馨", "平静", "淡然"],
            "悲伤": ["悲伤", "难过", "伤心", "悲痛", "失落", "哀伤", "哭泣", "沮丧", "黯然"],
            "愤怒": ["愤怒", "生气", "恼怒", "暴怒", "愤慨", "火大", "暴跳如雷", "气愤"],
            "惊喜": ["惊喜", "惊讶", "震惊", "意外", "喜出望外", "大吃一惊", "愕然"],
            "危险": ["危险", "危机", "凶险", "紧急", "千钧一发", "命悬一线", "危急"],
            "神秘": ["神秘", "诡异", "离奇", "不可思议", "扑朔迷离", "费解"],
        }
        
        # 统计每种情绪的命中次数
        emotion_counts: dict[str, int] = {}
        for emotion, keywords in emotion_keywords.items():
            count = 0
            for keyword in keywords:
                count += content.count(keyword)
            if count > 0:
                emotion_counts[emotion] = count
        
        # 如果没有匹配到任何情绪，返回 None
        if not emotion_counts:
            return None
        
        # 返回命中次数最多的情绪
        max_count = max(emotion_counts.values())
        # 如果有多个情绪命中次数相同，返回第一个
        for emotion, count in emotion_counts.items():
            if count == max_count:
                return emotion
        
        return None

    def _merge_segments(self, opening: str, middle: str, ending: str) -> str:
        """
        合并三部分内容，处理重复和过渡

        问题5: 优化去重逻辑
        - 扩大检查窗口(50→200 字),捕捉更长重复
        - 用最大重叠子串匹配(而非简单包含),能处理部分重叠
        - 在句子边界对齐(避免截断句子)
        - 最小重叠阈值 10 字,避免误删短句

        Args:
            opening: 开场部分
            middle: 发展部分
            ending: 结尾部分

        Returns:
            合并后的完整章节内容
        """
        segments = [opening.strip(), middle.strip(), ending.strip()]
        segments = [s.rstrip("\n") for s in segments]

        result = []
        for i, segment in enumerate(segments):
            if i == 0:
                result.append(segment)
                continue
            # 问题5: 用改进的去重逻辑合并
            merged = self._deduplicate_overlap(result[-1], segment)
            result[-1], deduped_segment = merged
            if deduped_segment:
                result.append(deduped_segment)

        return "\n\n\n".join([s for s in result if s])

    def _deduplicate_overlap(self, prev: str, curr: str) -> tuple[str, str]:
        """问题5: 找出 prev 结尾与 curr 开头的最大重叠并去重

        策略:
        1. 取 prev 末尾和 curr 开头各 200 字作为搜索窗口
        2. 找最大公共子串(前段结尾 == 后段开头)
        3. 若重叠 >= 10 字,在句子边界对齐后去除
        4. 返回 (去重后的 prev, 去重后的 curr)

        Args:
            prev: 前一段内容
            curr: 当前段内容

        Returns:
            (prev_trimmed, curr_trimmed)
        """
        if not prev or not curr:
            return prev, curr

        window = 200
        prev_tail = prev[-window:] if len(prev) > window else prev
        curr_head = curr[:window] if len(curr) > window else curr

        # 找最大重叠:prev_tail 的后缀 == curr_head 的前缀
        max_overlap = 0
        min_overlap = 10  # 最小阈值,避免误删短词
        check_len = min(len(prev_tail), len(curr_head))

        for length in range(check_len, min_overlap - 1, -1):
            if prev_tail[-length:] == curr_head[:length]:
                max_overlap = length
                break

        if max_overlap == 0:
            return prev, curr

        # 在句子边界对齐(避免截断句子)
        overlap_text = curr_head[:max_overlap]
        # 找重叠区域中最后一个句子结束符(。！？…)
        sentence_end_chars = "。！？…"
        last_sentence_end = -1
        for idx, ch in enumerate(overlap_text):
            if ch in sentence_end_chars:
                last_sentence_end = idx

        if last_sentence_end >= 0 and last_sentence_end < max_overlap - 3:
            # 在句子边界切分,保留完整句子在前段
            # 前 0~last_sentence_end 留给 prev,后面给 curr
            cut_in_curr = last_sentence_end + 1
            # 从 prev 末尾移除重叠部分(保留到句子结束)
            prev_keep_len = len(prev) - (max_overlap - cut_in_curr)
            prev_trimmed = prev[:prev_keep_len].rstrip()
            curr_trimmed = curr[cut_in_curr:].lstrip()
        else:
            # 无合适句子边界,直接在重叠处切分
            prev_trimmed = prev[:len(prev) - max_overlap].rstrip()
            curr_trimmed = curr[max_overlap:].lstrip()

        return prev_trimmed, curr_trimmed

    def _get_next_version(self, chapter_num: int) -> int:
        """
        获取下一版本号

        Args:
            chapter_num: 章节号

        Returns:
            下一个版本号
        """
        output_dir = self.config.resolve_output_dir(self.novel_id) / Config.chapter_dir_name(chapter_num)
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

        output_dir = self.config.resolve_output_dir(self.novel_id) / Config.chapter_dir_name(result.chapter_num)
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

        output_dir = self.config.resolve_output_dir(self.novel_id) / Config.chapter_dir_name(chapter_num)
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
        output_dir = self.config.resolve_output_dir(self.novel_id) / Config.chapter_dir_name(chapter_num)
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
        output_dir = self.config.resolve_output_dir(self.novel_id) / Config.chapter_dir_name(chapter_num)
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
        backup_path = self.config.resolve_output_dir(self.novel_id)

        for character in characters:
            # 设置备份路径
            character.set_backup_path(backup_path)

            # 先备份当前状态（保存更新前的状态）
            character.backup(chapter_num)

            # 从正文中提取状态变化并更新（使用严格模式，减少误判）
            character.update_state_from_text(content, strict=True)

            # 记录最后出场章节(供内建图谱上下文使用)
            if character.state:
                character.state.last_chapter_appeared = chapter_num

            # 保存更新后的角色卡到角色目录
            self._save_character(character)

    def _save_character(self, character: CharacterCard) -> None:
        """
        保存角色卡到角色目录

        同时写入 data/novels/{id}/characters/(源数据,供下次加载)
        和 output/novels/{id}/chapters/characters/(生成快照)。

        Args:
            character: 角色卡
        """
        # 1. 源数据目录 — 后续 load_characters / inject_graph_context 从这里读
        data_chars = self.config.resolve_data_dir(self.novel_id) / "characters"
        data_chars.mkdir(parents=True, exist_ok=True)
        character.to_yaml(data_chars / f"{character.name}.yaml")

        # 2. 输出快照目录(保留兼容)
        output_dir = self.config.resolve_output_dir(self.novel_id) / "characters"
        output_dir.mkdir(parents=True, exist_ok=True)
        character.to_yaml(output_dir / f"{character.name}.yaml")
