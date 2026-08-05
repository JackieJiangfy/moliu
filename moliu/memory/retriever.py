"""分层检索 — 精确加载 + 向量检索 + 结构化查询"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from moliu.config import Config
from moliu.data.schemas import CharacterCard, NarratorCard, WorldSetting
from moliu.memory.store import MemoryStore


@dataclass
class ChapterContext:
    """组装好的章节上下文"""
    world_setting: str = ""
    narrator_context: str = ""
    narrator_card: NarratorCard | None = None
    character_cards: list[CharacterCard] = field(default_factory=list)
    recent_chapters_text: str = ""
    last_emotion: str = "轻松"
    last_300_words: str = ""
    related_summaries: list[str] = field(default_factory=list)
    related_notes: list[str] = field(default_factory=list)
    active_plot_threads: list[dict] = field(default_factory=list)
    banned_phrases: list[str] = field(default_factory=list)


class Retriever:
    """分层检索上下文组装器"""

    def __init__(self, config: Config, memory: MemoryStore):
        self.config = config
        self.memory = memory

    def assemble(
        self,
        chapter_num: int,
        beat: str,
        characters: list[CharacterCard],
        world: WorldSetting,
        narrator: NarratorCard | None = None,
        narrator_guide: str = "",
        recent_chapters: str = "",
        last_emotion: str = "轻松",
    ) -> ChapterContext:
        ctx = ChapterContext()

        # 第一层: 精确加载
        ctx.world_setting = world.to_context()
        ctx.character_cards = characters

        if narrator:
            ctx.narrator_context = narrator.to_context()
            ctx.narrator_card = narrator
            ctx.banned_phrases = list(narrator.banned_phrases)
        elif narrator_guide:
            ctx.narrator_context = narrator_guide

        ctx.last_emotion = last_emotion

        # 上一章最后 300 字（从文件读取）
        ctx.last_300_words = self._load_last_300_words(chapter_num)

        # 前文回顾
        if recent_chapters:
            ctx.recent_chapters_text = recent_chapters
        else:
            ctx.recent_chapters_text = self._load_recent_from_meta(chapter_num)

        # 第二层: 向量检索（RAG）
        if self.memory.chapter_count() > 0:
            ctx.related_summaries = self.memory.query_summaries(beat, n=5)
            ctx.related_notes = self.memory.query_notes(beat, n=5)

        # 第三层: 结构化查询
        ctx.active_plot_threads = self.memory.get_active_plot_threads()

        return ctx

    def _load_last_300_words(self, chapter_num: int) -> str:
        if chapter_num <= 1:
            return ""
        output_dir = self.config.resolve_output_dir()
        prev_chapter = output_dir / f"第{chapter_num - 1}章" / "正文.md"
        if prev_chapter.exists():
            text = prev_chapter.read_text(encoding="utf-8")
            return text[-300:] if len(text) > 300 else text
        return ""

    def _load_recent_from_meta(self, chapter_num: int) -> str:
        """从 meta.json 加载最近几章的摘要"""
        if chapter_num <= 1:
            return ""
        output_dir = self.config.resolve_output_dir()
        summaries = []
        for n in range(max(1, chapter_num - 3), chapter_num):
            meta_path = output_dir / f"第{n}章" / "meta.json"
            if meta_path.exists():
                try:
                    from moliu.data.schemas import ChapterMeta
                    meta = ChapterMeta.from_json(meta_path)
                    summaries.append(meta.to_context())
                except Exception:
                    pass
        return "\n\n".join(summaries)
