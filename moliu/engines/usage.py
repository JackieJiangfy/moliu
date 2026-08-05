"""Token 用量统计 — 每次 API 调用的记录与预算管理"""

from __future__ import annotations

import datetime
import json
from pathlib import Path


class UsageTracker:
    """记录每次 LLM 调用的 token 消耗，支持预算管理"""

    def __init__(self, log_path: Path, monthly_budget: int = 0):
        self._path = log_path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self.monthly_budget = monthly_budget

    def log(
        self,
        command: str,
        model: str,
        tokens: int,
        chapter_num: int | None = None,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
    ) -> None:
        record = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "command": command,
            "model": model,
            "tokens": tokens,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
        }
        if chapter_num is not None:
            record["chapter_num"] = chapter_num

        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def today(self) -> int:
        return self._sum_since(datetime.datetime.now(datetime.timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0,
        ))

    def this_week(self) -> int:
        now = datetime.datetime.now(datetime.timezone.utc)
        start = now - datetime.timedelta(days=now.weekday())
        return self._sum_since(start.replace(hour=0, minute=0, second=0, microsecond=0))

    def this_month(self) -> int:
        now = datetime.datetime.now(datetime.timezone.utc)
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return self._sum_since(start)

    def by_command(self) -> dict[str, int]:
        result: dict[str, int] = {}
        for record in self._read_all():
            cmd = record.get("command", "unknown")
            result[cmd] = result.get(cmd, 0) + record.get("tokens", 0)
        return result

    def by_chapter(self) -> dict[int, int]:
        result: dict[int, int] = {}
        for record in self._read_all():
            ch = record.get("chapter_num")
            if ch is not None:
                result[ch] = result.get(ch, 0) + record.get("tokens", 0)
        return result

    def budget_status(self) -> str:
        if self.monthly_budget <= 0:
            return "预算未设置"
        used = self.this_month()
        remaining = self.monthly_budget - used
        pct = used / self.monthly_budget * 100
        return f"{used:,} / {self.monthly_budget:,} tokens ({pct:.1f}%)，剩余 {remaining:,}"

    def average_per_chapter(self) -> float:
        by_ch = self.by_chapter()
        if not by_ch:
            return 0.0
        return sum(by_ch.values()) / len(by_ch)

    def _sum_since(self, since: datetime.datetime) -> int:
        total = 0
        since_str = since.isoformat()
        for record in self._read_all():
            if record.get("timestamp", "") >= since_str:
                total += record.get("tokens", 0)
        return total

    def _read_all(self) -> list[dict]:
        if not self._path.exists():
            return []
        records = []
        with open(self._path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        return records
