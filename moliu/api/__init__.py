"""墨流 FastAPI 后端 — 小说创作专用 REST API

架构：单页创作界面（static/index.html）→ OpenAI 兼容接口 → 本后端
本后端提供数据 CRUD + 生成编排，前端为单页 HTML。
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

from moliu.config import Config

from .routes import status, volumes, chapters, characters, world, foreshadows, relationships, novels, openai_compat


def create_app(config: Config | None = None) -> FastAPI:
    """创建 FastAPI 应用实例

    Args:
        config: 墨流配置（可选，不传则自动加载）
    """
    app = FastAPI(
        title="墨流 API",
        description="AI 小说创作引擎后端 API",
        version="1.0.0",
    )

    # CORS — 本地自用
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 注入 config
    if config is None:
        config = Config()
    app.state.config = config

    # 数据 CRUD 路由
    app.include_router(novels.router, prefix="/api/v1", tags=["小说"])
    app.include_router(status.router, prefix="/api/v1", tags=["状态"])
    app.include_router(volumes.router, prefix="/api/v1", tags=["卷管理"])
    app.include_router(chapters.router, prefix="/api/v1", tags=["章节"])
    app.include_router(characters.router, prefix="/api/v1", tags=["角色"])
    app.include_router(world.router, prefix="/api/v1", tags=["世界观"])
    app.include_router(foreshadows.router, prefix="/api/v1", tags=["伏笔"])
    app.include_router(relationships.router, prefix="/api/v1", tags=["关系图谱"])

    # OpenAI 兼容接口（无前缀 — 直接挂载在 /v1 下）
    app.include_router(openai_compat.router, tags=["OpenAI 兼容"])

    # 静态前端（单页创作界面）
    static_dir = Path(__file__).resolve().parent.parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # 根路径 → 创作工作台
    @app.get("/")
    async def root():
        return RedirectResponse(url="/static/index.html")

    return app


# 便捷启动
app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("moliu.api:app", host="0.0.0.0", port=8000, reload=True)