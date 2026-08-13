"""墨流 FastAPI 后端 — 小说创作专用 REST API

架构：OpenWebUI（现成聊天 UI）→ OpenAI 兼容接口 → 本后端
本后端只提供数据 CRUD + 生成编排，不提供任何前端页面。
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from moliu.config import Config

from .routes import status, volumes, chapters, characters, world, foreshadows, openai_compat


def create_app(config: Config | None = None) -> FastAPI:
    """创建 FastAPI 应用实例

    Args:
        config: 墨流配置（可选，不传则自动加载）
    """
    app = FastAPI(
        title="墨流 API",
        description="AI 小说创作引擎后端 API（OpenWebUI 后端）",
        version="1.0.0",
    )

    # CORS — 允许 OpenWebUI 跨域访问
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # 本地自用
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 注入 config
    if config is None:
        config = Config()
    app.state.config = config

    # 数据 CRUD 路由
    app.include_router(status.router, prefix="/api/v1", tags=["状态"])
    app.include_router(volumes.router, prefix="/api/v1", tags=["卷管理"])
    app.include_router(chapters.router, prefix="/api/v1", tags=["章节"])
    app.include_router(characters.router, prefix="/api/v1", tags=["角色"])
    app.include_router(world.router, prefix="/api/v1", tags=["世界观"])
    app.include_router(foreshadows.router, prefix="/api/v1", tags=["伏笔"])

    # OpenAI 兼容接口（无前缀 — 直接挂载在 /v1 下，供 OpenWebUI 连接）
    app.include_router(openai_compat.router, tags=["OpenAI 兼容"])

    return app


# 便捷启动
app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("moliu.api:app", host="0.0.0.0", port=8000, reload=True)