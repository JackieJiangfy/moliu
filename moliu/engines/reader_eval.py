"""读者体验评估 — 模拟读者视角评估章节质量"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from moliu.engines.gateway import DeepSeekGateway

logger = logging.getLogger(__name__)


@dataclass
class ReaderFeedback:
    skip_paragraphs: list[str] = field(default_factory=list)
    memorable: str = ""
    emotional_moment: str = ""
    want_next: bool = True
    feels_repetitive: bool = False
    raw_feedback: str = ""

    def summary(self) -> str:
        parts = []
        if self.want_next:
            parts.append("[OK] 读者想继续看")
        else:
            parts.append("[WARN] 读者不想继续")
        if self.feels_repetitive:
            parts.append("[WARN] 读者感觉重复")
        if self.emotional_moment:
            parts.append(f"[OK] 情绪波动: {self.emotional_moment[:60]}")
        if self.memorable:
            parts.append(f"[OK] 记忆点: {self.memorable[:60]}")
        return " | ".join(parts)


class ReaderEvaluator:
    """模拟读者视角，独立于作者和编辑"""

    # 问题6: 改用 JSON 结构化输出,便于精确解析
    EVAL_PROMPT = """你是一个读者,刚看完这章。你不是编辑,不用分析技术问题。
你只是一个普通的网文读者。请诚实回答,输出严格按 JSON 格式:

{
  "skip_paragraphs": ["想跳过的段落描述,没有则空数组"],
  "memorable": "这章看完记住了什么(什么都记不住就写'没记住什么')",
  "emotional_moment": "有情绪波动的瞬间(紧张/好笑/爽/甜/难受/感动等,没有则写'无')",
  "want_next": true,
  "feels_repetitive": false
}

要求:
- want_next: 想看下一章为 true,不太想/不想为 false
- feels_repetitive: 和上一章比感觉重复为 true,否则 false
- 只输出 JSON,不要 markdown 代码块或额外说明
- 说真话,不用客气"""

    def __init__(self, gateway: DeepSeekGateway):
        self.gateway = gateway

    async def evaluate(self, content: str, chapter_num: int | None = None) -> ReaderFeedback:
        result, _ = await self.gateway.generate(
            system_prompt=self.EVAL_PROMPT,
            user_prompt=f"以下是一章小说正文，请以读者身份评价：\n\n{content[:4000]}",
            temperature=0.9,
            max_tokens=1024,
            chapter_num=chapter_num,
        )
        return self._parse(result)

    def _parse(self, text: str) -> ReaderFeedback:
        """问题6: 优先用 JSON 解析,失败时回退到关键词解析

        Returns:
            ReaderFeedback 解析结果
        """
        # 优先尝试 JSON 解析
        fb = self._parse_json(text)
        if fb is not None:
            fb.raw_feedback = text
            return fb

        # 回退到关键词解析(向后兼容旧格式输出)
        logger.debug("reader_eval JSON 解析失败,回退到关键词解析")
        return self._parse_legacy(text)

    def _parse_json(self, text: str) -> ReaderFeedback | None:
        """问题6: 用 JSON 格式解析读者反馈

        Returns:
            ReaderFeedback 或 None(解析失败时)
        """
        try:
            text_stripped = text.strip()
            # 去除 markdown 代码块包裹
            if text_stripped.startswith("```"):
                lines = text_stripped.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                text_stripped = "\n".join(lines).strip()

            data = json.loads(text_stripped)
            if not isinstance(data, dict):
                return None

            fb = ReaderFeedback()
            # skip_paragraphs: list[str]
            sp = data.get("skip_paragraphs", [])
            if isinstance(sp, list):
                fb.skip_paragraphs = [str(p).strip() for p in sp if str(p).strip()]
            elif isinstance(sp, str) and sp.strip():
                fb.skip_paragraphs = [sp.strip()]

            fb.memorable = str(data.get("memorable", "")).strip()
            fb.emotional_moment = str(data.get("emotional_moment", "")).strip()

            # want_next: bool
            want = data.get("want_next", True)
            if isinstance(want, bool):
                fb.want_next = want
            elif isinstance(want, str):
                fb.want_next = want.lower() in ("true", "想", "yes", "1")

            # feels_repetitive: bool
            rep = data.get("feels_repetitive", False)
            if isinstance(rep, bool):
                fb.feels_repetitive = rep
            elif isinstance(rep, str):
                fb.feels_repetitive = rep.lower() in ("true", "有", "yes", "1")

            return fb
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.debug("reader_eval JSON 解析失败: %s", e)
            return None

    def _parse_legacy(self, text: str) -> ReaderFeedback:
        """旧的关键词解析(向后兼容)"""
        fb = ReaderFeedback(raw_feedback=text)

        text_lower = text.lower()
        if any(w in text_lower for w in ["不太想", "不想看", "不想继续", "不想"]):
            fb.want_next = False
        elif any(w in text_lower for w in ["想立刻", "想看", "很想看", "想看下一章", "立刻看"]):
            fb.want_next = True

        has_rep = any(w in text for w in ["有重复", "雷同", "似曾相识", "感觉很重复", "有点重复", "重复了"])
        no_rep = any(w in text for w in ["没有重复", "不重复", "不会重复", "没重复", "不觉得重复", "不一样", "不同"])
        if has_rep and not no_rep:
            fb.feels_repetitive = True

        for marker in ["情绪波动", "紧张", "好笑", "爽", "甜", "难受", "感动", "笑声"]:
            if marker in text:
                fb.emotional_moment = text[text.index(marker):][:80]
                break

        for marker in ["记住了", "印象", "记得"]:
            if marker in text:
                fb.memorable = text[text.index(marker):][:80]
                break

        return fb
