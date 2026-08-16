"""创作意图规划器 — 把自然语言意图拆解成结构化章节蓝图"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from moliu.config import Config
from moliu.data.schemas import ChapterMeta, CharacterCard
from moliu.engines.gateway import DeepSeekGateway
from moliu.prompts.manager import PromptManager

logger = logging.getLogger(__name__)


@dataclass
class ChapterPlan:
    """一章的结构化写作蓝图"""

    chapter_num: int = 0
    beat: str = ""
    emotion: str = "轻松"
    chapter_type: str = "normal"
    characters: list[str] = field(default_factory=list)
    reason: str = ""
    references: list[str] = field(default_factory=list)
    raw_response: str = ""  # 原始 LLM 输出(调试用)

    def is_valid(self) -> bool:
        return self.chapter_num > 0 and bool(self.beat)

    def to_dict(self) -> dict:
        return {
            "chapter_num": self.chapter_num,
            "beat": self.beat,
            "emotion": self.emotion,
            "chapter_type": self.chapter_type,
            "characters": self.characters,
            "reason": self.reason,
            "references": self.references,
        }


class Planner:
    """把作者的模糊创作意图拆解成下一章的结构化蓝图

    工作流：
        1. 加载小说当前状态（最新章号、上一章 summary、角色卡）
        2. 渲染 chapter_plan.system.j2 模板
        3. LLM 输出 JSON
        4. 解析为 ChapterPlan

    用法：
        planner = Planner(config, gateway, prompts, novel_id=1)
        plan = await planner.plan("帮我推进到沈夜发现验钞机真相")
        if plan.is_valid():
            # 用户在前端确认后调 /generate
    """

    VALID_TYPES = {"normal", "opening", "setup", "climax", "transition", "epilogue"}

    def __init__(
        self,
        config: Config,
        gateway: DeepSeekGateway,
        prompts: PromptManager,
        *,
        novel_id: int = 1,
    ):
        self.config = config
        self.gateway = gateway
        self.prompts = prompts
        self.novel_id = novel_id

    async def plan(self, user_intent: str) -> ChapterPlan:
        """把自然语言意图转为结构化章节蓝图

        Args:
            user_intent: 作者的自然语言输入
                         例如 "帮我推进到沈夜发现验钞机真相"
                         "第 30 章重写,要更紧张"
                         "我想写一段沈夜和李建国的对手戏"

        Returns:
            ChapterPlan 结构化蓝图（解析失败时返回带默认值的 plan）
        """
        ctx = self._load_context()
        system_prompt = self.prompts.render(
            "chapter_plan.system.j2",
            novel_title=ctx["novel_title"],
            premise=ctx["premise"],
            genre=ctx["genre"],
            latest_chapter=ctx["latest_chapter"],
            target_chapters=ctx["target_chapters"],
            last_summary=ctx["last_summary"],
            last_emotion=ctx["last_emotion"],
            characters=ctx["characters"],
        )

        try:
            content, _ = await self.gateway.generate(
                system_prompt=system_prompt,
                user_prompt=user_intent,
                temperature=0.7,  # 略带创造性,但稳定
                max_tokens=1024,
            )
        except Exception as e:
            logger.warning("Planner LLM 调用失败: %s", e)
            return ChapterPlan(raw_response=str(e))

        return self._parse(content, fallback_latest=ctx["latest_chapter"])

    # ---------- 上下文加载 ----------

    def _load_context(self) -> dict:
        """加载规划所需的所有上下文（全部同步本地读取，零 LLM 调用）"""
        cfg = self.config
        novel_id = self.novel_id

        # 小说元数据
        novel_title, premise, genre, target_chapters = self._load_novel_meta()

        # 已有章节
        output_dir = cfg.resolve_output_dir(novel_id)
        existing = sorted(
            d for d in output_dir.iterdir()
            if d.is_dir() and Config.parse_chapter_num(d.name) is not None
        ) if output_dir.exists() else []
        latest_chapter = max(
            (Config.parse_chapter_num(d.name) for d in existing if Config.parse_chapter_num(d.name)),
            default=0,
        )

        # 上一章 meta（用于 summary / emotion）
        last_summary = ""
        last_emotion = ""
        if latest_chapter > 0:
            meta = self._load_chapter_meta(latest_chapter)
            if meta:
                last_summary = meta.summary or ""
                last_emotion = meta.emotion or ""

        # 角色卡（最多取前 8 个，避免上下文过长）
        characters = self._load_characters()[:8]

        return {
            "novel_title": novel_title,
            "premise": premise,
            "genre": genre,
            "target_chapters": target_chapters,
            "latest_chapter": latest_chapter,
            "last_summary": last_summary,
            "last_emotion": last_emotion,
            "characters": characters,
        }

    def _load_novel_meta(self) -> tuple[str, str, str, int]:
        """从 novels/index.json 读取小说元数据"""
        index_path = self.config.resolve_novel_index_path()
        if not index_path.exists():
            return "", "", "", 1000
        try:
            data = json.loads(index_path.read_text(encoding="utf-8"))
            for n in data.get("novels", []):
                if n.get("id") == self.novel_id:
                    return (
                        n.get("title", ""),
                        n.get("premise", ""),
                        n.get("genre", ""),
                        n.get("target_chapters", 1000),
                    )
        except Exception as e:
            logger.warning("读取小说元数据失败: %s", e)
        return "", "", "", 1000

    def _load_chapter_meta(self, chapter_num: int) -> ChapterMeta | None:
        """读取指定章节的 meta.json"""
        meta_path = (
            self.config.resolve_output_dir(self.novel_id)
            / Config.chapter_dir_name(chapter_num)
            / "meta.json"
        )
        if not meta_path.exists():
            return None
        try:
            return ChapterMeta.from_json(meta_path)
        except Exception as e:
            logger.warning("读取章节 %d meta 失败: %s", chapter_num, e)
            return None

    def _load_characters(self) -> list[CharacterCard]:
        """加载所有角色卡"""
        chars_dir = self.config.resolve_data_dir(self.novel_id) / "characters"
        if not chars_dir.exists():
            return []
        characters: list[CharacterCard] = []
        for f in sorted(chars_dir.glob("*.yaml")):
            try:
                characters.append(CharacterCard.from_yaml(f))
            except Exception as e:
                logger.warning("跳过角色文件 %s: %s", f.name, e)
        return characters

    # ---------- 解析 ----------

    def _parse(self, text: str, *, fallback_latest: int = 0) -> ChapterPlan:
        """解析 LLM 输出为 ChapterPlan

        优先 JSON 解析，失败时回退到正则提取关键字段。
        """
        raw = text
        # 剥除 markdown 代码块
        cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip())
        cleaned = re.sub(r"\s*```$", "", cleaned)

        # 尝试 JSON
        try:
            data = json.loads(cleaned)
            if isinstance(data, dict):
                return self._from_dict(data, raw=raw, fallback_latest=fallback_latest)
        except json.JSONDecodeError:
            pass

        # 回退：正则提取 {...} 段
        m = re.search(r"\{[^{}]*\}", cleaned, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(0))
                if isinstance(data, dict):
                    return self._from_dict(data, raw=raw, fallback_latest=fallback_latest)
            except json.JSONDecodeError:
                pass

        logger.warning("Planner 输出解析失败,原始: %s", text[:300])
        return ChapterPlan(raw_response=raw)

    def _from_dict(self, data: dict, *, raw: str, fallback_latest: int) -> ChapterPlan:
        """从 dict 构建 ChapterPlan,带容错"""
        chapter_num = data.get("chapter_num") or (fallback_latest + 1)
        try:
            chapter_num = int(chapter_num)
        except (TypeError, ValueError):
            chapter_num = fallback_latest + 1

        beat = str(data.get("beat", "")).strip()
        emotion = str(data.get("emotion", "轻松")).strip() or "轻松"

        chapter_type = str(data.get("chapter_type", "normal")).strip().lower()
        if chapter_type not in self.VALID_TYPES:
            chapter_type = "normal"

        characters = data.get("characters", []) or []
        if not isinstance(characters, list):
            characters = [str(characters)]
        characters = [str(c).strip() for c in characters if str(c).strip()]

        reason = str(data.get("reason", "")).strip()
        references = data.get("references", []) or []
        if not isinstance(references, list):
            references = [str(references)]
        references = [str(r).strip() for r in references if str(r).strip()]

        return ChapterPlan(
            chapter_num=chapter_num,
            beat=beat,
            emotion=emotion,
            chapter_type=chapter_type,
            characters=characters,
            reason=reason,
            references=references,
            raw_response=raw,
        )
