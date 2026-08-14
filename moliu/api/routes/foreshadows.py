"""伏笔管理 API — 通用 CRUD"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from moliu.api.locks import novel_lock

router = APIRouter()


class ForeshadowItem(BaseModel):
    id: int = 0
    description: str = ""
    type: str = "mystery"       # mystery / character / object / world
    priority: str = "normal"    # high / normal / low
    status: str = "planted"     # planted / building / paid
    planted_chapter: int = 0
    paid_chapter: int = 0
    notes: str = ""


class ForeshadowCreate(BaseModel):
    description: str
    type: str = "mystery"
    priority: str = "normal"
    planted_chapter: int = 0
    notes: str = ""


class ForeshadowUpdate(BaseModel):
    description: str | None = None
    type: str | None = None
    priority: str | None = None
    status: str | None = None
    paid_chapter: int | None = None
    notes: str | None = None


def _get_foreshadows(data_dir: Path) -> list[dict]:
    path = data_dir / "foreshadow.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _save_foreshadows(data_dir: Path, items: list[dict]) -> None:
    path = data_dir / "foreshadow.json"
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


@router.get("/foreshadows", response_model=list[ForeshadowItem])
async def list_foreshadows(
    request: Request,
    status: str | None = None,
    novel_id: int = Query(1, description="小说ID"),
):
    """获取伏笔列表"""
    cfg = request.app.state.config
    items = _get_foreshadows(cfg.resolve_data_dir(novel_id))

    if status:
        items = [e for e in items if e.get("status") == status]

    return [
        ForeshadowItem(
            id=e.get("id", 0),
            description=e.get("description", ""),
            type=e.get("type", "mystery"),
            priority=e.get("priority", "normal"),
            status=e.get("status", "planted"),
            planted_chapter=e.get("planted_chapter", 0),
            paid_chapter=e.get("paid_chapter", 0),
            notes=e.get("notes", ""),
        )
        for e in items
    ]


@router.post("/foreshadows", response_model=ForeshadowItem, status_code=201)
async def create_foreshadow(
    request: Request,
    body: ForeshadowCreate,
    novel_id: int = Query(1, description="小说ID"),
):
    """埋入伏笔"""
    cfg = request.app.state.config
    async with novel_lock(novel_id):
        items = _get_foreshadows(cfg.resolve_data_dir(novel_id))

        new_id = max((e.get("id", 0) for e in items), default=0) + 1
        new_item = {
            "id": new_id,
            "description": body.description,
            "type": body.type,
            "priority": body.priority,
            "status": "planted",
            "planted_chapter": body.planted_chapter,
            "paid_chapter": 0,
            "notes": body.notes,
        }
        items.append(new_item)
        _save_foreshadows(cfg.resolve_data_dir(novel_id), items)

    return ForeshadowItem(**new_item)


@router.put("/foreshadows/{foreshadow_id}", response_model=ForeshadowItem)
async def update_foreshadow(
    request: Request,
    foreshadow_id: int,
    body: ForeshadowUpdate,
    novel_id: int = Query(1, description="小说ID"),
):
    """更新伏笔（推进或回收）"""
    cfg = request.app.state.config
    async with novel_lock(novel_id):
        items = _get_foreshadows(cfg.resolve_data_dir(novel_id))

        for e in items:
            if e.get("id") == foreshadow_id:
                if body.description is not None:
                    e["description"] = body.description
                if body.type is not None:
                    e["type"] = body.type
                if body.priority is not None:
                    e["priority"] = body.priority
                if body.status is not None:
                    e["status"] = body.status
                if body.paid_chapter is not None:
                    e["paid_chapter"] = body.paid_chapter
                if body.notes is not None:
                    e["notes"] = body.notes

                _save_foreshadows(cfg.resolve_data_dir(novel_id), items)
                return ForeshadowItem(**e)

        raise HTTPException(status_code=404, detail=f"伏笔 {foreshadow_id} 不存在")


@router.delete("/foreshadows/{foreshadow_id}", status_code=204)
async def delete_foreshadow(
    request: Request,
    foreshadow_id: int,
    novel_id: int = Query(1, description="小说ID"),
):
    """删除伏笔"""
    cfg = request.app.state.config
    async with novel_lock(novel_id):
        items = _get_foreshadows(cfg.resolve_data_dir(novel_id))

        for i, e in enumerate(items):
            if e.get("id") == foreshadow_id:
                items.pop(i)
                _save_foreshadows(cfg.resolve_data_dir(novel_id), items)
                return

        raise HTTPException(status_code=404, detail=f"伏笔 {foreshadow_id} 不存在")