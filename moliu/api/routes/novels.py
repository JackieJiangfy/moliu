"""小说管理 API — 多本小说 CRUD

数据存储：data/novels/index.json
每本小说的数据目录：data/novels/{novel_id}/
每本小说的章节输出：output/novels/{novel_id}/chapters/
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from moliu.data.schemas import Novel, NovelIndex

router = APIRouter()

# 全局索引锁 — 防止并发创建/删除导致 id 冲突
_novel_lock = asyncio.Lock()


# --- Request/Response 模型 ---

class NovelCreate(BaseModel):
    title: str
    subtitle: str = ""
    genre: str = ""
    premise: str = ""
    target_chapters: int = 1000


class NovelUpdate(BaseModel):
    title: str | None = None
    subtitle: str | None = None
    genre: str | None = None
    premise: str | None = None
    target_chapters: int | None = None
    status: str | None = None


class NovelResponse(BaseModel):
    id: int
    title: str
    subtitle: str
    genre: str
    premise: str
    target_chapters: int
    status: str
    created_at: str
    updated_at: str


# --- 辅助函数 ---

def _get_index(request: Request) -> NovelIndex:
    cfg = request.app.state.config
    return NovelIndex.from_json(cfg.resolve_novel_index_path())


def _save_index(request: Request, index: NovelIndex) -> None:
    cfg = request.app.state.config
    index.to_json(cfg.resolve_novel_index_path())


def _init_novel_dirs(request: Request, novel_id: int) -> None:
    """创建小说所需的所有子目录"""
    cfg = request.app.state.config
    data_dir = cfg.resolve_novel_data_dir(novel_id)
    for sub in ["characters", "outlines", "volumes", "world"]:
        (data_dir / sub).mkdir(parents=True, exist_ok=True)
    # 触发章节输出目录创建
    cfg.resolve_novel_output_dir(novel_id)


# --- 路由 ---

@router.get("/novels", response_model=list[NovelResponse])
async def list_novels(request: Request):
    """列出所有小说"""
    index = _get_index(request)
    return [NovelResponse(**n.model_dump()) for n in index.novels]


@router.get("/novels/{novel_id}", response_model=NovelResponse)
async def get_novel(request: Request, novel_id: int):
    """获取单个小说"""
    index = _get_index(request)
    novel = index.get(novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail=f"小说 {novel_id} 不存在")
    return NovelResponse(**novel.model_dump())


@router.post("/novels", response_model=NovelResponse, status_code=201)
async def create_novel(request: Request, body: NovelCreate):
    """创建新小说 — 同时初始化目录结构"""
    cfg = request.app.state.config
    async with _novel_lock:
        index = _get_index(request)
        now = datetime.now(timezone.utc).isoformat()

        new_id = index.next_id
        novel = Novel(
            id=new_id,
            title=body.title,
            subtitle=body.subtitle,
            genre=body.genre,
            premise=body.premise,
            target_chapters=body.target_chapters,
            status="planned",
            created_at=now,
            updated_at=now,
        )
        index.novels.append(novel)
        index.next_id = new_id + 1
        _save_index(request, index)

        # 初始化目录结构
        _init_novel_dirs(request, new_id)

        # 初始化空的卷索引(写入 novel_title)
        from moliu.data.schemas import VolumeIndex
        vol_index = VolumeIndex(novel_title=body.title)
        vol_index.to_json(cfg.resolve_novel_data_dir(new_id) / "volumes" / "index.json")

    return NovelResponse(**novel.model_dump())


@router.put("/novels/{novel_id}", response_model=NovelResponse)
async def update_novel(request: Request, novel_id: int, body: NovelUpdate):
    """更新小说信息"""
    async with _novel_lock:
        index = _get_index(request)
        novel = index.get(novel_id)
        if not novel:
            raise HTTPException(status_code=404, detail=f"小说 {novel_id} 不存在")

        if body.title is not None: novel.title = body.title
        if body.subtitle is not None: novel.subtitle = body.subtitle
        if body.genre is not None: novel.genre = body.genre
        if body.premise is not None: novel.premise = body.premise
        if body.target_chapters is not None: novel.target_chapters = body.target_chapters
        if body.status is not None: novel.status = body.status
        novel.updated_at = datetime.now(timezone.utc).isoformat()

        _save_index(request, index)

    return NovelResponse(**novel.model_dump())


@router.delete("/novels/{novel_id}", status_code=204)
async def delete_novel(request: Request, novel_id: int):
    """删除小说 — 同时删除数据目录(谨慎)"""
    import shutil
    cfg = request.app.state.config
    async with _novel_lock:
        index = _get_index(request)
        novel = index.get(novel_id)
        if not novel:
            raise HTTPException(status_code=404, detail=f"小说 {novel_id} 不存在")

        # 删除数据目录
        data_dir = cfg.resolve_novel_data_dir(novel_id)
        if data_dir.exists():
            shutil.rmtree(data_dir, ignore_errors=True)
        output_dir = cfg.resolve_novel_output_dir(novel_id)
        if output_dir.exists():
            shutil.rmtree(output_dir.parent, ignore_errors=True)

        # 从索引移除
        index.novels = [n for n in index.novels if n.id != novel_id]
        _save_index(request, index)
