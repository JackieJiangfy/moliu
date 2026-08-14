"""Novel API CRUD 测试

覆盖 /api/v1/novels 端点的增删改查:
- 创建小说 → 自动建目录
- 列出所有小说
- 查询单个小说
- 更新小说信息
- 删除小说 → 同时清目录
- 404 错误
- 索引自增 ID
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from moliu.api import create_app
from moliu.config import Config


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    """构造 TestClient,使用 tmp_path 作为项目根"""
    cfg = Config()
    cfg.project_dir = tmp_path
    app = create_app(cfg)
    return TestClient(app)


class TestNovelsCreate:
    """POST /api/v1/novels"""

    def test_create_novel_returns_201(self, client, tmp_path):
        resp = client.post("/api/v1/novels", json={
            "title": "测试小说",
            "genre": "都市",
            "premise": "一个测试故事",
        })
        assert resp.status_code == 201
        body = resp.json()
        assert body["title"] == "测试小说"
        assert body["genre"] == "都市"
        assert body["premise"] == "一个测试故事"
        assert body["status"] == "planned"
        assert body["id"] >= 1

    def test_create_novel_initializes_directories(self, client, tmp_path):
        """创建小说后应自动建好子目录"""
        resp = client.post("/api/v1/novels", json={"title": "目录测试"})
        novel_id = resp.json()["id"]

        cfg = Config()
        cfg.project_dir = tmp_path
        data_dir = cfg.resolve_novel_data_dir(novel_id)
        assert data_dir.exists()
        assert (data_dir / "characters").is_dir()
        assert (data_dir / "outlines").is_dir()
        assert (data_dir / "volumes").is_dir()
        assert (data_dir / "world").is_dir()
        # 章节输出目录
        output_dir = cfg.resolve_novel_output_dir(novel_id)
        assert output_dir.is_dir()

    def test_create_novel_initializes_volume_index(self, client, tmp_path):
        """创建后应同时写入空的卷索引"""
        resp = client.post("/api/v1/novels", json={"title": "卷索引测试"})
        novel_id = resp.json()["id"]

        cfg = Config()
        cfg.project_dir = tmp_path
        vol_idx = cfg.resolve_novel_data_dir(novel_id) / "volumes" / "index.json"
        assert vol_idx.exists()
        data = json.loads(vol_idx.read_text(encoding="utf-8"))
        assert data.get("novel_title") == "卷索引测试"

    def test_create_multiple_novels_assigns_increasing_ids(self, client):
        """连续创建多本小说,ID 应自增"""
        resp1 = client.post("/api/v1/novels", json={"title": "小说1"})
        resp2 = client.post("/api/v1/novels", json={"title": "小说2"})
        resp3 = client.post("/api/v1/novels", json={"title": "小说3"})

        id1 = resp1.json()["id"]
        id2 = resp2.json()["id"]
        id3 = resp3.json()["id"]
        assert id2 == id1 + 1
        assert id3 == id2 + 1

    def test_create_novel_persists_index(self, client, tmp_path):
        """创建后索引应持久化到 index.json"""
        client.post("/api/v1/novels", json={"title": "持久化测试"})
        cfg = Config()
        cfg.project_dir = tmp_path
        idx_path = cfg.resolve_novel_index_path()
        assert idx_path.exists()
        data = json.loads(idx_path.read_text(encoding="utf-8"))
        assert len(data["novels"]) == 1
        assert data["novels"][0]["title"] == "持久化测试"
        assert data["next_id"] == 2


class TestNovelsList:
    """GET /api/v1/novels"""

    def test_list_empty(self, client):
        """无小说时返回空列表"""
        resp = client.get("/api/v1/novels")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_returns_all(self, client):
        """列出所有已创建的小说"""
        client.post("/api/v1/novels", json={"title": "甲"})
        client.post("/api/v1/novels", json={"title": "乙"})
        client.post("/api/v1/novels", json={"title": "丙"})

        resp = client.get("/api/v1/novels")
        assert resp.status_code == 200
        titles = [n["title"] for n in resp.json()]
        assert titles == ["甲", "乙", "丙"]


class TestNovelsGet:
    """GET /api/v1/novels/{id}"""

    def test_get_existing(self, client):
        """获取存在的小说"""
        create_resp = client.post("/api/v1/novels", json={"title": "存在测试"})
        novel_id = create_resp.json()["id"]

        resp = client.get(f"/api/v1/novels/{novel_id}")
        assert resp.status_code == 200
        assert resp.json()["title"] == "存在测试"

    def test_get_not_found(self, client):
        """查询不存在的小说 → 404"""
        resp = client.get("/api/v1/novels/9999")
        assert resp.status_code == 404
        assert "9999" in resp.json()["detail"]


class TestNovelsUpdate:
    """PUT /api/v1/novels/{id}"""

    def test_update_title(self, client):
        novel_id = client.post("/api/v1/novels", json={"title": "原名"}).json()["id"]
        resp = client.put(f"/api/v1/novels/{novel_id}", json={"title": "新名"})
        assert resp.status_code == 200
        assert resp.json()["title"] == "新名"

    def test_update_status(self, client):
        novel_id = client.post("/api/v1/novels", json={"title": "状态测试"}).json()["id"]
        resp = client.put(f"/api/v1/novels/{novel_id}", json={"status": "active"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "active"

    def test_update_partial(self, client):
        """只更新部分字段,其它字段保留原值"""
        novel_id = client.post("/api/v1/novels", json={
            "title": "原标题", "genre": "都市"
        }).json()["id"]
        resp = client.put(f"/api/v1/novels/{novel_id}", json={"genre": "玄幻"})
        body = resp.json()
        assert body["genre"] == "玄幻"
        assert body["title"] == "原标题"  # 未改

    def test_update_changes_updated_at(self, client):
        """更新后 updated_at 应变"""
        create_resp = client.post("/api/v1/novels", json={"title": "时间测试"})
        novel_id = create_resp.json()["id"]
        original_updated = create_resp.json()["updated_at"]

        # 更新
        resp = client.put(f"/api/v1/novels/{novel_id}", json={"title": "新"})
        assert resp.json()["updated_at"] != original_updated

    def test_update_not_found(self, client):
        resp = client.put("/api/v1/novels/9999", json={"title": "x"})
        assert resp.status_code == 404


class TestNovelsDelete:
    """DELETE /api/v1/novels/{id}"""

    def test_delete_existing(self, client, tmp_path):
        novel_id = client.post("/api/v1/novels", json={"title": "删除测试"}).json()["id"]
        resp = client.delete(f"/api/v1/novels/{novel_id}")
        assert resp.status_code == 204

        # 索引里已无
        assert client.get(f"/api/v1/novels/{novel_id}").status_code == 404

    def test_delete_removes_data_dir(self, client, tmp_path):
        """删除小说应同时删除其数据目录"""
        novel_id = client.post("/api/v1/novels", json={"title": "目录删除"}).json()["id"]
        cfg = Config()
        cfg.project_dir = tmp_path
        data_dir = cfg.resolve_novel_data_dir(novel_id)
        assert data_dir.exists()

        client.delete(f"/api/v1/novels/{novel_id}")
        assert not data_dir.exists()

    def test_delete_not_found(self, client):
        resp = client.delete("/api/v1/novels/9999")
        assert resp.status_code == 404

    def test_delete_does_not_affect_others(self, client):
        """删一本不影响其它小说"""
        id1 = client.post("/api/v1/novels", json={"title": "甲"}).json()["id"]
        id2 = client.post("/api/v1/novels", json={"title": "乙"}).json()["id"]

        client.delete(f"/api/v1/novels/{id1}")

        # 乙还在
        assert client.get(f"/api/v1/novels/{id2}").status_code == 200
        # 列表里只剩乙
        titles = [n["title"] for n in client.get("/api/v1/novels").json()]
        assert titles == ["乙"]
