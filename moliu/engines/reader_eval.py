"""读者体验评估 — 模拟读者视角评估章节质量"""

from __future__ import annotations

from dataclasses import dataclass, field

from moliu.engines.gateway import DeepSeekGateway


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

    EVAL_PROMPT = """你是一个读者，刚看完这章。你不是编辑，不用分析技术问题。
你只是一个普通的网文读者。请诚实回答：

1. 你有想跳过的段落吗？是哪一段？为什么？
2. 这一章看完你记住了什么？（什么都记不住就直说"没记住什么"）
3. 有没有哪个瞬间让你有情绪波动？（紧张/好笑/爽/甜/难受 都算）
4. 你想立刻看下一章吗？（想/不太想/不想）
5. 和上一章比，这章的感觉有没有重复？（有/没有/说不上来）

不用客气，说真话。输出格式随意，但请逐一回答这 5 个问题。"""

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
        fb = ReaderFeedback(raw_feedback=text)

        # 简单关键词解析
        text_lower = text.lower()
        if any(w in text_lower for w in ["不太想", "不想看", "不想继续", "不想"]):
            fb.want_next = False
        elif any(w in text_lower for w in ["想立刻", "想看", "很想看", "想看下一章", "立刻看"]):
            fb.want_next = True

        # 检测重复感: "有重复" / "雷同" = True; "没有重复" / "不重复" = False
        has_rep = any(w in text for w in ["有重复", "雷同", "似曾相识", "感觉很重复", "有点重复", "重复了"])
        no_rep = any(w in text for w in ["没有重复", "不重复", "不会重复", "没重复", "不觉得重复", "不一样", "不同"])
        if has_rep and not no_rep:
            fb.feels_repetitive = True

        # 提取情绪波动
        for marker in ["情绪波动", "紧张", "好笑", "爽", "甜", "难受", "感动", "笑声"]:
            if marker in text:
                fb.emotional_moment = text[text.index(marker):][:80]
                break

        # 提取记忆点
        for marker in ["记住了", "印象", "记得"]:
            if marker in text:
                fb.memorable = text[text.index(marker):][:80]
                break

        return fb
