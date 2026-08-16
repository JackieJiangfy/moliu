"""伏笔自动提取器 (P1-1) — 从章节内容自动提取伏笔并追踪状态

核心问题:
- 现有 ForeshadowManager 只支持手动 plant/advance/pay
- 长篇(1000 章)生成时,无法人工追踪所有伏笔
- 缺少与大纲(ChapterPlan.foreshadows_plant/pay)的联动

解决方案:
- ForeshadowExtractor 从生成的章节正文自动提取伏笔
- 策略:LLM 优先(理解上下文),降级到关键词启发式
- 与大纲联动:章节生成后自动比对大纲的 foreshadows_plant/pay,标记状态
- 与 ForeshadowManager 联动:新伏笔自动 plant,已回收的自动 pay
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from moliu.data.schemas import ChapterPlan
from moliu.rules.foreshadow_watch import ForeshadowEntry, ForeshadowManager

if TYPE_CHECKING:
    from moliu.config import Config
    from moliu.engines.gateway import DeepSeekGateway

logger = logging.getLogger(__name__)


@dataclass
class ExtractedForeshadow:
    """从章节中提取出的伏笔信息"""
    description: str
    action: str = "plant"     # plant / advance / pay
    priority: str = "normal"  # high / normal / low
    type: str = "明"          # 明 / 暗 / 潜
    matched_plan: str = ""    # 匹配到的大纲规划项(可空)


@dataclass
class ExtractResult:
    """提取结果"""
    chapter_num: int
    planted: list[ExtractedForeshadow] = field(default_factory=list)
    advanced: list[ExtractedForeshadow] = field(default_factory=list)
    paid: list[ExtractedForeshadow] = field(default_factory=list)
    model_used: str = "heuristic"
    tokens_used: int = 0


class ForeshadowExtractor:
    """伏笔自动提取器

    使用方式:
        extractor = ForeshadowExtractor(config, novel_id=1, gateway=gateway)
        result = await extractor.extract_from_chapter(chapter_num, content, plan)
        # 应用到 ForeshadowManager
        extractor.apply_to_manager(result, manager)
    """

    # 启发式关键词 — 用于无 LLM 时的降级提取
    PLANT_KEYWORDS = [
        "神秘", "未知", "隐藏", "暗中", "悄悄", "未解", "谜团",
        "似乎", "仿佛", "不详", "可疑", "古怪", "奇异",
    ]
    PAY_KEYWORDS = [
        "原来", "真相", "揭晓", "解开", "解释", "终于明白",
        "浮出水面", "水落石出", "真相大白",
    ]
    ADVANCE_KEYWORDS = [
        "线索", "迹象", "苗头", "端倪", "暗示", "指向",
    ]

    def __init__(
        self,
        config: "Config",
        novel_id: int = 1,
        gateway: "DeepSeekGateway | None" = None,
    ) -> None:
        self.config = config
        self.novel_id = novel_id
        self.gateway = gateway

    async def extract_from_chapter(
        self,
        chapter_num: int,
        content: str,
        plan: ChapterPlan | None = None,
    ) -> ExtractResult:
        """从章节内容提取伏笔

        Args:
            chapter_num: 章节号
            content: 章节正文
            plan: 章节大纲规划(可选,用于比对预期伏笔)
        """
        # 若有大纲规划,优先用大纲的伏笔信息
        if plan is not None and (plan.foreshadows_plant or plan.foreshadows_pay):
            return self._extract_from_plan(chapter_num, plan)

        # 否则用 LLM 或启发式从正文提取
        if self.gateway is not None:
            try:
                return await self._extract_with_llm(chapter_num, content)
            except Exception as e:
                logger.warning("LLM 伏笔提取失败,降级到启发式: %s", e)

        return self._extract_heuristic(chapter_num, content)

    def _extract_from_plan(
        self, chapter_num: int, plan: ChapterPlan,
    ) -> ExtractResult:
        """从大纲规划提取伏笔 — 高置信度,直接采用"""
        result = ExtractResult(chapter_num=chapter_num, model_used="plan")
        for desc in plan.foreshadows_plant:
            result.planted.append(ExtractedForeshadow(
                description=desc, action="plant", matched_plan="plant",
            ))
        for desc in plan.foreshadows_pay:
            result.paid.append(ExtractedForeshadow(
                description=desc, action="pay", matched_plan="pay",
            ))
        return result

    def _extract_heuristic(self, chapter_num: int, content: str) -> ExtractResult:
        """启发式提取 — 基于关键词匹配

        简单但可用,适合无 LLM 场景
        """
        result = ExtractResult(chapter_num=chapter_num, model_used="heuristic")

        # 按句子分割
        sentences = re.split(r"[。！？\n]", content)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 5]

        seen_descriptions: set[str] = set()

        for sent in sentences:
            # 检测埋伏笔
            for kw in self.PLANT_KEYWORDS:
                if kw in sent:
                    desc = self._extract_description(sent, kw)
                    if desc and desc not in seen_descriptions:
                        # 启发式判断类型
                        ftype = "暗" if any(k in sent for k in ["悄悄", "暗中", "隐藏", "未察觉"]) else "明"
                        result.planted.append(ExtractedForeshadow(
                            description=desc, action="plant", type=ftype,
                        ))
                        seen_descriptions.add(desc)
                    break

            # 检测回收伏笔
            for kw in self.PAY_KEYWORDS:
                if kw in sent:
                    desc = self._extract_description(sent, kw)
                    if desc and desc not in seen_descriptions:
                        result.paid.append(ExtractedForeshadow(
                            description=desc, action="pay",
                        ))
                        seen_descriptions.add(desc)
                    break

            # 检测推进伏笔
            for kw in self.ADVANCE_KEYWORDS:
                if kw in sent:
                    desc = self._extract_description(sent, kw)
                    if desc and desc not in seen_descriptions:
                        result.advanced.append(ExtractedForeshadow(
                            description=desc, action="advance",
                        ))
                        seen_descriptions.add(desc)
                    break

        # 限制每类最多 5 条,避免噪声
        result.planted = result.planted[:5]
        result.advanced = result.advanced[:3]
        result.paid = result.paid[:3]
        return result

    def _extract_description(self, sentence: str, keyword: str) -> str:
        """从句子中提取伏笔描述"""
        # 找到关键词位置,提取前后 20 字
        idx = sentence.find(keyword)
        if idx == -1:
            return ""
        start = max(0, idx - 10)
        end = min(len(sentence), idx + len(keyword) + 20)
        desc = sentence[start:end].strip()
        # 清理标点
        desc = re.sub(r"^[，,。！？\s]+|[，,。！？\s]+$", "", desc)
        return desc if len(desc) >= 4 else ""

    async def _extract_with_llm(
        self, chapter_num: int, content: str,
    ) -> ExtractResult:
        """LLM 提取 — 理解上下文,准确率更高"""
        # 截断过长内容(保留开头和结尾)
        if len(content) > 8000:
            content = content[:4000] + "\n...(中间省略)...\n" + content[-3000:]

        system_prompt = """你是资深小说编辑,擅长识别章节中的伏笔。

任务:分析给定章节,提取本章的伏笔动作。

伏笔动作类型:
- plant: 本章新埋下的伏笔(后续章节才能回收的悬念)
- advance: 本章推进了已有伏笔(给出新线索,但未回收)
- pay: 本章回收了某个伏笔(真相揭晓)

输出严格的 JSON:
{
  "planted": [
    {"description": "<伏笔描述,30-60字>", "type": "明/暗/潜", "priority": "high/normal/low"}
  ],
  "advanced": [
    {"description": "<推进的伏笔描述>"}
  ],
  "paid": [
    {"description": "<回收的伏笔描述>"}
  ]
}

判断标准:
- 明伏笔:读者能直接察觉的悬念
- 暗伏笔:细心读者能发现的隐藏线索
- 潜伏笔:作者埋下的,读者几乎察觉不到
- high:影响主线的关键伏笔
- normal:支线伏笔
- low:细节伏笔

若本章无明显伏笔,返回空数组。只输出 JSON,不要其他解释。"""

        user_prompt = f"第{chapter_num}章正文:\n\n{content}"

        try:
            response, tokens = await self.gateway.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.3,
            )
        except Exception as e:
            logger.error("LLM 调用失败: %s", e)
            raise

        result = ExtractResult(
            chapter_num=chapter_num,
            model_used=self.config.deepseek_model,
            tokens_used=tokens,
        )

        # 解析 JSON
        text = response.strip()
        if "```" in text:
            m = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
            if m:
                text = m.group(1).strip()

        # 找 JSON 对象
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1:
            logger.warning("LLM 伏笔输出未找到 JSON")
            return result

        try:
            data = json.loads(text[start:end + 1])
        except json.JSONDecodeError as e:
            logger.warning("LLM 伏笔 JSON 解析失败: %s", e)
            return result

        for item in data.get("planted", []):
            try:
                result.planted.append(ExtractedForeshadow(
                    description=str(item.get("description", "")),
                    action="plant",
                    priority=str(item.get("priority", "normal")),
                    type=str(item.get("type", "明")),
                ))
            except Exception:
                continue

        for item in data.get("advanced", []):
            try:
                result.advanced.append(ExtractedForeshadow(
                    description=str(item.get("description", "")),
                    action="advance",
                ))
            except Exception:
                continue

        for item in data.get("paid", []):
            try:
                result.paid.append(ExtractedForeshadow(
                    description=str(item.get("description", "")),
                    action="pay",
                ))
            except Exception:
                continue

        return result

    def apply_to_manager(
        self,
        result: ExtractResult,
        manager: ForeshadowManager,
    ) -> dict:
        """将提取结果应用到 ForeshadowManager

        策略:
        - planted: 若描述与已有伏笔相似度低,则新增
        - paid: 若能匹配到已有 planted/building 伏笔,则回收
        - advanced: 若能匹配,则推进;否则忽略

        Returns:
            统计信息: {"planted": N, "advanced": N, "paid": N, "skipped": N}
        """
        stats = {"planted": 0, "advanced": 0, "paid": 0, "skipped": 0}

        # 1. 处理 plant
        for ext in result.planted:
            # 去重 — 检查是否已有相似描述
            if self._find_similar(manager, ext.description, statuses=("planted", "building")):
                stats["skipped"] += 1
                continue
            manager.plant(
                description=ext.description,
                chapter_num=result.chapter_num,
                priority=ext.priority,
                type=ext.type,
            )
            stats["planted"] += 1

        # 2. 处理 advance
        for ext in result.advanced:
            entry = self._find_similar(manager, ext.description, statuses=("planted",))
            if entry:
                try:
                    manager.advance(entry.id, result.chapter_num)
                    stats["advanced"] += 1
                except Exception:
                    pass
            else:
                stats["skipped"] += 1

        # 3. 处理 pay
        for ext in result.paid:
            entry = self._find_similar(manager, ext.description, statuses=("planted", "building"))
            if entry:
                try:
                    manager.pay(entry.id, result.chapter_num)
                    stats["paid"] += 1
                except Exception:
                    pass
            else:
                stats["skipped"] += 1

        return stats

    def _find_similar(
        self,
        manager: ForeshadowManager,
        description: str,
        statuses: tuple[str, ...],
    ) -> ForeshadowEntry | None:
        """在 manager 中查找相似伏笔

        简单策略:关键词重合度 > 50% 视为相似
        """
        desc_words = set(self._tokenize(description))
        if not desc_words:
            return None

        best_match = None
        best_score = 0.0

        for entry in manager._entries:
            if entry.status not in statuses:
                continue
            entry_words = set(self._tokenize(entry.description))
            if not entry_words:
                continue
            # Jaccard 相似度
            intersection = desc_words & entry_words
            union = desc_words | entry_words
            score = len(intersection) / len(union) if union else 0
            if score > best_score:
                best_score = score
                best_match = entry

        # 相似度阈值
        if best_score >= 0.5:
            return best_match
        return None

    def _tokenize(self, text: str) -> list[str]:
        """简单分词 — 中文按字,英文按词"""
        # 中文按 2-gram
        tokens: list[str] = []
        chinese_chars = re.findall(r"[\u4e00-\u9fff]", text)
        for i in range(len(chinese_chars) - 1):
            tokens.append(chinese_chars[i] + chinese_chars[i + 1])
        # 英文按词
        english_words = re.findall(r"[a-zA-Z]+", text)
        tokens.extend(w.lower() for w in english_words if len(w) >= 3)
        return tokens


# === 管线集成辅助 ===

async def extract_and_apply_foreshadows(
    config: "Config",
    novel_id: int,
    chapter_num: int,
    content: str,
    plan: ChapterPlan | None = None,
    gateway: "DeepSeekGateway | None" = None,
) -> tuple[ExtractResult, dict]:
    """章节生成后调用 — 自动提取并应用伏笔

    Returns:
        (extract_result, apply_stats)
    """
    extractor = ForeshadowExtractor(config, novel_id=novel_id, gateway=gateway)
    result = await extractor.extract_from_chapter(chapter_num, content, plan)

    # 加载 ForeshadowManager
    data_dir = config.resolve_data_dir(novel_id)
    manager = ForeshadowManager(data_dir)

    stats = extractor.apply_to_manager(result, manager)
    return result, stats
