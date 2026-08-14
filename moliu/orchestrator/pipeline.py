"""章节生成编排层 — 生成 + RAG + 检查 + 评估"""

from __future__ import annotations

import datetime
from pathlib import Path

from moliu.config import Config
from moliu.data.schemas import (
    ChapterMeta, ChapterResult, CharacterCard, NarratorCard, WorldSetting,
)
from moliu.engines.checker import AnchoredPreChecker, ConsistencyChecker
from moliu.engines.gateway import DeepSeekGateway
from moliu.engines.generator import Generator, count_words
from moliu.engines.reader_eval import ReaderEvaluator
from moliu.memory.retriever import Retriever
from moliu.memory.store import MemoryStore
from moliu.prompts.manager import PromptManager
from moliu.rules.rhythm_tracker import RhythmRecord, RhythmTracker, TensionScorer


class QualityReport:
    """一次章节生成后的完整质检报告"""

    def __init__(self):
        self.pre_check_passed: bool = True
        self.pre_check_text: str = ""
        self.consistency: str = ""
        self.consistency_fatal: int = 0
        self.consistency_warn: int = 0
        self.reader_feedback: str = ""
        self.reader_want_next: bool = True
        self.reader_repetitive: bool = False
        self.rhythm_alerts: list[str] = []
        self.tension_score: int = 5

    def can_advance(self) -> bool:
        """是否可以推进到下一章 (fatal=0)"""
        return self.consistency_fatal == 0

    def summary(self) -> str:
        lines = ["=== 质量报告 ==="]
        if self.pre_check_passed:
            lines.append("[OK] 锚点预检通过")
        else:
            lines.append(f"[WARN] 锚点预检: {self.pre_check_text[:80]}")
        if self.consistency_fatal == 0 and self.consistency_warn == 0:
            lines.append("[OK] 一致性检查通过")
        else:
            lines.append(f"一致性: {self.consistency_fatal}致命 {self.consistency_warn}警告")
        lines.append(f"读者: {'想继续' if self.reader_want_next else '不想继续'}")
        if self.reader_repetitive:
            lines.append("[WARN] 读者感觉与上一章重复")
        lines.append(f"张力: {self.tension_score}/10")
        if self.rhythm_alerts:
            for a in self.rhythm_alerts:
                lines.append(f"[WARN] 节奏: {a}")
        return "\n".join(lines)


class ChapterPipeline:
    """完整的章节生成管线：上下文组装 → 预检 → 生成 → 检查 → 评估 → 记忆存储"""

    def __init__(
        self,
        config: Config,
        gateway: DeepSeekGateway,
        prompts: PromptManager,
        *,
        memory: MemoryStore | None = None,
        retriever: Retriever | None = None,
        checker: ConsistencyChecker | None = None,
        prechecker: AnchoredPreChecker | None = None,
        reader: ReaderEvaluator | None = None,
        tracker: RhythmTracker | None = None,
        novel_id: int = 1,
    ):
        self.config = config
        self.novel_id = novel_id
        self.gateway = gateway
        self.generator = Generator(config, gateway, prompts, novel_id=novel_id)
        self.memory = memory
        self.retriever = retriever
        self.checker = checker
        self.prechecker = prechecker
        self.reader = reader
        self.tracker = tracker

    async def run_quality_checks(
        self,
        result: ChapterResult,
        beat: str,
        characters: list[CharacterCard],
        world: WorldSetting,
        narrator: NarratorCard | None = None,
        chapter_num: int | None = None,
    ) -> QualityReport:
        """运行所有质量检查（生成后调用）"""
        qr = QualityReport()

        # 一致性检查
        if self.checker:
            report = await self.checker.check(
                result.content, characters, world, narrator,
                chapter_num=chapter_num,
            )
            qr.consistency = report.to_text()
            qr.consistency_fatal = report.fatal_count
            qr.consistency_warn = report.warning_count

        # 读者评估
        if self.reader:
            fb = await self.reader.evaluate(result.content, chapter_num=chapter_num)
            qr.reader_feedback = fb.summary()
            qr.reader_want_next = fb.want_next
            qr.reader_repetitive = fb.feels_repetitive

        # 张力评分
        qr.tension_score = TensionScorer.score(result.content)

        return qr

    async def run_pre_check(
        self, beat: str, characters: list[CharacterCard],
        chapter_num: int | None = None,
    ) -> tuple[bool, str]:
        """锚点预检（生成前调用）"""
        if self.prechecker:
            return await self.prechecker.check(beat, characters, chapter_num=chapter_num)
        return True, "预检未启用"

    def save_rhythm_record(
        self,
        chapter_num: int,
        result: ChapterResult,
        qr: QualityReport,
        chapter_type: str,
        emotion: str,
    ) -> None:
        """保存节奏追踪数据"""
        if not self.tracker:
            return

        content = result.content
        record = RhythmRecord(
            chapter_num=chapter_num,
            chapter_type=chapter_type,
            tension_score=qr.tension_score,
            opening_style=TensionScorer.detect_opening(content),
            closing_style=TensionScorer.detect_closing(content),
            dialogue_ratio=TensionScorer.dialogue_ratio(content),
            word_count=result.word_count,
            has_memorable_moment=qr.reader_want_next and not qr.reader_repetitive,
            emotion_tag=emotion,
        )
        self.tracker.record(record)

        # 输出节奏告警
        alerts = self.tracker.check_variety()
        qr.rhythm_alerts = alerts

    async def run_with_retry(
        self,
        *,
        generate_fn,
        quality_fn,
        max_retries: int = 1,
        retry_on: tuple[str, ...] = ("fatal",),
    ) -> tuple[ChapterResult, QualityReport]:
        """生成 + 质检,不达标自动重试

        Args:
            generate_fn: 无参 async callable,返回 ChapterResult
            quality_fn: async callable(result) -> QualityReport
            max_retries: 最多重试次数(默认 1,即最多生成 2 次)
            retry_on: 触发重试的条件
                      - "fatal"  一致性致命问题(默认)
                      - "reader" 读者明确不想继续
                      - "tension_low"  张力 < 4
                      - "repetitive"  读者感觉重复

        Returns:
            (result, qr) 最终结果 + 质检报告(最后一次)
        """
        import logging
        log = logging.getLogger(__name__)

        result = await generate_fn()
        qr = await quality_fn(result)

        for attempt in range(max_retries):
            should_retry = False
            reasons: list[str] = []

            if "fatal" in retry_on and qr.consistency_fatal > 0:
                should_retry = True
                reasons.append(f"{qr.consistency_fatal} 个致命问题")
            if "reader" in retry_on and not qr.reader_want_next:
                should_retry = True
                reasons.append("读者不想继续")
            if "tension_low" in retry_on and qr.tension_score < 4:
                should_retry = True
                reasons.append(f"张力 {qr.tension_score}/10")
            if "repetitive" in retry_on and qr.reader_repetitive:
                should_retry = True
                reasons.append("读者感觉重复")

            if not should_retry:
                break

            log.warning(
                "第 %d 次重试: %s",
                attempt + 1, "; ".join(reasons),
            )
            result = await generate_fn()
            qr = await quality_fn(result)

        return result, qr

    def save_to_memory(
        self,
        chapter_num: int,
        result: ChapterResult,
        summary: str,
        emotion: str,
        characters: list[CharacterCard],
    ) -> None:
        """保存到 ChromaDB 长期记忆"""
        if not self.memory:
            return

        char_names = [c.name for c in characters]
        self.memory.add_summary(chapter_num, summary, emotion, char_names)

    def save_meta(
        self,
        chapter_num: int,
        result: ChapterResult,
        qr: QualityReport,
        summary: str,
        emotion: str,
        characters: list[CharacterCard],
    ) -> None:
        """保存 meta.json + 版本管理 + 角色状态更新"""
        # 使用 Generator 的版本管理（含角色备份+状态更新）
        self.generator.save_chapter(result, emotion=emotion, summary=summary, characters=characters)

        # 额外保存质检报告（save_chapter 不写这些）
        output_dir = self.config.resolve_output_dir(self.novel_id) / Config.chapter_dir_name(chapter_num)
        (output_dir / "质量报告.md").write_text(qr.summary(), encoding="utf-8")
        if qr.consistency:
            (output_dir / "一致性检查.md").write_text(qr.consistency, encoding="utf-8")
