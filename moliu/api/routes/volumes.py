"""卷管理 API — 通用 CRUD"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from moliu.data.schemas import VolumeIndex, VolumePlan

router = APIRouter()


def _get_index(request: Request) -> VolumeIndex:
    cfg = request.app.state.config
    path = cfg.resolve_data_dir() / "volumes" / "index.json"
    if not path.exists():
        return VolumeIndex()
    return VolumeIndex.from_json(path)


def _save_index(request: Request, index: VolumeIndex) -> None:
    cfg = request.app.state.config
    path = cfg.resolve_data_dir() / "volumes" / "index.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    index.to_json(path)


# --- Request/Response 模型 ---

class VolumeCreate(BaseModel):
    name: str
    subtitle: str = ""
    chapter_start: int = 1
    chapter_end: int = 0
    summary: str = ""


class VolumeUpdate(BaseModel):
    name: str | None = None
    subtitle: str | None = None
    chapter_start: int | None = None
    chapter_end: int | None = None
    summary: str | None = None
    status: str | None = None


class VolumeResponse(BaseModel):
    id: int
    name: str
    subtitle: str
    chapter_start: int
    chapter_end: int
    summary: str
    status: str
    created_at: str
    updated_at: str


# --- Routes ---

@router.get("/volumes", response_model=list[VolumeResponse])
async def list_volumes(request: Request):
    """获取所有卷"""
    index = _get_index(request)
    return [
        VolumeResponse(
            id=v.id,
            name=v.name,
            subtitle=v.subtitle,
            chapter_start=v.chapter_start,
            chapter_end=v.chapter_end,
            summary=v.summary,
            status=v.status,
            created_at=v.created_at,
            updated_at=v.updated_at,
        )
        for v in sorted(index.volumes, key=lambda x: x.chapter_start)
    ]


@router.get("/volumes/{volume_id}", response_model=VolumeResponse)
async def get_volume(request: Request, volume_id: int):
    """获取单个卷"""
    index = _get_index(request)
    for v in index.volumes:
        if v.id == volume_id:
            return VolumeResponse(
                id=v.id, name=v.name, subtitle=v.subtitle,
                chapter_start=v.chapter_start, chapter_end=v.chapter_end,
                summary=v.summary, status=v.status,
                created_at=v.created_at, updated_at=v.updated_at,
            )
    raise HTTPException(status_code=404, detail=f"卷 {volume_id} 不存在")


@router.post("/volumes", response_model=VolumeResponse, status_code=201)
async def create_volume(request: Request, body: VolumeCreate):
    """创建新卷"""
    index = _get_index(request)
    now = datetime.now(timezone.utc).isoformat()

    new_id = max((v.id for v in index.volumes), default=0) + 1
    new_vol = VolumePlan(
        id=new_id,
        name=body.name,
        subtitle=body.subtitle,
        chapter_start=body.chapter_start,
        chapter_end=body.chapter_end,
        summary=body.summary,
        status="planned",
        created_at=now,
        updated_at=now,
    )
    index.volumes.append(new_vol)
    index.volumes.sort(key=lambda v: v.id)
    _save_index(request, index)

    return VolumeResponse(
        id=new_vol.id, name=new_vol.name, subtitle=new_vol.subtitle,
        chapter_start=new_vol.chapter_start, chapter_end=new_vol.chapter_end,
        summary=new_vol.summary, status=new_vol.status,
        created_at=new_vol.created_at, updated_at=new_vol.updated_at,
    )


@router.put("/volumes/{volume_id}", response_model=VolumeResponse)
async def update_volume(request: Request, volume_id: int, body: VolumeUpdate):
    """更新卷信息"""
    index = _get_index(request)
    for v in index.volumes:
        if v.id == volume_id:
            if body.name is not None:
                v.name = body.name
            if body.subtitle is not None:
                v.subtitle = body.subtitle
            if body.chapter_start is not None:
                v.chapter_start = body.chapter_start
            if body.chapter_end is not None:
                v.chapter_end = body.chapter_end
            if body.summary is not None:
                v.summary = body.summary
            if body.status is not None:
                v.status = body.status
            v.updated_at = datetime.now(timezone.utc).isoformat()
            _save_index(request, index)

            return VolumeResponse(
                id=v.id, name=v.name, subtitle=v.subtitle,
                chapter_start=v.chapter_start, chapter_end=v.chapter_end,
                summary=v.summary, status=v.status,
                created_at=v.created_at, updated_at=v.updated_at,
            )

    raise HTTPException(status_code=404, detail=f"卷 {volume_id} 不存在")


@router.delete("/volumes/{volume_id}", status_code=204)
async def delete_volume(request: Request, volume_id: int):
    """删除卷"""
    index = _get_index(request)
    for i, v in enumerate(index.volumes):
        if v.id == volume_id:
            index.volumes.pop(i)
            _save_index(request, index)
            return
    raise HTTPException(status_code=404, detail=f"卷 {volume_id} 不存在")