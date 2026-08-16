"""分层记忆系统 — 支撑长篇小说(500+ 章)的核心记忆基础设施

三层记忆结构,与现有 assembler 协同工作:

1. 短期记忆 (Short-term)
   - 最近 3 章原文,复用 assembler._load_recent_full
   - 上一章最后 300 字,复用 assembler._load_last_300_words

2. 中期记忆 (Mid-term) — 阶段摘要
   - 每 N 章自动生成阶段摘要 (默认 10 章一个阶段)
   - 装配时加载最近 3 个阶段的摘要 (约 30 章的浓缩记忆)
   - 解决"第 200 章看不到第 50 章"的问题

3. 长期记忆 (Long-term) — Story Bible
   - 全书累积式知识库,主要包含:
     * 已发生关键事件 (key_events)
     * 角色关系演化 (谁帮过谁、谁背叛谁)
     * 已确立的世界观事实 (地理、势力、规则)
     * 未解的悬念和承诺
   - 每章生成后增量更新,装配时全量注入(控制长度)

数据存储位置:
- data/novels/{id}/memory/arc_summaries.jsonl    # 阶段摘要(追加式)
- data/novels/{id}/memory/story_bible.json       # Story Bible(覆盖式)

设计原则:
- 失败优雅降级,不阻断章节生成
- LLM 不可用时回退到启发式摘要
- 长度受控,不影响生成 token 预算
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from moliu.config import Config
from moliu.data.schemas import ChapterMeta

logger = logging.getLogger(__name__)


# === 配置常量 ===

ARC_SIZE = 10                  # 每多少章生成一个阶段摘要
ARC_HISTORY_LOAD = 3           # 装配时加载最近几个阶段摘要
BIBLE_MAX_EVENTS = 80          # Story Bible 关键事件最大保留数
BIBLE_MAX_FACTS = 40           # Story Bible 世界观事实最大保留数
BIBLE_MAX_PROMISES = 30        # Story Bible 未解悬念最大保留数
BIBLE_MAX_CHARS = 12000        # Story Bible 注入 prompt 时的字符上限


@dataclass
class ArcSummary:
    """阶段摘要 — 一个阶段(约 10 章)的浓缩记忆"""
    arc_id: int                         # 第几个阶段,从 1 开始
    chapter_start: int
    chapter_end: int
    summary: str = ""                   # LLM 生成的阶段总结
    key_events: list[str] = field(default_factory=list)   # 阶段内关键事件
    character_changes: list[str] = field(default_factory=list)  # 角色状态变化
    open_threads: list[str] = field(default_factory=list)       # 阶段结束时未解决的线
    created_at: str = ""
    chapter_count: int = 0               # 实际包含章节数

    def to_dict(self) -> dict[str, Any]:
        return {
            "arc_id": self.arc_id,
            "chapter_start": self.chapter_start,
            "chapter_end": self.chapter_end,
            "summary": self.summary,
            "key_events": self.key_events,
            "character_changes": self.character_changes,
            "open_threads": self.open_threads,
            "created_at": self.created_at,
            "chapter_count": self.chapter_count,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ArcSummary":
        return cls(
            arc_id=int(d.get("arc_id", 0)),
            chapter_start=int(d.get("chapter_start", 0)),
            chapter_end=int(d.get("chapter_end", 0)),
            summary=str(d.get("summary", "")),
            key_events=list(d.get("key_events", [])),
            character_changes=list(d.get("character_changes", [])),
            open_threads=list(d.get("open_threads", [])),
            created_at=str(d.get("created_at", "")),
            chapter_count=int(d.get("chapter_count", 0)),
        )


@dataclass
class StoryBible:
    """全书累积式知识库

    设计为幂等可重建 — 从所有已生成章节的 meta.json 可重新构建。
    每章生成后增量更新即可,不需要每次全量重建。
    """
    novel_id: int
    # 已发生的关键事件 (按时间序,旧的可被新事件取代)
    key_events: list[str] = field(default_factory=list)
    # 已确立的世界观事实 (地理/势力/规则等)
    world_facts: list[str] = field(default_factory=list)
    # 未解决的悬念和承诺 (与伏笔表互补,这里存"人物承诺/剧情线")
    open_promises: list[str] = field(default_factory=list)
    # 角色关系演化历史 (累积式,不覆盖)
    character_relations: list[str] = field(default_factory=list)
    last_updated_chapter: int = 0
    last_updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "novel_id": self.novel_id,
            "key_events": self.key_events,
            "world_facts": self.world_facts,
            "open_promises": self.open_promises,
            "character_relations": self.character_relations,
            "last_updated_chapter": self.last_updated_chapter,
            "last_updated_at": self.last_updated_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "StoryBible":
        return cls(
            novel_id=int(d.get("novel_id", 0)),
            key_events=list(d.get("key_events", [])),
            world_facts=list(d.get("world_facts", [])),
            open_promises=list(d.get("open_promises", [])),
            character_relations=list(d.get("character_relations", [])),
            last_updated_chapter=int(d.get("last_updated_chapter", 0)),
            last_updated_at=str(d.get("last_updated_at", "")),
        )

    def to_context(self) -> str:
        """渲染为 prompt 可注入的上下文块

        长度受控,超长时自动裁剪保留最近的内容。
        """
        if not any([self.key_events, self.world_facts, self.open_promises, self.character_relations]):
            return ""

        sections: list[str] = []

        if self.world_facts:
            sections.append("【世界观已确立事实】\n" + "\n".join(f"· {f}" for f in self.world_facts[-BIBLE_MAX_FACTS:]))

        if self.key_events:
            events = self.key_events[-BIBLE_MAX_EVENTS:]
            sections.append("【已发生关键事件】\n" + "\n".join(f"· {e}" for e in events))

        if self.character_relations:
            sections.append("【角色关系演化】\n" + "\n".join(f"· {r}" for r in self.character_relations[-30:]))

        if self.open_promises:
            sections.append("【未解悬念/承诺】\n" + "\n".join(f"· {p}" for p in self.open_promises[-BIBLE_MAX_PROMISES:]))

        text = "\n\n".join(sections)

        # 超长裁剪 — 保留前面(世界观)和后面(最新事件)
        if len(text) > BIBLE_MAX_CHARS:
            keep_tail = int(BIBLE_MAX_CHARS * 0.7)
            text = "[Story Bible 已裁剪]\n" + text[-keep_tail:]
            logger.info("Story Bible 超长(%d 字符),裁剪到 %d", len(text), BIBLE_MAX_CHARS)

        return text


# === LLM 生成阶段摘要的 Prompt ===

ARC_SUMMARY_SYSTEM = """你是小说编辑助手,擅长把多章节浓缩成结构化阶段总结。
你将从若干章节的元数据中提炼出阶段摘要,供后续章节生成时回顾前文。

输出严格按以下格式(每节用【】标记):

【阶段总结】
(2-3 句话总结这个阶段发生了什么、推进了什么剧情线)

【关键事件】
1. ...
2. ...
(3-6 条最重要的事件,按时间序)

【角色变化】
1. 角色名 — 从X变为Y (因为...)
(只记录有显著变化的,无关紧要不写)

【未决线索】
1. ...
(本阶段结束时仍未解决的问题、承诺、悬念)

要点:
- 用第三人称,客观陈述
- 避免细节描写,只记关键信息
- 每条不超过 40 字
"""

ARC_SUMMARY_USER = """以下是第 {start} 到第 {end} 章的元数据:

{chapters_meta}

请按格式生成阶段摘要。"""


class LayeredMemory:
    """分层记忆管理器 — 协调短期/中期/长期记忆

    使用方式:
        memory = LayeredMemory(config, novel_id=1)
        # 装配上下文时
        context = memory.assemble_for_chapter(chapter_num)
        # 章节生成后
        memory.update_after_chapter(chapter_num, chapter_meta, content)
    """

    def __init__(self, config: Config, novel_id: int = 1, gateway=None):
        self.config = config
        self.novel_id = novel_id
        self.gateway = gateway  # 可选,用于 LLM 生成阶段摘要
        self._data_dir = config.resolve_data_dir(novel_id) / "memory"
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._arc_file = self._data_dir / "arc_summaries.jsonl"
        self._bible_file = self._data_dir / "story_bible.json"

    # === 中期记忆:阶段摘要 ===

    def load_arc_summaries(self) -> list[ArcSummary]:
        """加载全部阶段摘要"""
        if not self._arc_file.exists():
            return []
        result: list[ArcSummary] = []
        try:
            with open(self._arc_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        result.append(ArcSummary.from_dict(json.loads(line)))
                    except (json.JSONDecodeError, KeyError):
                        continue
        except OSError as e:
            logger.warning("读取阶段摘要失败: %s", e)
        return result

    def load_recent_arcs(self, chapter_num: int, count: int = ARC_HISTORY_LOAD) -> list[ArcSummary]:
        """加载影响当前章节的最近几个阶段摘要

        只返回 chapter_end < chapter_num 的阶段。
        """
        arcs = self.load_arc_summaries()
        relevant = [a for a in arcs if a.chapter_end < chapter_num]
        return relevant[-count:] if relevant else []

    async def generate_arc_summary(self, arc_id: int, chapter_start: int, chapter_end: int) -> ArcSummary:
        """为一个阶段生成摘要

        优先用 LLM,失败时回退到启发式。
        """
        # 收集阶段内所有章节的 meta
        chapters_meta = self._collect_chapter_metas(chapter_start, chapter_end)
        if not chapters_meta:
            logger.warning("阶段 %d (章 %d-%d) 无章节元数据,跳过", arc_id, chapter_start, chapter_end)
            return ArcSummary(
                arc_id=arc_id,
                chapter_start=chapter_start,
                chapter_end=chapter_end,
                created_at=datetime.now(timezone.utc).isoformat(),
                chapter_count=0,
            )

        # 尝试 LLM 生成
        summary_text = ""
        key_events: list[str] = []
        character_changes: list[str] = []
        open_threads: list[str] = []

        if self.gateway:
            try:
                meta_text = self._format_chapter_metas(chapters_meta)
                user_prompt = ARC_SUMMARY_USER.format(
                    start=chapter_start,
                    end=chapter_end,
                    chapters_meta=meta_text,
                )
                result, _ = await self.gateway.generate(
                    system_prompt=ARC_SUMMARY_SYSTEM,
                    user_prompt=user_prompt,
                    temperature=0.2,
                    max_tokens=1024,
                )
                summary_text, key_events, character_changes, open_threads = self._parse_arc_llm_output(result)
            except Exception as e:
                logger.warning("LLM 生成阶段摘要失败,回退到启发式: %s", e)

        # 启发式回退 — 从 meta 直接提取
        if not summary_text:
            summary_text, key_events, character_changes, open_threads = self._heuristic_arc_summary(chapters_meta)

        arc = ArcSummary(
            arc_id=arc_id,
            chapter_start=chapter_start,
            chapter_end=chapter_end,
            summary=summary_text,
            key_events=key_events,
            character_changes=character_changes,
            open_threads=open_threads,
            created_at=datetime.now(timezone.utc).isoformat(),
            chapter_count=len(chapters_meta),
        )
        self._save_arc_summary(arc)
        return arc

    def _collect_chapter_metas(self, start: int, end: int) -> list[ChapterMeta]:
        """收集章节范围内的 meta.json"""
        output_dir = self.config.resolve_output_dir(self.novel_id)
        metas: list[ChapterMeta] = []
        for num in range(start, end + 1):
            meta_path = output_dir / Config.chapter_dir_name(num) / "meta.json"
            if meta_path.exists():
                try:
                    metas.append(ChapterMeta.from_json(meta_path))
                except Exception:
                    continue
        return metas

    @staticmethod
    def _format_chapter_metas(metas: list[ChapterMeta]) -> str:
        """格式化章节元数据供 LLM 阅读"""
        parts: list[str] = []
        for m in metas:
            line = f"第{m.chapter_num}章"
            if m.title:
                line += f"《{m.title}》"
            if m.summary:
                line += f" — {m.summary}"
            if m.key_events:
                line += f" | 事件: {'; '.join(m.key_events[:3])}"
            if m.key_characters:
                line += f" | 角色: {', '.join(m.key_characters[:5])}"
            if m.emotion:
                line += f" | 情绪: {m.emotion}"
            parts.append(line)
        return "\n".join(parts)

    @staticmethod
    def _parse_arc_llm_output(text: str) -> tuple[str, list[str], list[str], list[str]]:
        """解析 LLM 输出的阶段摘要(容错解析)"""
        summary = ""
        key_events: list[str] = []
        character_changes: list[str] = []
        open_threads: list[str] = []

        # 用【】分段
        sections = re.split(r"【[^】]+】", text)
        headers = re.findall(r"【([^】]+)】", text)

        for i, h in enumerate(headers):
            body = sections[i + 1].strip() if i + 1 < len(sections) else ""
            if "总结" in h:
                summary = body.strip()
            elif "事件" in h:
                for line in body.split("\n"):
                    line = re.sub(r"^[\d.\-*]+\s*", "", line.strip())
                    if line and len(line) > 3:
                        key_events.append(line)
            elif "角色" in h or "变化" in h:
                for line in body.split("\n"):
                    line = re.sub(r"^[\d.\-*]+\s*", "", line.strip())
                    if line and len(line) > 3:
                        character_changes.append(line)
            elif "线索" in h or "未决" in h or "悬念" in h:
                for line in body.split("\n"):
                    line = re.sub(r"^[\d.\-*]+\s*", "", line.strip())
                    if line and len(line) > 3:
                        open_threads.append(line)

        return summary, key_events, character_changes, open_threads

    @staticmethod
    def _heuristic_arc_summary(metas: list[ChapterMeta]) -> tuple[str, list[str], list[str], list[str]]:
        """无 LLM 时的启发式摘要 — 从 meta 直接拼"""
        if not metas:
            return "", [], [], []
        first, last = metas[0], metas[-1]
        summary = f"第{first.chapter_num}-{last.chapter_num}章,共{len(metas)}章。"
        if first.summary and last.summary:
            summary += f" 开始于:{first.summary[:50]}。 结束于:{last.summary[:50]}。"

        key_events: list[str] = []
        for m in metas:
            key_events.extend(m.key_events[:2])
        # 去重保序
        seen = set()
        unique_events = []
        for e in key_events:
            if e not in seen:
                seen.add(e)
                unique_events.append(e)

        # 角色变化 — 提取每章出场角色
        chars: dict[str, list[int]] = {}
        for m in metas:
            for name in m.key_characters:
                chars.setdefault(name, []).append(m.chapter_num)
        char_changes = [
            f"{name} 出现于第{min(chs)}-{max(chs)}章(共{len(chs)}章)"
            for name, chs in chars.items()
            if len(chs) >= 2
        ][:5]

        return summary, unique_events[:6], char_changes, []

    def _save_arc_summary(self, arc: ArcSummary) -> None:
        """追加保存阶段摘要(同 arc_id 则替换)"""
        existing = self.load_arc_summaries()
        existing = [a for a in existing if a.arc_id != arc.arc_id]
        existing.append(arc)
        existing.sort(key=lambda a: a.arc_id)
        try:
            with open(self._arc_file, "w", encoding="utf-8") as f:
                for a in existing:
                    f.write(json.dumps(a.to_dict(), ensure_ascii=False) + "\n")
        except OSError as e:
            logger.error("保存阶段摘要失败: %s", e)

    def maybe_generate_arc_for_chapter(self, chapter_num: int) -> ArcSummary | None:
        """检查是否需要为刚完成的章节生成阶段摘要

        章节号是 ARC_SIZE 的倍数时触发(如第 10、20、30 章)。
        返回生成的 ArcSummary 或 None(未触发)。
        """
        if chapter_num <= 0 or chapter_num % ARC_SIZE != 0:
            return None
        arc_id = chapter_num // ARC_SIZE
        existing = self.load_arc_summaries()
        # 已存在则跳过(幂等)
        if any(a.arc_id == arc_id for a in existing):
            return None
        # 同步调用(无 LLM 时),LLM 版本由 pipeline 异步调用
        if self.gateway is None:
            # 启发式直接生成
            return self._sync_generate_arc(arc_id, chapter_num - ARC_SIZE + 1, chapter_num)
        return None  # pipeline 应该调 async 版本

    def _sync_generate_arc(self, arc_id: int, start: int, end: int) -> ArcSummary:
        """同步生成(启发式)"""
        metas = self._collect_chapter_metas(start, end)
        summary, key_events, char_changes, open_threads = self._heuristic_arc_summary(metas)
        arc = ArcSummary(
            arc_id=arc_id,
            chapter_start=start,
            chapter_end=end,
            summary=summary,
            key_events=key_events,
            character_changes=char_changes,
            open_threads=open_threads,
            created_at=datetime.now(timezone.utc).isoformat(),
            chapter_count=len(metas),
        )
        self._save_arc_summary(arc)
        return arc

    # === 长期记忆:Story Bible ===

    def load_bible(self) -> StoryBible:
        """加载 Story Bible"""
        if not self._bible_file.exists():
            return StoryBible(novel_id=self.novel_id)
        try:
            with open(self._bible_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return StoryBible.from_dict(data)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("加载 Story Bible 失败,使用空 bible: %s", e)
            return StoryBible(novel_id=self.novel_id)

    def save_bible(self, bible: StoryBible) -> None:
        """保存 Story Bible"""
        try:
            with open(self._bible_file, "w", encoding="utf-8") as f:
                json.dump(bible.to_dict(), f, ensure_ascii=False, indent=2)
        except OSError as e:
            logger.error("保存 Story Bible 失败: %s", e)

    def update_bible_after_chapter(
        self,
        chapter_num: int,
        chapter_meta: ChapterMeta,
        content: str = "",
    ) -> StoryBible:
        """章节生成后增量更新 Story Bible

        策略:
        - key_events: 从 meta.key_events 追加(去重)
        - world_facts: 不自动提取(需要人工或后续 LLM 提取)
        - open_promises: 不自动提取(由伏笔表管理)
        - character_relations: 不自动提取(由关系图谱管理)

        保持简单 — 只追加 key_events,其他由专门模块负责。
        """
        bible = self.load_bible()

        # 增量更新 key_events
        if chapter_meta.key_events:
            prefix = f"[第{chapter_num}章] "
            for event in chapter_meta.key_events:
                event_text = f"{prefix}{event}"
                if event_text not in bible.key_events:
                    bible.key_events.append(event_text)

        # 裁剪 — 超出上限时丢弃最旧的
        if len(bible.key_events) > BIBLE_MAX_EVENTS * 2:
            bible.key_events = bible.key_events[-BIBLE_MAX_EVENTS:]

        bible.last_updated_chapter = chapter_num
        bible.last_updated_at = datetime.now(timezone.utc).isoformat()
        self.save_bible(bible)
        return bible

    def rebuild_bible_from_history(self) -> StoryBible:
        """从所有已生成章节的 meta.json 重建 Story Bible

        用于:
        - 首次启用分层记忆时,回填历史数据
        - Story Bible 损坏时重建
        """
        bible = StoryBible(novel_id=self.novel_id)
        output_dir = self.config.resolve_output_dir(self.novel_id)
        if not output_dir.exists():
            return bible

        # 找到所有章节目录
        chapter_dirs = []
        for d in output_dir.iterdir():
            if d.is_dir():
                num = Config.parse_chapter_num(d.name)
                if num is not None:
                    chapter_dirs.append((num, d))
        chapter_dirs.sort(key=lambda x: x[0])

        for num, d in chapter_dirs:
            meta_path = d / "meta.json"
            if meta_path.exists():
                try:
                    meta = ChapterMeta.from_json(meta_path)
                    if meta.key_events:
                        prefix = f"[第{num}章] "
                        for event in meta.key_events:
                            bible.key_events.append(f"{prefix}{event}")
                except Exception:
                    continue

        # 去重
        seen: set[str] = set()
        unique: list[str] = []
        for e in bible.key_events:
            if e not in seen:
                seen.add(e)
                unique.append(e)
        bible.key_events = unique[-BIBLE_MAX_EVENTS * 2:]

        bible.last_updated_chapter = chapter_dirs[-1][0] if chapter_dirs else 0
        bible.last_updated_at = datetime.now(timezone.utc).isoformat()
        self.save_bible(bible)
        logger.info("Story Bible 重建完成: %d 个关键事件", len(bible.key_events))
        return bible

    # === 统一装配接口 ===

    def assemble_for_chapter(self, chapter_num: int) -> str:
        """为章节生成装配分层记忆上下文

        返回可直接注入 prompt 的字符串块。
        不包含短期记忆(由 assembler 负责),只包含中期+长期。
        """
        parts: list[str] = []

        # 中期:最近几个阶段摘要
        recent_arcs = self.load_recent_arcs(chapter_num)
        if recent_arcs:
            arc_text = self._format_arcs_for_prompt(recent_arcs)
            if arc_text:
                parts.append(arc_text)

        # 长期:Story Bible
        bible = self.load_bible()
        bible_text = bible.to_context()
        if bible_text:
            parts.append("【Story Bible — 全书累积记忆】\n" + bible_text)

        return "\n\n".join(parts) if parts else ""

    @staticmethod
    def _format_arcs_for_prompt(arcs: list[ArcSummary]) -> str:
        """格式化阶段摘要供 prompt 注入"""
        if not arcs:
            return ""
        lines = ["【前文阶段摘要 — 中期记忆】"]
        for arc in arcs:
            lines.append(f"\n--- 阶段{arc.arc_id} (第{arc.chapter_start}-{arc.chapter_end}章) ---")
            if arc.summary:
                lines.append(arc.summary)
            if arc.key_events:
                lines.append("关键事件:")
                for e in arc.key_events[:5]:
                    lines.append(f"  · {e}")
            if arc.character_changes:
                lines.append("角色变化:")
                for c in arc.character_changes[:3]:
                    lines.append(f"  · {c}")
            if arc.open_threads:
                lines.append("未决线索:")
                for t in arc.open_threads[:3]:
                    lines.append(f"  · {t}")
        return "\n".join(lines)
