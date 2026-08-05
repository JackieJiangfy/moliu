"""去AI味改写器 — LLM 重写标记段落，保持情节不变"""

from __future__ import annotations

from moliu.engines.gateway import DeepSeekGateway


class DeAIRewriter:
    """改写 AI 味段落。只改表达，不改情节/爽点/钩子/数值。"""

    REWRITE_SYSTEM = """你是专业文字编辑。请重写以下段落，去掉AI写作痕迹。

改写规则:
1. 变化句式节奏 — 交替使用短句和长句，打破主谓宾的单调
2. 去掉过度解释 — 读者很聪明，不需要解释"为什么"。删掉"是因为""意味着"等解释句
3. 用行动代替情绪标注 — 不写"他生气地说"，改写具体的动作或环境。"他放下杯子。很轻。"
4. 随机化段落长度 — 不要每段3-5行均匀分布，偶尔用1行段落制造节奏
5. 删掉所有"仿佛...一般""心中涌起""不由得""眼中闪过"等AI套话
6. 保持角色说话风格和情节关键信息不变
7. 保持字数在原文的±10%范围内
8. 只输出改写后的文本，不要加任何说明"""

    def __init__(self, gateway: DeepSeekGateway):
        self.gateway = gateway

    async def rewrite_paragraph(self, text: str, chapter_num: int | None = None, retries: int = 2) -> str:
        """重写单个段落。最多 retries 次尝试，失败返回原文。"""
        for attempt in range(retries):
            try:
                result, _ = await self.gateway.generate(
                    system_prompt=self.REWRITE_SYSTEM,
                    user_prompt=f"请重写以下段落：\n\n{text}",
                    temperature=0.5,
                    max_tokens=min(len(text) * 3, 2048),
                    chapter_num=chapter_num,
                )
                return result.strip()
            except Exception:
                if attempt == retries - 1:
                    return text
        return text

    async def rewrite_flagged(
        self,
        content: str,
        flagged: list[tuple[str, str, int]],
        chapter_num: int | None = None,
    ) -> str:
        """重写标记段落并替换回原文"""
        if not flagged:
            return content

        paragraphs = content.split("\n\n")
        rewritten_count = 0

        for para_text, pattern, line_num in flagged:
            if rewritten_count >= 5:  # 最多改 5 段，避免过度改写
                break
            try:
                new_para = await self.rewrite_paragraph(para_text, chapter_num=chapter_num)
                if new_para and len(new_para) > len(para_text) * 0.5:
                    # 在原文中找到对应段落并替换
                    for i, p in enumerate(paragraphs):
                        if p.strip() == para_text:
                            paragraphs[i] = new_para
                            rewritten_count += 1
                            break
            except Exception:
                continue

        return "\n\n".join(paragraphs)
