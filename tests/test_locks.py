"""novel_lock 并发正确性测试

验证:
1. 同 novel_id 的锁是串行的(进入第二次必须等第一次释放)
2. 不同 novel_id 互不阻塞(可并发)
3. 退出上下文后释放
"""

import asyncio
import time

import pytest

from moliu.api.locks import novel_lock, _registry


pytestmark = pytest.mark.asyncio


class TestNovelLock:
    """novel_lock 行为验证"""

    async def test_serial_same_novel(self):
        """同 novel_id 的两次加锁必须串行执行"""
        order: list[str] = []

        async def worker(tag: str, delay: float):
            async with novel_lock(42):
                order.append(f"{tag}-enter")
                await asyncio.sleep(delay)
                order.append(f"{tag}-exit")

        # 两个 worker 共享同一 novel_id=42
        await asyncio.gather(worker("A", 0.05), worker("B", 0.05))

        # 必须严格串行:A 全程在 B 之前
        assert order == ["A-enter", "A-exit", "B-enter", "B-exit"], order

    async def test_parallel_different_novels(self):
        """不同 novel_id 的锁互不阻塞 — 这是 per-novel 设计的核心"""
        order: list[str] = []

        async def worker(novel_id: int, tag: str, delay: float):
            async with novel_lock(novel_id):
                order.append(f"{tag}-enter")
                await asyncio.sleep(delay)
                order.append(f"{tag}-exit")

        # 不同 novel_id 并发 — 应该重叠
        await asyncio.gather(
            worker(1, "A", 0.1),
            worker(2, "B", 0.1),
        )

        # 两个 enter 都在 exit 之前 — 说明它们重叠执行了
        enters = [i for i, x in enumerate(order) if x.endswith("-enter")]
        exits = [i for i, x in enumerate(order) if x.endswith("-exit")]
        assert max(enters) < min(exits), f"未并发执行: {order}"

    async def test_lock_released_after_context(self):
        """退出 contextmanager 后锁应被释放,可再次获取"""
        async with novel_lock(99):
            pass

        # 再次获取不应阻塞(立即拿到)
        async with novel_lock(99):
            pass

    async def test_lock_serializes_critical_section(self):
        """实测临界区串行 — 用计数器验证无 race"""
        # 注意:asyncio 单线程无真竞态,但锁应保证可见的串行顺序
        counter = 0
        max_concurrent = 0
        current_concurrent = 0

        async def increment():
            nonlocal counter, current_concurrent, max_concurrent
            async with novel_lock(7):
                current_concurrent += 1
                max_concurrent = max(max_concurrent, current_concurrent)
                # 模拟读改写
                tmp = counter
                await asyncio.sleep(0.01)
                counter = tmp + 1
                current_concurrent -= 1

        await asyncio.gather(*[increment() for _ in range(10)])

        assert counter == 10  # 无丢失
        assert max_concurrent == 1  # 严格串行

    async def test_registry_reuses_lock(self):
        """同一 novel_id 反复拿应得同一把锁实例"""
        lock1 = await _registry.get(123)
        lock2 = await _registry.get(123)
        assert lock1 is lock2

    async def test_exception_still_releases(self):
        """临界区抛异常时锁也应被释放"""
        try:
            async with novel_lock(555):
                raise ValueError("boom")
        except ValueError:
            pass

        # 应能立即重新获取
        async with novel_lock(555):
            pass
