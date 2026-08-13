"""关系抽取器 — 从章节正文用 LLM 抽取角色关系

输入：章节正文 + 出场角色列表
输出：关系列表 [{source_name, target_name, rel_type, category, intensity, description}, ...]

设计要点：
- 用 JSON 模式输出，严格约束格式，避免幻觉
- 只允许抽取角色名存在于给定角色列表中的关系
- 温度低（0.3），追求稳定
"""
from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING

from moliu.config import Config
from moliu.engines.gateway import DeepSeekGateway

if TYPE_CHECKING:
    from moliu.data.schemas import CharacterCard

logger = logging.getLogger(__name__)

# 系统 Prompt：要求 LLM 输出严格 JSON
_SYSTEM_PROMPT = """你是小说角色关系抽取器。

任务：分析章节正文，抽取角色之间的关系。

输出格式：必须是合法 JSON 数组，每个元素格式如下：
{
  "source_name": "角色A名字",
  "target_name": "角色B名字",
  "rel_type": "关系类型（如：父子/师徒/恋人/仇敌/朋友/主仆/合作/竞争/暗恋等）",
  "category": "positive/neutral/negative 之一",
  "directed": 0 或 1（0=双向关系，1=单向如暗恋），
  "intensity": 1-10 的整数（关系强度），
  "description": "一句话描述这对关系"
}

规则：
1. source_name 和 target_name 必须严格来自给定的角色名列表
2. 只抽取本章正文明确体现的关系（本章新形成或本章有明显变化的关系）
3. 关系类型要具体（如 "师徒" 而非 "上下级"）
4. 不要编造角色或关系
5. 如果本章没有明显的关系变化，返回空数组 []
6. 不要输出任何其他内容，只输出 JSON 数组
"""


class RelationExtractor:
    """关系抽取器"""

    def __init__(self, config: Config, gateway: DeepSeekGateway):
        self.config = config
        self.gateway = gateway

    async def extract(
        self,
        chapter_num: int,
        content: str,
        characters: list[CharacterCard],
    ) -> list[dict]:
        """抽取章节中的角色关系

        Returns:
            关系列表，每个元素是 dict，字段对齐墨脉图 MoliuRelationshipSyncDTO
        """
        if not characters:
            return []

        char_list = "\n".join(f"- {c.name}: {c.one_line_pitch or ''}" for c in characters)
        user_prompt = f"""章节号：第 {chapter_num} 章

出场角色列表：
{char_list}

章节正文：
---
{content}
---

请抽取本章中角色之间的关系，只输出 JSON 数组。
"""

        try:
            raw, tokens = await self.gateway.generate(
                system_prompt=_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                temperature=0.3,
                max_tokens=2048,
                chapter_num=chapter_num,
            )
        except Exception as e:
            logger.warning("关系抽取 LLM 调用失败 ch%d: %s", chapter_num, e)
            return []

        # 解析 JSON（LLM 输出可能含 markdown 代码块）
        relations = self._parse_json(raw)
        if not relations:
            logger.info("第%d章未抽取到关系", chapter_num)
            return []

        # 过滤：只保留角色名在列表中的关系
        valid_names = {c.name for c in characters}
        filtered = []
        for r in relations:
            src = r.get("source_name")
            tgt = r.get("target_name")
            if src in valid_names and tgt in valid_names and src != tgt:
                # 补 start_chapter
                if not r.get("start_chapter"):
                    r["start_chapter"] = f"第{chapter_num}章"
                filtered.append(r)
            else:
                logger.debug("过滤无效关系: %s -> %s", src, tgt)

        logger.info("第%d章抽取到 %d 条关系（过滤后）", chapter_num, len(filtered))
        return filtered

    @staticmethod
    def _parse_json(raw: str) -> list[dict]:
        """从 LLM 输出中提取 JSON 数组（兼容 markdown 代码块包裹）"""
        # 去掉 markdown ```json ... ``` 包裹
        cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned.strip())

        # 尝试找到第一个 [ 到最后一个 ]
        start = cleaned.find("[")
        end = cleaned.rfind("]")
        if start == -1 or end == -1 or end <= start:
            return []

        try:
            parsed = json.loads(cleaned[start:end + 1])
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError as e:
            logger.warning("关系抽取 JSON 解析失败: %s, raw=%s", e, cleaned[:200])
        return []
