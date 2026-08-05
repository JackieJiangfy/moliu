"""记忆存储单元测试 — JSON 回退模式（离线）"""

from pathlib import Path

import pytest

from moliu.memory.store import MemoryStore


@pytest.fixture
def store(tmp_path):
    return MemoryStore(str(tmp_path))


class TestMemoryStore:
    def test_init_empty(self, store):
        assert store.chapter_count() == 0

    def test_add_and_query_summary(self, store):
        store.add_summary(1, "林小满在食堂收到系统任务", "轻松", ["林小满"])
        assert store.chapter_count() == 1

    def test_query_summaries_bigram(self, store):
        store.add_summary(1, "林小满在食堂收到系统第一个任务", "轻松", ["林小满"])
        store.add_summary(2, "陆沉舟深夜查看后台日志，看到任务完成", "甜", ["陆沉舟"])
        store.add_summary(3, "苏晚渔端着咖啡路过", "轻松", ["苏晚渔"])

        results = store.query_summaries("食堂系统", n=2)
        assert len(results) >= 1
        # 第1章包含"食堂"和"系统"两个bigram，得分最高
        assert "食堂" in results[0] or "系统" in results[0]

    def test_query_summaries_no_match(self, store):
        store.add_summary(1, "林小满在食堂", "轻松", ["林小满"])
        results = store.query_summaries("动物园", n=3)
        assert len(results) == 0

    def test_plot_thread_lifecycle(self, store):
        store.add_plot_thread("f1", "系统真相", "planted", 1)
        store.update_plot_thread("f1", "系统真相逐步揭示", "building", 5)
        active = store.get_active_plot_threads()
        assert len(active) == 1
        assert active[0]["status"] == "building"

    def test_plot_thread_paid_not_active(self, store):
        store.add_plot_thread("f1", "测试", "planted", 1)
        store.update_plot_thread("f1", "测试", "paid", 10)
        active = store.get_active_plot_threads()
        assert len(active) == 0

    def test_notes(self, store):
        store.add_note("n1", "第5章记得回收食堂伏笔", ["伏笔", "食堂"])
        store.add_note("n2", "林默的性格可以更冷一点", ["角色"])
        results = store.query_notes("伏笔食堂", n=2)
        assert len(results) >= 1
        # "食堂" bigram matches note n1
        assert any("伏笔" in r for r in results)

    def test_count(self, store):
        assert store.count("chapter_summaries") == 0
        store.add_summary(1, "test", "ok", [])
        assert store.count("chapter_summaries") == 1

    def test_persistence(self, tmp_path):
        d = str(tmp_path)
        ms1 = MemoryStore(d)
        ms1.add_summary(1, "持久化测试", "轻松", ["A"])
        del ms1

        ms2 = MemoryStore(d)
        assert ms2.chapter_count() == 1
        results = ms2.query_summaries("持久化", n=1)
        assert len(results) == 1
