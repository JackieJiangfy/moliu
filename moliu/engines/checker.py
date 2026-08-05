"""一致性检查引擎 — AI 检查 AI：角色锚点 + 世界观规则 + 剧情逻辑 + 叙事质量"""

from __future__ import annotations

from dataclasses import dataclass, field

from moliu.data.schemas import CharacterCard, NarratorCard, WorldSetting
from moliu.engines.gateway import DeepSeekGateway


@dataclass
class CheckIssue:
    severity: str  # "fatal" | "warning" | "info"
    category: str  # "character_voice" | "world_rules" | "plot_logic" | "narrative_quality"
    description: str
    evidence: str  # 原文引用
    suggestion: str = ""


@dataclass
class CheckReport:
    passed: bool = True
    fatal_count: int = 0
    warning_count: int = 0
    info_count: int = 0
    issues: list[CheckIssue] = field(default_factory=list)

    def to_text(self) -> str:
        if not self.issues:
            return "一致性检查：全部通过。"
        lines = [f"一致性检查报告: {self.fatal_count}致命 {self.warning_count}警告 {self.info_count}提示"]
        for issue in self.issues:
            icon = {"fatal": "[FAIL]", "warning": "[WARN]", "info": "[INFO]"}[issue.severity]
            lines.append(f"\n{icon} [{issue.category}] {issue.description}")
            if issue.evidence:
                lines.append(f"  原文: {issue.evidence[:120]}")
            if issue.suggestion:
                lines.append(f"  建议: {issue.suggestion}")
        return "\n".join(lines)


class ConsistencyChecker:
    """一致性检查 — 使用独立 LLM 调用检查 AI 生成的章节"""

    CHECK_PROMPT = """你是小说质量审查员。请逐项检查以下章节，输出结构化报告。

## 检查项

### 1. 角色说话风格检查
- 每个角色的对话是否与其设定的说话风格一致？
- 是否出现了该角色的"禁用词"？
- 不同角色的对话是否可以互相区分（换读法测试：把名字遮住，能看出谁在说话吗）？

### 2. 世界观规则检查
- 是否违反了世界观中列出的"硬约束"？
- 角色能力/道具使用是否与当前状态一致？
- 时间线、地点是否与前文一致？

### 3. 剧情逻辑检查
- 有没有"突然出现/突然消失"的角色？
- 事件因果关系是否合理？
- 角色的行为是否符合其动机和底线？

### 4. 叙事质量检查
- 是否出现明显的 AI 套话？
- 是否有"写出来但没推进"的冗余段落？
- 章节开头是否承接了上一章的情绪？
- 结尾是否有吸引继续阅读的钩子？

## 输出格式
逐条列出发现的问题，每条包含:
- 严重度: fatal / warning / info
- 类别: character_voice / world_rules / plot_logic / narrative_quality
- 问题描述
- 原文证据（直接引用）

如果没有发现问题，输出 "PASS: 未发现一致性问题。"

=== 检查开始 ===
"""

    def __init__(self, gateway: DeepSeekGateway):
        self.gateway = gateway

    async def check(
        self,
        content: str,
        characters: list[CharacterCard],
        world: WorldSetting,
        narrator: NarratorCard | None = None,
        chapter_num: int | None = None,
    ) -> CheckReport:
        """运行一致性检查"""
        # 组装角色上下文
        char_context = "\n\n".join(c.to_context() for c in characters)
        world_context = world.to_context()
        narrator_context = narrator.to_context() if narrator else ""

        user_prompt = f"""
## 角色设定
{char_context}

## 世界观
{world_context}

## 叙述者约束
{narrator_context}

## 待检查章节正文
---
{content}
---

请逐项检查并输出报告。
"""

        result, _ = await self.gateway.generate(
            system_prompt=self.CHECK_PROMPT,
            user_prompt=user_prompt,
            temperature=0.1,
            max_tokens=2048,
            chapter_num=chapter_num,
        )

        return self._parse_report(result)

    def _parse_report(self, text: str) -> CheckReport:
        """解析 LLM 输出的检查报告"""
        if "PASS" in text and "未发现问题" in text:
            return CheckReport(passed=True)

        report = CheckReport(passed=True)
        lines = text.split("\n")
        current = None

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # 检测严重度标记
            severity = None
            if "fatal" in line.lower() or "[FAIL]" in line or "致命" in line:
                severity = "fatal"
            elif "warning" in line.lower() or "[WARN]" in line or "警告" in line:
                severity = "warning"
            elif "info" in line.lower() or "[INFO]" in line or "提示" in line:
                severity = "info"

            if severity:
                category = "narrative_quality"
                if "角色" in line or "说话" in line or "对话" in line:
                    category = "character_voice"
                elif "世界" in line or "规则" in line or "设定" in line:
                    category = "world_rules"
                elif "逻辑" in line or "情节" in line or "因果" in line:
                    category = "plot_logic"

                report.issues.append(CheckIssue(
                    severity=severity,
                    category=category,
                    description=line,
                    evidence="",
                ))

                if severity == "fatal":
                    report.fatal_count += 1
                    report.passed = False
                elif severity == "warning":
                    report.warning_count += 1
                else:
                    report.info_count += 1

        return report


class AnchoredPreChecker:
    """角色锚点预检 — 正文生成前检查节拍是否违背角色锚点"""

    PRE_CHECK_PROMPT = """你是角色一致性顾问。检查本章节拍是否会违背角色锚点。

## 角色锚点
{character_anchors}

## 本章节拍
{beat}

## 分析
1. 本章节拍中角色的行为是否违背了以上锚点？
2. 如果违背，是"合理的角色成长"还是"崩人设"？

输出格式:
- 如果一致: "OK: 锚点一致"
- 如果成长: "GROWTH: [角色名] 的 [行为] 是合理成长，因为 [原因]"
- 如果崩人设: "BROKEN: [角色名] 的 [行为] 违背了 [锚点]。建议: [调整方案]"
"""

    def __init__(self, gateway: DeepSeekGateway):
        self.gateway = gateway

    async def check(
        self, beat: str, characters: list[CharacterCard],
        chapter_num: int | None = None,
    ) -> tuple[bool, str]:
        """返回 (是否通过, 分析文本)"""
        anchors = "\n\n".join(
            f"【{c.name}】{c.one_line_pitch}\n"
            f"核心欲望: {c.core.core_desire}\n"
            f"深层恐惧: {c.core.deep_fear}\n"
            f"底线: {' / '.join(c.core.value_bottom_line)}"
            for c in characters
        )

        result, _ = await self.gateway.generate(
            system_prompt="你是角色一致性顾问。",
            user_prompt=self.PRE_CHECK_PROMPT.format(
                character_anchors=anchors, beat=beat,
            ),
            temperature=0.1,
            max_tokens=512,
            chapter_num=chapter_num,
        )

        passed = result.strip().startswith("OK") or result.strip().startswith("GROWTH")
        return passed, result.strip()
