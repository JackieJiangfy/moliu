"""统一的并发锁管理 — 每本小说一个独立锁,避免不同 novel 互相阻塞

用法:
    from moliu.api.locks import novel_lock

    async with novel_lock(novel_id):
        # 修改此 novel 的数据...
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Dict


class _NovelLockRegistry:
    """按 novel_id 维护独立的 asyncio.Lock

    使用 defaultdict 自动创建锁,无需预先注册。
    锁是进程级的,单 worker 内有效。多 worker 部署需配合文件锁或 DB 事务。
    """

    def __init__(self):
        self._locks: Dict[int, asyncio.Lock] = {}
        self._registry_lock = asyncio.Lock()

    async def get(self, novel_id: int) -> asyncio.Lock:
        """获取指定 novel 的锁(不存在则创建)"""
        async with self._registry_lock:
            if novel_id not in self._locks:
                self._locks[novel_id] = asyncio.Lock()
            return self._locks[novel_id]


# 全局单例
_registry = _NovelLockRegistry()


class _NovelLockContext:
    """async context manager — 简化 `async with novel_lock(id):` 用法"""

    def __init__(self, novel_id: int):
        self.novel_id = novel_id
        self._lock: asyncio.Lock | None = None

    async def __aenter__(self):
        self._lock = await _registry.get(self.novel_id)
        await self._lock.acquire()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self._lock is not None:
            self._lock.release()
        return False


def novel_lock(novel_id: int = 1) -> _NovelLockContext:
    """获取指定 novel 的锁上下文

    用法:
        async with novel_lock(1):
            ...
    """
    return _NovelLockContext(novel_id)
