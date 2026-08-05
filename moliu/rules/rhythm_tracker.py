"""节奏追踪 + 张力评分 — 纯计算，零 API 开销"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class RhythmRecord:
    chapter_num: int
    chapter_type: str = "normal"
    tension_score: int = 5       # 1-10
    opening_style: str = ""      # 对话开场 / 场景开场 / 动作开场 / 内心独白
    closing_style: str = ""      # 悬念钩子 / 情绪收束 / 动作收尾 / 对话收尾
    dialogue_ratio: float = 0.0  # 对话占全文比
    word_count: int = 0
    has_memorable_moment: bool = False
    emotion_tag: str = ""


class RhythmTracker:
    """节奏追踪器 — 每章记录一次，趋势分析"""

    def __init__(self, data_dir: Path):
        data_dir.mkdir(parents=True, exist_ok=True)
        self._file = data_dir / "rhythm_log.jsonl"

    def record(self, record: RhythmRecord) -> None:
        line = json.dumps({
            "chapter_num": record.chapter_num,
            "chapter_type": record.chapter_type,
            "tension_score": record.tension_score,
            "opening_style": record.opening_style,
            "closing_style": record.closing_style,
            "dialogue_ratio": round(record.dialogue_ratio, 2),
            "word_count": record.word_count,
            "has_memorable_moment": record.has_memorable_moment,
            "emotion_tag": record.emotion_tag,
        }, ensure_ascii=False)
        with open(self._file, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def load_all(self) -> list[RhythmRecord]:
        if not self._file.exists():
            return []
        records = []
        with open(self._file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    d = json.loads(line)
                    records.append(RhythmRecord(**d))
        return records

    def check_variety(self, window: int = 5) -> list[str]:
        """检查最近 N 章的多样性，返回告警列表"""
        alerts = []
        records = self.load_all()
        if len(records) < 3:
            return alerts

        recent = records[-window:]

        # 检查开场方式单一
        openings = [r.opening_style for r in recent if r.opening_style]
        if len(openings) >= 3 and len(set(openings)) == 1:
            alerts.append(f"连续 {len(openings)} 章同一开场方式 ({openings[0]})")

        # 检查收尾方式单一
        closings = [r.closing_style for r in recent if r.closing_style]
        if len(closings) >= 3 and len(set(closings)) == 1:
            alerts.append(f"连续 {len(closings)} 章同一收尾方式 ({closings[0]})")

        # 检查无记忆点
        no_memory = [r for r in recent if not r.has_memorable_moment]
        if len(no_memory) >= 2:
            alerts.append(f"连续 {len(no_memory)} 章无记忆点")

        # 检查张力持续低迷
        low_tension = [r for r in recent if r.tension_score < 3]
        if len(low_tension) >= 3:
            alerts.append(f"连续 {len(low_tension)} 章张力 < 3")

        # 检查张力持续过高
        high_tension = [r for r in recent if r.tension_score > 8]
        if len(high_tension) >= 3:
            alerts.append(f"连续 {len(high_tension)} 章张力 > 8，读者需要喘息")

        return alerts

    def tension_curve(self) -> list[int]:
        """返回全书的张力曲线数据"""
        records = self.load_all()
        return [r.tension_score for r in records]


class TensionScorer:
    """张力评分器 — 从文本中快速估算张力值"""

    @staticmethod
    def score(content: str) -> int:
        """
        基于关键词密度估算张力 (1-10)。
        这是快速估算，不是精确分析。
        """
        # 高张力关键词
        high_tension = [
            "突然", "猛地", "危机", "危险", "紧急", "枪", "血",
            "怒吼", "冲", "爆发", "死", "杀",
            "颤抖", "恐惧", "尖叫", "逃跑",
        ]
        # 低张力关键词
        low_tension = [
            "安静", "平静", "慢慢地", "轻松", "微笑", "温馨",
            "聊天", "散步", "阳光", "休息", "茶", "饭",
        ]

        high_count = sum(content.count(w) for w in high_tension)
        low_count = sum(content.count(w) for w in low_tension)

        # 基础分 5
        score = 5
        # 高张力词每个 +0.5
        score += high_count * 0.5
        # 低张力词每个 -0.3
        score -= low_count * 0.3

        return max(1, min(10, int(score)))

    @staticmethod
    def detect_opening(content: str) -> str:
        """检测开场方式"""
        first_100 = content[:100]
        if '"' in first_100 or '"' in first_100 or "'" in first_100:
            return "对话开场"
        if any(w in first_100 for w in ["想", "思考", "记得", "回忆"]):
            return "内心独白"
        if any(w in first_100 for w in ["跑", "冲", "推", "拉", "打"]):
            return "动作开场"
        return "场景开场"

    @staticmethod
    def detect_closing(content: str) -> str:
        """检测收尾方式"""
        last_200 = content[-200:]
        if "?" in last_200 or "……" in last_200:
            return "悬念钩子"
        if '"' in last_200:
            return "对话收尾"
        if any(w in last_200 for w in ["安静", "平静", "温暖", "微笑", "结束"]):
            return "情绪收束"
        return "动作收尾"

    @staticmethod
    def dialogue_ratio(content: str) -> float:
        """计算对话占比"""
        dialogue_chars = sum(1 for c in content if c in '""“”「」')
        total = len(content) if content else 1
        return dialogue_chars / total
