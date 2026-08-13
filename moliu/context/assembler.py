"""结构化上下文组装 — 作家思维：大纲 + 人物表 + 伏笔 + 图谱 + 最近稿子"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from moliu.config import Config
from moliu.data.schemas import CharacterCard, NarratorCard, WorldSetting

logger = logging.getLogger(__name__)

# 伏笔年龄阈值
FORESHADOW_AGE_HIGH = 15    # 高优先级伏笔超过此年龄触发提醒
FORESHADOW_AGE_NORMAL = 25   # 普通伏笔超过此年龄触发提醒
FORESHADOW_AGE_CRITICAL = 40  # 任意伏笔超过此年龄强制提醒
MAX_RECENT_WORDS = 10000      # 最近章节原文最大加载字数
ARC_SNIPPET_RADIUS = 300      # 弧方向上下文窗口半径（字符）


@dataclass
class StructuredContext:
    """组装后的章节上下文——只含 AI 此刻该知道的"""
    world_setting: str = ""
    narrator_context: str = ""
    banned_phrases: list[str] = field(default_factory=list)
    arc_direction: str = ""
    character_snapshots: str = ""
    graph_insights: str = ""        # 图谱反向注入的智能提示
    due_foreshadows: str = ""
    constraints: str = ""
    recent_chapters_full: str = ""
    last_emotion: str = "轻松"
    last_300_words: str = ""

    def to_prompt_context(self) -> str:
        """渲染为可注入的上下文块"""
        sections = [
            ("arc_direction", "【当前故事方向】"),
            ("character_snapshots", "【出场角色当前状态】"),
            ("graph_insights", "【图谱智能提示】"),
            ("constraints", "【本章约束：不可出现】"),
            ("due_foreshadows", "【本章可能需要回收的伏笔】"),
            ("recent_chapters_full", "【前文章节原文】"),
            ("last_300_words", "【上一章收尾原文】"),
        ]
        parts = []
        for attr, header in sections:
            value = getattr(self, attr, "")
            if value:
                parts.append(f"{header}\n{value}")
        return "\n\n".join(parts)


class StructuredAssembler:
    """作家的上下文组装：精确查询，不语义检索"""

    def __init__(self, config: Config):
        self.config = config
        self._cache: dict[str, str] = {}  # path → content

    def _read_cached(self, path: Path) -> str | None:
        key = str(path)
        if key in self._cache:
            return self._cache[key]
        if path.exists():
            content = path.read_text(encoding="utf-8")
            self._cache[key] = content
            return content
        return None

    def _invalidate_cache(self) -> None:
        self._cache.clear()

    async def assemble(
        self,
        chapter_num: int,
        beat: str,
        characters: list[CharacterCard],
        world: WorldSetting,
        narrator: NarratorCard | None = None,
        narrator_guide: str = "",
        last_emotion: str = "轻松",
        recent_override: str = "",
    ) -> StructuredContext:
        ctx = StructuredContext()

        ctx.world_setting = world.to_context()

        if narrator:
            ctx.narrator_context = narrator.to_context()
            ctx.banned_phrases = list(narrator.banned_phrases)
        elif narrator_guide:
            ctx.narrator_context = narrator_guide

        ctx.last_emotion = last_emotion
        ctx.arc_direction = self._load_arc_direction(chapter_num)
        ctx.character_snapshots = self._load_character_snapshots(characters)
        ctx.due_foreshadows = self._load_due_foreshadows(chapter_num)
        ctx.constraints = self._load_constraints(characters, world, narrator)

        if recent_override:
            ctx.recent_chapters_full = recent_override
        else:
            ctx.recent_chapters_full = self._load_recent_full(chapter_num)

        ctx.last_300_words = self._load_last_300_words(chapter_num)

        # 图谱反向注入（墨脉图）
        ctx.graph_insights = await self.inject_graph_context(chapter_num, characters)

        return ctx

    # === arc direction ===

    _CHAPTER_RE = re.compile(r"(?:^|\n)\s*第\s*(\d+)\s*章\s*[:：\s]")

    def _load_arc_direction(self, chapter_num: int) -> str:
        """从大纲文件读取当前弧的方向。用正则以行首章号匹配，避免误匹配注释/对话。"""
        outlines_dir = self.config.resolve_data_dir() / "outlines"
        if not outlines_dir.exists():
            logger.info("大纲目录 %s 不存在，跳过弧方向", outlines_dir)
            return ""

        for f in sorted(outlines_dir.glob("*.yaml")):
            try:
                text = self._read_cached(f)
                if text is None:
                    continue
                # 正则匹配行首 "第N章" 或 "第N章:标题"
                for m in self._CHAPTER_RE.finditer(text):
                    if int(m.group(1)) == chapter_num:
                        idx = m.start()
                        start = max(0, idx - ARC_SNIPPET_RADIUS)
                        end = min(len(text), idx + ARC_SNIPPET_RADIUS + 200)
                        snippet = text[start:end].strip()

                        # 检测弧边界：往前找最近的 "##" 或 "卷" 标记
                        before = text[max(0, idx - 2000):idx]
                        arc_header = ""
                        for marker in ["### ", "## ", "卷", "阶段"]:
                            pos = before.rfind(marker)
                            if pos > 0:
                                arc_line = before[pos:].split("\n")[0].strip()
                                arc_header = f"所属阶段: {arc_line}\n"
                                break

                        if arc_header:
                            snippet = arc_header + snippet
                        return snippet

            except Exception:
                logger.warning("读取大纲文件 %s 失败", f, exc_info=True)
                continue

        # 回退：找不到精确章号时，尝试根据章节号推算所在弧段
        return self._fallback_arc_direction(chapter_num)

    def _fallback_arc_direction(self, chapter_num: int) -> str:
        """无精确大纲时的回退方向"""
        if chapter_num <= 3:
            return "故事开篇阶段。建立世界观、介绍主要角色、埋下核心伏笔。"
        arcs = [
            (30, "故事第一阶段（约第1-30章）。主角获得能力/系统的初期，探索规则，建立初期人际关系。"),
            (60, "故事第二阶段（约第31-60章）。冲突升级，反派出现，角色关系复杂化，核心秘密开始揭露线索。"),
            (90, "故事第三阶段（约第61-90章）。高潮逼近，多方势力交汇，核心秘密即将揭晓。"),
        ]
        for boundary, direction in arcs:
            if chapter_num <= boundary:
                return direction
        return "故事后期阶段。收束伏笔，角色弧完成，走向结局。"

    # === character snapshots ===

    def _load_character_snapshots(self, characters: list[CharacterCard]) -> str:
        """出场角色的最新状态。跳过 dead/left 的角色，标记 injured/missing。"""
        parts = []
        for c in characters:
            state = c.state
            status = (state.status or "active").strip()

            # 已死亡/离场的角色不应出场
            if status in ("dead", "left"):
                logger.warning("%s 状态为 '%s'，但出现在出场角色列表中", c.name, status)
                continue

            lines = [f"【{c.name}】{c.one_line_pitch or '(无定位)'}"]

            # 异常状态提醒
            if status == "injured":
                lines.append("[状态: 受伤中，行动应受限]")
            elif status == "missing":
                lines.append("[状态: 失踪中，本章不应直接出场]")

            info_parts = []
            if state.location:
                info_parts.append(f"在{state.location}")
            if state.current_goal:
                info_parts.append(f"目标: {state.current_goal}")
            if state.current_emotion:
                info_parts.append(f"情绪: {state.current_emotion}")
            if state.physical_state:
                info_parts.append(f"身体: {state.physical_state}")
            if info_parts:
                lines.append("、".join(info_parts))

            if state.resources:
                lines.append(f"持有: {'、'.join(state.resources)}")

            if c.core.core_desire:
                lines.append(f"核心欲望: {c.core.core_desire}")
            if c.core.value_bottom_line:
                lines.append(f"底线: {'、'.join(c.core.value_bottom_line)}")

            # 说话样本（防串味）
            if c.speech_samples:
                sample = c.speech_samples[0] if c.speech_samples else ""
                if sample:
                    lines.append(f"说话示例: {sample}")

            parts.append("\n".join(lines))

        return "\n\n".join(parts)

    # === foreshadows ===

    def _load_due_foreshadows(self, chapter_num: int) -> str:
        """从伏笔文件查该回收/推进的伏笔。处理边界值。"""
        fs_file = self.config.resolve_data_dir() / "foreshadow.json"
        if not fs_file.exists():
            return ""

        try:
            raw = self._read_cached(fs_file)
            if raw is None:
                return ""
            data: list[dict] = json.loads(raw)
        except (json.JSONDecodeError, OSError) as e:
            logger.error("伏笔文件 %s 解析失败: %s", fs_file, e)
            return ""

        due = []
        for entry in data:
            status = entry.get("status", "")
            if status not in ("planted", "building"):
                continue

            planted = entry.get("planted_chapter", 0)
            if planted <= 0 or planted > chapter_num:
                # 未设定章号或数据异常，跳过
                continue

            age = chapter_num - planted
            priority = entry.get("priority", "normal")

            if ((priority == "high" and age > FORESHADOW_AGE_HIGH)
                    or (priority == "normal" and age > FORESHADOW_AGE_NORMAL)
                    or age > FORESHADOW_AGE_CRITICAL):
                due.append(
                    f"伏笔 [{entry.get('id', '?')}] '{entry.get('description', '')}' "
                    f"已埋 {age} 章 ({entry.get('type', '明')}伏笔)。"
                )

        if due:
            return "以下伏笔埋了较久，如果本章有合适时机请推进或回收：\n" + "\n".join(due)
        return ""

    # === constraints ===

    def _load_constraints(
        self,
        characters: list[CharacterCard],
        world: WorldSetting,
        narrator: NarratorCard | None = None,
    ) -> str:
        """生成本章'不该出现'的约束。"""
        bans = []

        # 世界硬约束
        if world.key_constraints:
            bans.append(f"世界观硬约束: {'; '.join(world.key_constraints)}")

        # 角色底线 + 禁用词
        for c in characters:
            if c.core.value_bottom_line:
                bans.append(f"不可违反 {c.name} 的底线: {'、'.join(c.core.value_bottom_line)}")
            if c.speech_profile.banned_words:
                bans.append(f"{c.name} 禁用词: {'、'.join(c.speech_profile.banned_words)}")

        # 叙述者禁令
        if narrator and narrator.banned_phrases:
            bans.append(f"叙述者禁用套话: {'、'.join(narrator.banned_phrases[:10])}")

        return "\n".join(bans) if bans else ""

    # === recent chapters ===

    def _load_recent_full(self, chapter_num: int) -> str:
        """加载最近 3 章全文，控制总字数"""
        if chapter_num <= 1:
            return ""

        output_dir = self.config.resolve_output_dir()
        loaded = 0
        parts = []
        for n in range(chapter_num - 1, max(0, chapter_num - 4), -1):
            path = output_dir / f"第{n}章" / "正文.md"
            text = self._read_cached(path)
            if text is not None:
                loaded += len(text)
                parts.insert(0, f"---第{n}章---\n{text}")
                if loaded > MAX_RECENT_WORDS:
                    break
        return "\n\n".join(parts)

    async def inject_graph_context(self, chapter_num: int, characters: list[CharacterCard]) -> str:
        """从墨脉图图谱拉取关系数据，生成可指导写作的上下文"""
        config = self.config
        if not config.is_momaitu_enabled():
            raise RuntimeError("图谱未启用——请在 .env 中配置 MO_MOMAITU_* 并启动墨脉图后端")

        try:
            from moliu.sync.client import MomaituSyncClient
            client = MomaituSyncClient(
                base_url=config.momaitu_base_url,
                username=config.momaitu_username,
                password=config.momaitu_password,
            )
            novel_id = config.momaitu_novel_id

            graph_chars = await client.get_characters(novel_id)
            graph_foreshadows = await client.get_foreshadows(novel_id)

            parts = []
            char_names = {c.name for c in characters}

            # 1. 角色出场间隔告警
            long_absent = []
            rarely_seen = []
            all_chars_absent = []
            for gc in graph_chars:
                name = gc.get("name", "")
                last_ch = int(gc.get("lastChapterAppeared", 0) or 0)
                gap = chapter_num - last_ch if last_ch > 0 else chapter_num
                status = gc.get("status", "")
                if status in ("dead", "left", "dropped"):
                    continue
                if name in char_names and gap > 5:
                    long_absent.append(f"[{name}] 已 {gap} 章没出现了——读者可能忘了 Ta 在干嘛")
                elif name not in char_names:
                    all_chars_absent.append(name)
                elif gap > 15:
                    rarely_seen.append(f"[{name}] 虽然本章未出场，但已 {gap} 章没被提及——考虑本章随口提一句")

            if long_absent:
                parts.append("【角色回归提醒】以下角色本章出场但已离开读者视野较久:\n" + "\n".join(long_absent))
            if rarely_seen:
                parts.append("【角色存在感】以下角色长期未露面:\n" + "\n".join(rarely_seen))
            if all_chars_absent and len(all_chars_absent) > 2:
                parts.append(f"【剧情密度】{len(char_names)} 个角色出现在本章，" + "、".join(all_chars_absent[:4]) + f" 等 {len(all_chars_absent)} 个角色未出场。考虑配角线是否需要推进")

            # 2. 活跃伏笔
            active_fs = []
            critical_fs = []
            for fs in graph_foreshadows:
                s = fs.get("status", "")
                if s not in ("planted", "building"):
                    continue
                planted = int(fs.get("plantedChapter", 0) or 0)
                if planted <= 0 or planted > chapter_num:
                    continue
                age = chapter_num - planted
                desc = fs.get("description", "")[:80]
                eid = fs.get("id", "?")[:12]
                if age > FORESHADOW_AGE_CRITICAL:
                    critical_fs.append(f"[!!] '{desc}' 已埋 {age} 章——再不回收读者要忘了")
                elif age > FORESHADOW_AGE_NORMAL:
                    active_fs.append(f"[!] '{desc}' 已埋 {age} 章——如果本章情节合适请推进")

            if critical_fs:
                parts.append("【伏笔紧急】\n" + "\n".join(critical_fs))
            elif active_fs:
                parts.append("【伏笔提醒】\n" + "\n".join(active_fs))

            # 3. 如果没有任何提醒——说明剧情平衡，给正向反馈
            if not parts and chapter_num > 5:
                parts.append(f"【图谱状态】{len(graph_chars)} 个角色出场节奏正常，伏笔状态良好。保持。")

            return "\n\n".join(parts) if parts else ""

        except Exception as e:
            raise RuntimeError(f"图谱注入失败——请确认墨脉图后端是否启动: {e}") from e

    def _load_last_300_words(self, chapter_num: int) -> str:
        if chapter_num <= 1:
            return ""
        path = self.config.resolve_output_dir() / f"第{chapter_num - 1}章" / "正文.md"
        text = self._read_cached(path)
        if text is not None:
            return text[-300:] if len(text) > 300 else text
        return ""
