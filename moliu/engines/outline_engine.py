"""章级大纲引擎 (P0-2) — 预规划 50-100 章 beat + 节点

核心问题:
- 现有生成流程中 beat 由用户手动传入,无法支撑长篇(1000 章)连续生成
- 缺少整体节奏控制,容易出现剧情漫无目的

解决方案:
- ChapterOutlineEngine 提供「卷级整体规划」+「章级细化」两层大纲
- 基于 LLM 生成一批(如 10-20 章)beat 节点,包含情绪、章节类型、关键事件、伏笔埋设/回收
- 与分层记忆联动:生成新大纲时参考 Story Bible 和已有阶段摘要
- 与生成管线联动:生成章节时自动从大纲读取 beat,无需手动传入

数据结构:
- 每卷对应一个 outlines/{volume_id}.json 文件
- 含 ChapterPlan 列表,持久化到磁盘

生成策略:
- LLM 不可用时降级为模板填充(基础节奏型 + 情绪节拍)
- LLM 可用时基于上下文(世界观、角色、Story Bible、卷摘要、上一章状态)生成
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from moliu.data.schemas import (
    ChapterPlan,
    CharacterCard,
    Novel,
    VolumeIndex,
    VolumePlan,
    WorldSetting,
)

if TYPE_CHECKING:
    from moliu.config import Config
    from moliu.engines.gateway import DeepSeekGateway
    from moliu.memory.layered import LayeredMemory

logger = logging.getLogger(__name__)

# 默认章节类型节奏模式 — 一卷 20 章的典型节奏分布
DEFAULT_RHYTHM_PATTERN = [
    "opening",    # 开篇
    "normal", "normal", "normal",  # 铺陈
    "normal", "normal",             # 转折
    "climax",                       # 小高潮
    "transition",                   # 过渡
    "normal", "normal", "normal",   # 新线展开
    "normal", "normal",             # 加压
    "climax",                       # 大高潮
    "transition",                   # 收束
    "normal", "normal",             # 余韵
    "opening",                      # 下卷引子
    "normal", "normal",
]

DEFAULT_EMOTION_PATTERN = [
    "好奇", "平静", "期待", "轻松",
    "紧张", "不安",
    "激动", "震撼",
    "缓和",
    "期待", "轻松", "好奇",
    "紧张", "压抑",
    "激昂", "震动",
    "舒缓",
    "感动", "回味",
    "好奇",
    "期待", "紧张",
]


@dataclass
class OutlineGenResult:
    """大纲生成结果"""
    volume_id: int
    chapter_start: int
    chapter_end: int
    plans: list[ChapterPlan]
    model_used: str = "heuristic"
    tokens_used: int = 0


class ChapterOutlineEngine:
    """章级大纲引擎

    使用方式:
        engine = ChapterOutlineEngine(config, novel_id=1, gateway=gateway)
        # 为卷 1 生成 1-30 章的大纲
        result = await engine.generate_for_volume(volume_id=1)
        # 获取第 15 章的 beat
        plan = engine.get_chapter_plan(15)
        if plan:
            beat, emotion, chapter_type = plan.beat, plan.emotion, plan.chapter_type
    """

    def __init__(
        self,
        config: "Config",
        novel_id: int = 1,
        gateway: "DeepSeekGateway | None" = None,
        layered_memory: "LayeredMemory | None" = None,
    ) -> None:
        self.config = config
        self.novel_id = novel_id
        self.gateway = gateway
        self._layered_memory = layered_memory
        self._outlines_dir = config.resolve_data_dir(novel_id) / "outlines"
        self._outlines_dir.mkdir(parents=True, exist_ok=True)

    # === 持久化 ===

    def _outline_file(self, volume_id: int) -> Path:
        return self._outlines_dir / f"volume_{volume_id:02d}.json"

    def load_volume_outline(self, volume_id: int) -> list[ChapterPlan]:
        """加载指定卷的章级大纲"""
        path = self._outline_file(volume_id)
        if not path.exists():
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return [ChapterPlan(**p) for p in data.get("chapters", [])]
        except Exception as e:
            logger.warning("加载卷 %s 大纲失败: %s", volume_id, e)
            return []

    def save_volume_outline(self, volume_id: int, plans: list[ChapterPlan]) -> Path:
        """保存卷的章级大纲"""
        path = self._outline_file(volume_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "volume_id": volume_id,
            "novel_id": self.novel_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "chapters": [p.model_dump() for p in plans],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        return path

    def get_chapter_plan(self, chapter_num: int) -> ChapterPlan | None:
        """获取指定章节的大纲规划 — 跨所有卷查找"""
        # 先确定章节属于哪一卷
        volume = self._find_volume_for_chapter(chapter_num)
        if volume is None:
            return None
        plans = self.load_volume_outline(volume.id)
        for p in plans:
            if p.chapter_num == chapter_num:
                return p
        return None

    def _find_volume_for_chapter(self, chapter_num: int) -> VolumePlan | None:
        """通过 VolumeIndex 查找章节所属的卷"""
        index_path = self.config.resolve_data_dir(self.novel_id) / "volumes" / "index.json"
        if not index_path.exists():
            return None
        try:
            vidx = VolumeIndex.from_json(index_path)
            return vidx.get_volume_for_chapter(chapter_num)
        except Exception:
            return None

    def list_all_plans(self) -> dict[int, list[ChapterPlan]]:
        """返回所有卷的大纲 {volume_id: [ChapterPlan, ...]}"""
        result: dict[int, list[ChapterPlan]] = {}
        for path in sorted(self._outlines_dir.glob("volume_*.json")):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                vid = data.get("volume_id", 0)
                plans = [ChapterPlan(**p) for p in data.get("chapters", [])]
                result[vid] = plans
            except Exception as e:
                logger.warning("加载大纲文件 %s 失败: %s", path, e)
        return result

    # === 大纲生成 ===

    async def generate_for_volume(
        self,
        volume_id: int,
        *,
        force: bool = False,
        characters: list[CharacterCard] | None = None,
        world: WorldSetting | None = None,
    ) -> OutlineGenResult:
        """为指定卷生成章级大纲

        Args:
            volume_id: 卷 ID
            force: 是否强制覆盖已存在的大纲
            characters: 角色列表(可选,用于 LLM 生成时参考)
            world: 世界观(可选)
        """
        # 1. 读取卷元数据
        volume = self._load_volume(volume_id)
        if volume is None:
            raise ValueError(f"卷 {volume_id} 不存在")

        if volume.chapter_end < volume.chapter_start:
            raise ValueError(f"卷 {volume_id} 章节范围无效: {volume.chapter_start}-{volume.chapter_end}")

        # 2. 已有大纲检查
        existing = self.load_volume_outline(volume_id)
        if existing and not force:
            logger.info("卷 %s 大纲已存在(%d 章),跳过生成", volume_id, len(existing))
            return OutlineGenResult(
                volume_id=volume_id,
                chapter_start=volume.chapter_start,
                chapter_end=volume.chapter_end,
                plans=existing,
                model_used="cached",
            )

        # 3. 选择生成策略:LLM 优先,降级到启发式
        plans: list[ChapterPlan] = []
        model_used = "heuristic"
        tokens = 0

        if self.gateway is not None:
            try:
                plans, tokens = await self._generate_with_llm(
                    volume, characters or [], world,
                )
                model_used = self.config.deepseek_model
            except Exception as e:
                logger.warning("LLM 生成卷 %s 大纲失败,降级到启发式: %s", volume_id, e)
                plans = self._generate_heuristic(volume)
        else:
            plans = self._generate_heuristic(volume)

        # 4. 保留已有状态(已生成章节的 status 不覆盖)
        if existing:
            existing_status = {p.chapter_num: p.status for p in existing}
            for p in plans:
                if p.chapter_num in existing_status:
                    p.status = existing_status[p.chapter_num]

        # 5. 持久化
        self.save_volume_outline(volume_id, plans)

        return OutlineGenResult(
            volume_id=volume_id,
            chapter_start=volume.chapter_start,
            chapter_end=volume.chapter_end,
            plans=plans,
            model_used=model_used,
            tokens_used=tokens,
        )

    def _load_volume(self, volume_id: int) -> VolumePlan | None:
        """加载卷元数据"""
        index_path = self.config.resolve_data_dir(self.novel_id) / "volumes" / "index.json"
        if not index_path.exists():
            return None
        vidx = VolumeIndex.from_json(index_path)
        for v in vidx.volumes:
            if v.id == volume_id:
                return v
        return None

    # === 启发式生成(无 LLM 时的降级) ===

    def _generate_heuristic(self, volume: VolumePlan) -> list[ChapterPlan]:
        """启发式生成 — 基于节奏模板填充

        优点:
        - 无需 LLM 即可生成结构化大纲
        - 节奏型固定,保证有起承转合
        - 字段留空,后续可由 LLM 补充 beat 描述
        """
        plans: list[ChapterPlan] = []
        n_chapters = volume.chapter_end - volume.chapter_start + 1

        for i, ch_num in enumerate(range(volume.chapter_start, volume.chapter_end + 1)):
            rhythm_idx = i % len(DEFAULT_RHYTHM_PATTERN)
            emotion_idx = i % len(DEFAULT_EMOTION_PATTERN)
            chapter_type = DEFAULT_RHYTHM_PATTERN[rhythm_idx]
            emotion = DEFAULT_EMOTION_PATTERN[emotion_idx]

            # 基础 beat 描述 — 由卷摘要 + 章节类型推断
            beat = self._heuristic_beat(volume, ch_num, chapter_type, i, n_chapters)

            plans.append(ChapterPlan(
                chapter_num=ch_num,
                title="",  # 标题留给生成时由 LLM 起
                beat=beat,
                emotion=emotion,
                chapter_type=chapter_type,
                characters=[],  # 启发式不猜测出场角色
                key_events=[],
                foreshadows_plant=[],
                foreshadows_pay=[],
                status="planned",
            ))
        return plans

    def _heuristic_beat(
        self, volume: VolumePlan, ch_num: int,
        chapter_type: str, idx: int, total: int,
    ) -> str:
        """生成启发式 beat 描述"""
        vol_name = volume.name or f"卷{volume.id}"
        vol_summary = volume.summary or "本卷核心冲突展开"

        # 按章节类型给出不同的 beat 模板
        if chapter_type == "opening":
            if idx == 0:
                return f"开篇:引入{vol_name}的核心冲突。{vol_summary}"
            return f"开启新阶段:埋下下一阶段伏笔,呼应{vol_name}主题"
        if chapter_type == "climax":
            position = "小高潮" if idx < total // 2 else "卷末高潮"
            return f"{position}:{vol_name}核心冲突爆发的关键章节"
        if chapter_type == "transition":
            return f"过渡:消化前文高潮余韵,为下一阶段铺垫"
        # normal
        return f"推进{vol_name}剧情,深化角色关系"

    # === LLM 生成 ===

    async def _generate_with_llm(
        self,
        volume: VolumePlan,
        characters: list[CharacterCard],
        world: WorldSetting | None,
    ) -> tuple[list[ChapterPlan], int]:
        """基于 LLM 生成章级大纲

        让 LLM 输出 JSON 数组,每项对应一章的 beat/emotion/type/key_events/foreshadows

        Raises:
            ValueError: LLM 输出无法解析为合法 JSON
        """
        from moliu.prompts.manager import PromptManager

        # 收集上下文
        char_brief = "\n".join(
            f"- {c.name}: {c.one_line_pitch}" for c in characters[:8]  # 最多 8 个角色
        ) or "(无角色信息)"

        world_brief = ""
        if world:
            world_brief = world.to_context()

        vol_summary = volume.summary or "(无卷摘要)"
        chapter_range = f"{volume.chapter_start}-{volume.chapter_end}"
        n_chapters = volume.chapter_end - volume.chapter_start + 1

        # Story Bible 上下文(可选)
        bible_ctx = ""
        if self._layered_memory is not None:
            try:
                bible = self._layered_memory.load_bible()
                bible_ctx = bible.to_context()
            except Exception:
                bible_ctx = ""

        # 阶段摘要(可选)— 显示到上一卷末
        arc_ctx = ""
        if self._layered_memory is not None:
            try:
                arc_ctx = self._layered_memory.assemble_for_chapter(volume.chapter_start)
            except Exception:
                arc_ctx = ""

        # 直接构造 prompt(避免依赖额外的 jinja 模板文件)
        system_prompt = f"""你是资深小说编辑,擅长长篇小说的章节大纲规划。

任务:为卷《{volume.name or f'卷{volume.id}'}》(第{chapter_range}章,共{n_chapters}章)规划每章的 beat 节点。

【卷摘要】
{vol_summary}

【世界观】
{world_brief}

【主要角色】
{char_brief}

【已有故事记忆】
{bible_ctx}
{arc_ctx}

【输出要求】
输出严格的 JSON 数组,数组长度必须等于 {n_chapters}。每个元素:
{{
  "chapter_num": <int, 从 {volume.chapter_start} 开始递增>,
  "title": "<可选,可留空>",
  "beat": "<一句话描述本章核心节拍,50-100 字>",
  "emotion": "<情绪标签,如:紧张/期待/悲伤/震撼>",
  "chapter_type": "<opening/normal/climax/transition/epilogue 之一>",
  "key_events": ["<关键事件1>", "<关键事件2>"],
  "foreshadows_plant": ["<本章埋下的伏笔>"],
  "foreshadows_pay": ["<本章回收的伏笔>"]
}}

节奏原则:
- 每卷至少 2 个 climax(小高潮 + 卷末高潮)
- opening 章节开篇定调,transition 章节过场收束
- 伏笔要埋设与回收对应,跨章节呼应
- beat 描述具体可执行,避免空泛的"推进剧情"
- 情绪曲线有起伏,避免平铺直叙

只输出 JSON 数组,不要其他解释文字。"""

        user_prompt = f"请为第{chapter_range}章({n_chapters}章)生成大纲。"

        try:
            content, tokens = await self.gateway.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.7,
            )
        except Exception as e:
            logger.error("LLM 调用失败: %s", e)
            raise

        # 解析 LLM 输出 — 失败时抛异常让上层降级
        plans = self._parse_llm_outline(content, volume.chapter_start, volume.chapter_end)
        if plans is None:
            raise ValueError("LLM 输出无法解析为合法大纲")
        return plans, tokens

    def _parse_llm_outline(
        self, content: str, ch_start: int, ch_end: int,
    ) -> list[ChapterPlan] | None:
        """解析 LLM 输出为 ChapterPlan 列表

        Returns:
            解析成功的 ChapterPlan 列表,若无法解析返回 None(由上层降级处理)
        """
        # 尝试提取 JSON 数组
        text = content.strip()

        # 去除可能的 markdown 包裹
        if "```" in text:
            # 提取 ```json ... ``` 或 ``` ... ``` 内的内容
            import re
            m = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
            if m:
                text = m.group(1).strip()

        # 找到第一个 [ 和最后一个 ]
        start = text.find("[")
        end = text.rfind("]")
        if start == -1 or end == -1:
            logger.warning("LLM 输出未找到 JSON 数组")
            return None

        try:
            data = json.loads(text[start:end + 1])
        except json.JSONDecodeError as e:
            logger.warning("LLM 输出 JSON 解析失败: %s", e)
            return None

        plans: list[ChapterPlan] = []
        for item in data:
            try:
                ch_num = int(item.get("chapter_num", 0))
                if ch_num < ch_start or ch_num > ch_end:
                    logger.warning("LLM 输出的 chapter_num=%s 超出范围 %s-%s,跳过",
                                   ch_num, ch_start, ch_end)
                    continue
                plan = ChapterPlan(
                    chapter_num=ch_num,
                    title=str(item.get("title", "")),
                    beat=str(item.get("beat", "")),
                    emotion=str(item.get("emotion", "")),
                    chapter_type=str(item.get("chapter_type", "normal")),
                    characters=list(item.get("characters", [])),
                    key_events=list(item.get("key_events", [])),
                    foreshadows_plant=list(item.get("foreshadows_plant", [])),
                    foreshadows_pay=list(item.get("foreshadows_pay", [])),
                    status="planned",
                )
                plans.append(plan)
            except Exception as e:
                logger.warning("解析大纲项失败: %s, item=%s", e, item)
                continue

        # 补全缺失的章节(用启发式填充)
        existing_nums = {p.chapter_num for p in plans}
        if existing_nums:  # 只有 LLM 至少返回了一些有效数据时才补全
            fake_volume = VolumePlan(id=0, chapter_start=ch_start, chapter_end=ch_end)
            heuristic_plans = self._generate_heuristic(fake_volume)
            for p in heuristic_plans:
                if p.chapter_num not in existing_nums:
                    plans.append(p)

        plans.sort(key=lambda p: p.chapter_num)
        return plans

    # === 单章 beat 更新 ===

    def update_chapter_plan(self, chapter_num: int, **fields) -> ChapterPlan | None:
        """更新单章大纲字段

        用法:
            engine.update_chapter_plan(15, beat="主角与反派决战", emotion="激昂")
        """
        volume = self._find_volume_for_chapter(chapter_num)
        if volume is None:
            return None

        plans = self.load_volume_outline(volume.id)
        for p in plans:
            if p.chapter_num == chapter_num:
                for k, v in fields.items():
                    if hasattr(p, k):
                        setattr(p, k, v)
                self.save_volume_outline(volume.id, plans)
                return p
        return None

    def mark_chapter_status(self, chapter_num: int, status: str) -> None:
        """更新章节状态(planned/generating/completed/revised)"""
        self.update_chapter_plan(chapter_num, status=status)

    # === 全局大纲统计 ===

    def get_outline_coverage(self) -> dict:
        """获取大纲覆盖率统计

        返回:
            {
                "total_planned": <已规划章节数>,
                "total_generated": <已生成章节数>,
                "covered_volumes": [<volume_id>, ...],
                "missing_volumes": [<volume_id>, ...],
            }
        """
        # 读取所有卷
        index_path = self.config.resolve_data_dir(self.novel_id) / "volumes" / "index.json"
        all_volumes: list[VolumePlan] = []
        if index_path.exists():
            vidx = VolumeIndex.from_json(index_path)
            all_volumes = vidx.volumes

        all_outlines = self.list_all_plans()
        total_planned = 0
        total_generated = 0
        covered = []
        missing = []

        for v in all_volumes:
            plans = all_outlines.get(v.id, [])
            if plans:
                covered.append(v.id)
                total_planned += len(plans)
                total_generated += sum(1 for p in plans if p.status == "completed")
            else:
                missing.append(v.id)

        return {
            "total_planned": total_planned,
            "total_generated": total_generated,
            "covered_volumes": covered,
            "missing_volumes": missing,
        }
