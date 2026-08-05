"""伏笔管理器单元测试 — 全部离线"""

from pathlib import Path

import pytest
from moliu.rules.foreshadow_watch import ForeshadowManager


class TestForeshadowManager:
    @pytest.fixture
    def fm(self, tmp_path):
        return ForeshadowManager(tmp_path)

    def test_plant_and_get_active(self, fm):
        fm.plant("系统真相", 1)
        active = fm.get_active()
        assert len(active) == 1
        assert active[0].description == "系统真相"
        assert active[0].status == "planted"

    def test_advance_and_pay(self, fm):
        eid = fm.plant("匿名短信", 3)
        fm.advance(eid, 8)
        assert fm.get_active()[0].status == "building"
        fm.pay(eid, 15)
        assert len(fm.get_active()) == 0

    def test_drop(self, fm):
        eid = fm.plant("废弃伏笔", 1)
        fm.drop(eid)
        assert len(fm.get_active()) == 0

    def test_density_alert(self, fm):
        for i in range(9):
            fm.plant(f"伏笔{i}", 1)
        alerts = fm.check_alerts(1)
        assert any("过多" in a for a in alerts)

    def test_age_alert(self, fm):
        fm.plant("旧伏笔", 1, priority="high")
        alerts = fm.check_alerts(25)
        assert any("旧伏笔" in a for a in alerts)

    def test_no_plant_gap_alert(self, fm):
        fm.plant("只有一个", 1)
        alerts = fm.check_alerts(20)
        assert any("未埋新伏笔" in a or "缺少" in a or "没有" in a for a in alerts)

    def test_summary(self, fm):
        fm.plant("测试伏笔", 5, type="暗")
        s = fm.summary(10)
        assert "测试伏笔" in s
        assert "5章" in s or "5章前" in s or "暗伏笔" in s

    def test_persistence(self, tmp_path):
        fm1 = ForeshadowManager(tmp_path)
        fm1.plant("持久化测试", 1)
        del fm1

        fm2 = ForeshadowManager(tmp_path)
        assert len(fm2.get_active()) == 1

    def test_multiple_lifecycle(self, fm):
        a = fm.plant("伏笔A", 1)
        b = fm.plant("伏笔B", 3, priority="high", type="暗")
        fm.advance(a, 5)
        fm.pay(a, 10)
        fm.advance(b, 8)
        active = fm.get_active()
        assert len(active) == 1
        assert active[0].id == b
