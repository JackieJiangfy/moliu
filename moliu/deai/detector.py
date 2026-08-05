"""去AI味检测器 — L1词汇层(正则,零API) + L2叙事层(LLM,轻量)"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


# ===== L1: 24 类 AI 套话模式 =====

L1_PATTERNS = [
    # 词级别 (正则可检测)
    ("情绪内化套话", r"心中(涌起|升起|泛起|一阵|满是|充满)"),
    ("机械反应描写", r"不由得|不禁|忍不住|不由地|下意识地"),
    ("比喻堆叠", r"仿佛.{1,20}一般|宛如.{1,20}一般|好像.{1,20}一般"),
    ("眼神过度解读", r"眼中(闪过|掠过|透出|满是|带着|浮现)"),
    ("虚词滥用结构", r"在.{1,20}(之下|之中|之上|之内|之外)"),
    ("句末顿悟", r"[。！？]\s*[A-Z一-鿿]+(意识到|明白了|懂了|清楚了|知道了)"),
    ("场景转换套话", r"与此(同时|同时刻)|另一方(面|边)|画面一(转|切)"),
    ("三段式总结", r"这就是.{1,30}的.{1,10}[。！？]$|^.{1,10}让.{1,20}(明白|知道|意识到)"),
    ("情节预测", r"(这意味着|预示着|代表着).{1,30}[。！？]"),
    ("破折号滥用", None),  # 统计类
    ("感叹号密度", None),
    ("主语单调", None),
    ("情绪标注", r"(生气|悲伤|开心|难过|愤怒|兴奋|紧张|害怕).{0,5}(地说|地想|地问|地道|地回答|地说着)"),
    ("感官三连", r"看到.{1,20}听到.{1,20}(闻到|感到|感觉到)"),
    ("感受解释", r"[。！？]\s*[A-Z一-鿿]+.{1,20}(是因为|源于|由于)"),
    # 句式级 (统计)
    ("过度修饰", None),
    ("重复收尾", None),
    ("独白括号式", r"\(.{1,40}\)"),  # 滥用括号补充心理
    ("被动表达", r"被.{1,10}(所|给|让|叫)"),
    ("泛指虚化", r"(似乎|好像|大概|也许|或许|仿佛).{1,15}(了|一样|似的)"),
    ("强行对仗", r"\w{2,4}(之|的)\w{2,4}[，,]\s*\w{2,4}(之|的)\w{2,4}"),
    ("万能开头", r"^(清晨|傍晚|深夜|黎明|黄昏|午后|午夜|翌日|次日|第二天)"),
    ("万能结尾", r"(夜幕降临|太阳升起|故事还在继续|一切才刚刚开始|新的篇章)[。！？]?$"),
    ("过度拟人", r"风(好像|似乎|仿佛).{1,20}(在说|在诉|在哭|在笑|在吼)"),
]


@dataclass
class DeAIDetectReport:
    tic_counts: dict[str, int] = field(default_factory=dict)   # 各类型命中次数
    hard_violations: list[str] = field(default_factory=list)     # 超硬上限的项
    overall_score: float = 1.0                                    # 0-1, 1=完全人类风
    flagged_paragraphs: list[tuple[str, str, int]] = field(default_factory=list)  # (段落文本, 命中模式, 行号)


class DeAIDetector:
    """去AI味检测。L1 正则零API，L2 语义用LLM。"""

    # 硬上限：超出即 flagged
    HARD_LIMITS = {
        "情绪内化套话": 2,
        "机械反应描写": 3,
        "比喻堆叠": 3,
        "眼神过度解读": 2,
        "虚词滥用结构": 4,
        "句末顿悟": 2,
        "场景转换套话": 3,
        "情绪标注": 3,
        "被动表达": 5,
        "情节预测": 2,
    }

    def detect_l1(self, content: str) -> DeAIDetectReport:
        """L1 词汇层检测（零API）"""
        report = DeAIDetectReport()

        for name, pattern in L1_PATTERNS:
            if pattern is None:
                continue
            matches = re.findall(pattern, content)
            if matches:
                report.tic_counts[name] = len(matches)

        # 统计类
        content_clean = content.replace(" ", "")
        # 破折号密度
        em_dash = content.count("——") + content.count("—")
        if em_dash > len(content_clean) / 150:
            report.tic_counts["破折号滥用"] = em_dash

        # 感叹号密度
        exclam = content.count("！") + content.count("!")
        if exclam > len(content_clean) / 100:
            report.tic_counts["感叹号密度"] = exclam

        # 主语单调 (段落开头同一人名)
        lines = [l.strip() for l in content.split("\n") if l.strip()]
        name_starts = []
        for line in lines:
            m = re.match(r"^([一-鿿]{2,4})", line)
            if m:
                name_starts.append(m.group(1))
        if len(name_starts) >= 5:
            most_common = max(set(name_starts), key=name_starts.count)
            ratio = name_starts.count(most_common) / len(name_starts)
            if ratio > 0.5:
                report.tic_counts["主语单调"] = int(ratio * 100)

        # 标记超限段落
        paragraphs = content.split("\n\n")
        for i, para in enumerate(paragraphs):
            for name, pattern in L1_PATTERNS:
                if pattern and re.search(pattern, para):
                    limit = self.HARD_LIMITS.get(name, 5)
                    count_in_para = len(re.findall(pattern, para))
                    if count_in_para > limit:
                        report.flagged_paragraphs.append((para.strip(), name, i + 1))
                        break

        # 硬上限违规
        for name, count in report.tic_counts.items():
            limit = self.HARD_LIMITS.get(name, 999)
            if count > limit:
                report.hard_violations.append(f"{name}: {count}次 (上限{limit})")

        # 综合评分
        total_issues = sum(report.tic_counts.values())
        penalty = min(total_issues * 0.02, 0.7)
        report.overall_score = max(0.3, 1.0 - penalty)

        return report

    def detect_l2_candidates(self, content: str) -> list[str]:
        """提取疑似 L2 叙事层问题段落（供 LLM 精检）"""
        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
        candidates = []

        for para in paragraphs:
            # Show-then-tell: 动作+解释
            if re.search(r"[。！？]\s*[^。！？]{1,30}(不想|觉得|认为|意识到|知道|明白)", para):
                candidates.append(para)

            # 情感柔化: "有些/略微/稍微"稀释情绪
            elif re.search(r"(有些|略微|稍微|有一点|有点|些许)(生气|难过|开心|紧张|害怕|愤怒|伤心)", para):
                candidates.append(para)

            # 过滤词: "看到/听到/注意到/意识到"开头
            elif re.search(r"^(他|她|它)(看到|听到|注意到|感觉到|闻到)", para):
                candidates.append(para)

        return candidates[:5]  # 最多 5 段给 LLM 精检
