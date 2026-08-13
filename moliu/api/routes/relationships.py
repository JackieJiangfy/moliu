"""角色关系管理 API — 关系 CRUD + 图谱数据

数据存储：data/relationships.json
关系类型：25 种预设（血缘/情感/社交/敌对/特殊），支持自定义
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter()

# 文件读写锁 — 防止并发请求导致读改写丢数据
_rel_lock = asyncio.Lock()


# --- 25 种预设关系类型 ---

PRESET_REL_TYPES: list[dict] = [
    # 血缘关系（正面）
    {"type_name": "父子", "category": "positive", "icon": "👨"},
    {"type_name": "母子", "category": "positive", "icon": "👩"},
    {"type_name": "兄妹", "category": "positive", "icon": "👫"},
    {"type_name": "祖孙", "category": "positive", "icon": "👴"},
    {"type_name": "姻亲", "category": "positive", "icon": "💒"},
    # 情感关系（正面）
    {"type_name": "恋人", "category": "positive", "icon": "❤️"},
    {"type_name": "夫妻", "category": "positive", "icon": "💍"},
    {"type_name": "暗恋", "category": "positive", "icon": "💘", "directed": True},
    {"type_name": "知己", "category": "positive", "icon": "🤝"},
    {"type_name": "前任", "category": "neutral", "icon": "💔"},
    # 社交关系（中立）
    {"type_name": "朋友", "category": "positive", "icon": "😊"},
    {"type_name": "师徒", "category": "neutral", "icon": "📚", "directed": True},
    {"type_name": "同门", "category": "neutral", "icon": "🏫"},
    {"type_name": "盟友", "category": "positive", "icon": "🤝"},
    {"type_name": "从属", "category": "neutral", "icon": "🔗", "directed": True},
    # 敌对关系（负面）
    {"type_name": "仇敌", "category": "negative", "icon": "⚔️"},
    {"type_name": "宿敌", "category": "negative", "icon": "🗡️"},
    {"type_name": "对手", "category": "negative", "icon": "🥊"},
    {"type_name": "叛徒", "category": "negative", "icon": "🔪", "directed": True},
    {"type_name": "对立", "category": "negative", "icon": "⛔"},
    # 特殊关系（中立）
    {"type_name": "主仆", "category": "neutral", "icon": "🔑", "directed": True},
    {"type_name": "转世", "category": "neutral", "icon": "🔄", "directed": True},
    {"type_name": "契约", "category": "neutral", "icon": "📜"},
    {"type_name": "宿命", "category": "neutral", "icon": "⭐"},
    {"type_name": "分身", "category": "neutral", "icon": "👥"},
]


# --- 数据模型 ---

class RelationshipItem(BaseModel):
    id: int = 0
    source_name: str               # 源角色名
    target_name: str               # 目标角色名
    rel_type: str                  # 关系类型（父子/恋人/仇敌...）
    category: str = "neutral"      # positive / neutral / negative
    directed: bool = False         # 是否单向
    intensity: int = 5             # 强度 1-10
    description: str = ""          # 关系说明
    start_chapter: int = 0         # 关系形成章节
    end_chapter: int = 0           # 关系结束章节


class RelationshipCreate(BaseModel):
    source_name: str
    target_name: str
    rel_type: str
    category: str | None = None     # None 表示未选，由预设类型补全；显式传值则尊重用户选择
    directed: bool = False
    intensity: int = 5
    description: str = ""
    start_chapter: int = 0
    end_chapter: int = 0


class RelationshipUpdate(BaseModel):
    source_name: str | None = None
    target_name: str | None = None
    rel_type: str | None = None
    category: str | None = None
    directed: bool | None = None
    intensity: int | None = None
    description: str | None = None
    start_chapter: int | None = None
    end_chapter: int | None = None


class GraphNode(BaseModel):
    id: str           # 用角色名作为 id
    name: str
    faction: str = ""
    role_type: str = ""
    relation_count: int = 0


class GraphEdge(BaseModel):
    id: str
    source: str       # 源节点 id（角色名）
    target: str       # 目标节点 id（角色名）
    rel_type: str
    category: str
    directed: bool
    intensity: int


class GraphData(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class RelTypeItem(BaseModel):
    type_name: str
    category: str
    icon: str = ""
    directed: bool = False


# --- 存储辅助 ---

def _get_rel_path(data_dir: Path) -> Path:
    return data_dir / "relationships.json"


def _get_relationships(data_dir: Path) -> list[dict]:
    path = _get_rel_path(data_dir)
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _save_relationships(data_dir: Path, items: list[dict]) -> None:
    path = _get_rel_path(data_dir)
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_characters_map(data_dir: Path) -> dict[str, dict]:
    """从 data/characters/*.yaml 加载角色名 → {faction, role_type} 映射"""
    chars_dir = data_dir / "characters"
    if not chars_dir.exists():
        return {}
    result = {}
    for f in chars_dir.glob("*.yaml"):
        try:
            data = yaml.safe_load(f.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("name"):
                name = data["name"]
                state = data.get("state")
                faction = data.get("faction") or (
                    state.get("location", "") if isinstance(state, dict) else ""
                )
                result[name] = {
                    "faction": faction,
                    "role_type": data.get("role_type", ""),
                }
        except Exception:
            continue
    return result


# --- 路由 ---

@router.get("/relationships", response_model=list[RelationshipItem])
async def list_relationships(request: Request):
    """获取所有关系"""
    cfg = request.app.state.config
    items = _get_relationships(cfg.resolve_data_dir())
    return [RelationshipItem(**e) for e in items]


@router.post("/relationships", response_model=RelationshipItem, status_code=201)
async def create_relationship(request: Request, body: RelationshipCreate):
    """新建关系"""
    cfg = request.app.state.config
    async with _rel_lock:
        items = _get_relationships(cfg.resolve_data_dir())

        # 查预设类型，自动补 category 和 directed
        preset = next((p for p in PRESET_REL_TYPES if p["type_name"] == body.rel_type), None)
        category = body.category
        directed = body.directed
        if preset:
            # 只在用户未显式指定（None）时用预设补全，避免覆盖用户明确选的 neutral
            if category is None:
                category = preset.get("category", "neutral")
            if not directed and preset.get("directed"):
                directed = True

        new_id = max((e.get("id", 0) for e in items), default=0) + 1
        new_item = {
            "id": new_id,
            "source_name": body.source_name,
            "target_name": body.target_name,
            "rel_type": body.rel_type,
            "category": category or "neutral",
            "directed": directed,
            "intensity": body.intensity,
            "description": body.description,
            "start_chapter": body.start_chapter,
            "end_chapter": body.end_chapter,
        }
        items.append(new_item)
        _save_relationships(cfg.resolve_data_dir(), items)
    return RelationshipItem(**new_item)


@router.put("/relationships/{rel_id}", response_model=RelationshipItem)
async def update_relationship(request: Request, rel_id: int, body: RelationshipUpdate):
    """更新关系"""
    cfg = request.app.state.config
    async with _rel_lock:
        items = _get_relationships(cfg.resolve_data_dir())

        for e in items:
            if e.get("id") == rel_id:
                if body.source_name is not None: e["source_name"] = body.source_name
                if body.target_name is not None: e["target_name"] = body.target_name
                if body.rel_type is not None: e["rel_type"] = body.rel_type
                if body.category is not None: e["category"] = body.category
                if body.directed is not None: e["directed"] = body.directed
                if body.intensity is not None: e["intensity"] = body.intensity
                if body.description is not None: e["description"] = body.description
                if body.start_chapter is not None: e["start_chapter"] = body.start_chapter
                if body.end_chapter is not None: e["end_chapter"] = body.end_chapter
                _save_relationships(cfg.resolve_data_dir(), items)
                return RelationshipItem(**e)

        raise HTTPException(status_code=404, detail=f"关系 {rel_id} 不存在")


@router.delete("/relationships/{rel_id}", status_code=204)
async def delete_relationship(request: Request, rel_id: int):
    """删除关系"""
    cfg = request.app.state.config
    async with _rel_lock:
        items = _get_relationships(cfg.resolve_data_dir())

        for i, e in enumerate(items):
            if e.get("id") == rel_id:
                items.pop(i)
                _save_relationships(cfg.resolve_data_dir(), items)
                return

        raise HTTPException(status_code=404, detail=f"关系 {rel_id} 不存在")


@router.get("/relationships/types", response_model=list[RelTypeItem])
async def list_rel_types():
    """获取预设关系类型（25 种）"""
    return [
        RelTypeItem(
            type_name=p["type_name"],
            category=p["category"],
            icon=p.get("icon", ""),
            directed=p.get("directed", False),
        )
        for p in PRESET_REL_TYPES
    ]


@router.get("/graph", response_model=GraphData)
async def get_graph(request: Request):
    """获取图谱数据 — 节点（角色）+ 边（关系）

    供前端 ECharts 力导向图直接渲染。
    """
    cfg = request.app.state.config
    data_dir = cfg.resolve_data_dir()

    relationships = _get_relationships(data_dir)
    chars_map = _load_characters_map(data_dir)

    # 统计每个角色的关联数
    rel_count: dict[str, int] = {}
    for rel in relationships:
        rel_count[rel["source_name"]] = rel_count.get(rel["source_name"], 0) + 1
        rel_count[rel["target_name"]] = rel_count.get(rel["target_name"], 0) + 1

    # 构建节点（关系中出现过的角色，按首次出现顺序保序，再按关联数降序排）
    node_names = list(dict.fromkeys(
        [rel["source_name"] for rel in relationships] + [rel["target_name"] for rel in relationships]
    ))
    node_names.sort(key=lambda n: rel_count.get(n, 0), reverse=True)

    nodes = []
    for name in node_names:
        char_info = chars_map.get(name, {})
        nodes.append(GraphNode(
            id=name,
            name=name,
            faction=char_info.get("faction", ""),
            role_type=char_info.get("role_type", ""),
            relation_count=rel_count.get(name, 0),
        ))

    edges = []
    for rel in relationships:
        edges.append(GraphEdge(
            id=str(rel["id"]),
            source=rel["source_name"],
            target=rel["target_name"],
            rel_type=rel["rel_type"],
            category=rel.get("category", "neutral"),
            directed=rel.get("directed", False),
            intensity=rel.get("intensity", 5),
        ))

    return GraphData(nodes=nodes, edges=edges)
