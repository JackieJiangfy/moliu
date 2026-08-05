"""伏笔智能层 — planted→building→paid 状态机 + 密度/回收提醒"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ForeshadowEntry:
    id: str
    description: str
    status: str = "planted"       # planted | building | paid | dropped
    planted_chapter: int = 0
    last_advanced: int = 0
    paid_chapter: int = 0
    priority: str = "normal"     # high | normal | low
    type: str = "明"              # 明/暗/潜


class ForeshadowManager:
    """伏笔管理器 — 生命周期追踪 + 智能提醒"""

    def __init__(self, data_dir: Path):
        self._file = data_dir / "foreshadow.json"
        self._entries: list[ForeshadowEntry] = []
        self._load()

    def _load(self) -> None:
        if self._file.exists():
            try:
                data = json.loads(self._file.read_text(encoding="utf-8"))
                self._entries = [ForeshadowEntry(**d) for d in data]
            except Exception:
                self._entries = []

    def _save(self) -> None:
        self._file.parent.mkdir(parents=True, exist_ok=True)
        self._file.write_text(
            json.dumps([e.__dict__ for e in self._entries], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def plant(self, description: str, chapter_num: int, priority: str = "normal", type: str = "明") -> str:
        """埋入新伏笔"""
        eid = f"f{len(self._entries) + 1:03d}"
        entry = ForeshadowEntry(
            id=eid, description=description, status="planted",
            planted_chapter=chapter_num, last_advanced=chapter_num,
            priority=priority, type=type,
        )
        self._entries.append(entry)
        self._save()
        return eid

    def advance(self, eid: str, chapter_num: int) -> bool:
        """推进伏笔到 building。返回 True 表示成功。"""
        for e in self._entries:
            if e.id == eid:
                e.status = "building"
                e.last_advanced = chapter_num
                self._save()
                return True
        raise ValueError(f"伏笔 ID '{eid}' 不存在")

    def pay(self, eid: str, chapter_num: int) -> bool:
        """回收伏笔。返回 True 表示成功。"""
        for e in self._entries:
            if e.id == eid:
                e.status = "paid"
                e.paid_chapter = chapter_num
                self._save()
                return True
        raise ValueError(f"伏笔 ID '{eid}' 不存在")

    def drop(self, eid: str, reason: str = "") -> bool:
        """放弃伏笔。返回 True 表示成功。"""
        for e in self._entries:
            if e.id == eid:
                e.status = "dropped"
                self._save()
                return True
        raise ValueError(f"伏笔 ID '{eid}' 不存在")

    def get_active(self) -> list[ForeshadowEntry]:
        return [e for e in self._entries if e.status in ("planted", "building")]

    def check_alerts(self, current_chapter: int) -> list[str]:
        """检查伏笔状态并返回提醒"""
        alerts = []
        active = self.get_active()
        all_entries = self._entries

        # 密度检查
        if len(active) > 8:
            alerts.append(f"伏笔过多 ({len(active)}条活跃), 读者可能遗忘。建议回收或放弃低优先级伏笔")
        if len(all_entries) > 15 and len(active) < 2:
            alerts.append(f"活跃伏笔仅 {len(active)} 条, 故事缺少悬念层次。建议埋入新伏笔")

        # 年龄检查
        for e in active:
            age = current_chapter - e.planted_chapter
            if e.priority == "high" and age > 20:
                alerts.append(f"高优先级伏笔 [{e.id}] '{e.description[:30]}' 已埋 {age} 章未回收。建议近期推进")
            elif e.priority == "normal" and age > 30:
                alerts.append(f"伏笔 [{e.id}] '{e.description[:30]}' 已埋 {age} 章未动。考虑回收或推进")
            elif age > 50:
                alerts.append(f"伏笔 [{e.id}] '{e.description[:30]}' 已埋 {age} 章。建议标记为 dropped 或立即回收")

        # 近期活跃度
        recently_planted = [e for e in self._entries if e.planted_chapter == current_chapter - 1]
        if not recently_planted and current_chapter > 10:
            last_plant = max((e.planted_chapter for e in self._entries), default=0)
            gap = current_chapter - last_plant
            if gap > 10:
                alerts.append(f"已连续 {gap} 章未埋新伏笔。后期缺少钩子吸引读者")

        # 类型分布
        ming = sum(1 for e in active if e.type == "明")
        an = sum(1 for e in active if e.type == "暗")
        if ming == 0 and len(active) > 2:
            alerts.append("无明伏笔。建议埋一条读者能直接察觉的悬念")
        if an == 0 and len(active) > 3:
            alerts.append("无暗伏笔。建议添加细心读者能发现的隐藏线索")

        return alerts

    def summary(self, current_chapter: int) -> str:
        """伏笔状态总览"""
        active = self.get_active()
        lines = [f"伏笔状态: {len(self._entries)} 条总计, {len(active)} 条活跃"]
        for e in sorted(active, key=lambda x: x.planted_chapter):
            age = current_chapter - e.planted_chapter
            lines.append(f"  [{e.id}] {e.status} | 埋于第{e.planted_chapter}章({age}章前) | {e.type}伏笔 | {e.description[:40]}")
        return "\n".join(lines)
