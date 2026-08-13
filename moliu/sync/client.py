"""墨流 → 墨脉图 同步客户端

将墨流生成的角色卡 / 世界观 / 叙述者 / 章节 / 伏笔
通过 HTTP 推送到墨脉图（novel_graph）后端，自动 upsert。

设计要点：
- 异步 httpx，与墨流其他网络调用一致
- 懒加载 token：首次同步时自动登录并缓存
- 同步失败只抛 MomaituSyncError，由调用方决定是否阻塞主流程
- 字段映射：墨流 Pydantic snake_case → 墨脉图 DTO snake_case（直传即可）
"""
from __future__ import annotations

import logging
from typing import Any

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class MomaituSyncError(Exception):
    """同步失败统一异常"""


class MomaituSyncClient:
    """墨脉图同步客户端

    用法：
        client = MomaituSyncClient(
            base_url="http://127.0.0.1:8080/api",
            username="moliu",
            password="xxx",
        )
        await client.sync_character(novel_id, character_card_dict)
    """

    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        *,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self._token: str | None = None
        self._client = httpx.AsyncClient(timeout=timeout)

    async def __aenter__(self) -> "MomaituSyncClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def close(self) -> None:
        await self._client.aclose()

    # ============ 内部工具 ============

    async def _login(self) -> None:
        """登录获取 token（已缓存则跳过）"""
        if self._token:
            return
        url = f"{self.base_url}/auth/login"
        try:
            r = await self._client.post(
                url,
                json={"username": self.username, "password": self.password},
            )
            r.raise_for_status()
            payload = r.json()
            if payload.get("code") != 200:
                raise MomaituSyncError(f"登录失败: {payload.get('message')}")
            self._token = payload["data"]["token"]
            logger.info("墨脉图登录成功 user=%s", self.username)
        except httpx.HTTPError as e:
            raise MomaituSyncError(f"登录请求失败: {e}") from e

    async def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        """POST 请求，自动带 token；401 时重试一次"""
        await self._login()
        url = f"{self.base_url}{path}"
        headers = {"Authorization": self._token}

        try:
            r = await self._client.post(url, json=body, headers=headers)
        except httpx.HTTPError as e:
            raise MomaituSyncError(f"请求失败 {path}: {e}") from e

        # 401 → token 失效，清空重试一次
        if r.status_code == 401:
            logger.warning("token 失效，重新登录")
            self._token = None
            await self._login()
            headers = {"Authorization": self._token}
            r = await self._client.post(url, json=body, headers=headers)

        try:
            payload = r.json()
        except Exception as e:
            raise MomaituSyncError(f"响应解析失败 {path} status={r.status_code}: {e}") from e

        if payload.get("code") != 200:
            raise MomaituSyncError(f"同步失败 {path}: {payload.get('message')}")

        return payload["data"]

    async def _get(self, path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        """GET 请求，自动带 token"""
        await self._login()
        url = f"{self.base_url}{path}"
        headers = {"Authorization": self._token}
        try:
            r = await self._client.get(url, params=params or {}, headers=headers)
        except httpx.HTTPError as e:
            raise MomaituSyncError(f"请求失败 {path}: {e}") from e
        if r.status_code == 401:
            self._token = None
            await self._login()
            r = await self._client.get(url, params=params or {}, headers={"Authorization": self._token})
        try:
            payload = r.json()
        except Exception as e:
            raise MomaituSyncError(f"响应解析失败 {path}: {e}") from e
        if payload.get("code") != 200:
            raise MomaituSyncError(f"查询失败 {path}: {payload.get('message')}")
        return payload["data"]

    async def get_characters(self, novel_id: str) -> list[dict]:
        """获取小说的所有角色"""
        data = await self._get(f"/novel/{novel_id}/characters")
        if isinstance(data, dict) and "records" in data:
            return data["records"]
        return data if isinstance(data, list) else []

    async def get_chapters(self, novel_id: str) -> list[dict]:
        """获取小说的所有章节"""
        data = await self._get(f"/novel/{novel_id}/chapters")
        if isinstance(data, dict) and "records" in data:
            return data["records"]
        return data if isinstance(data, list) else []

    async def get_foreshadows(self, novel_id: str) -> list[dict]:
        """获取小说的所有伏笔"""
        data = await self._get(f"/novel/{novel_id}/foreshadows")
        if isinstance(data, dict) and "records" in data:
            return data["records"]
        return data if isinstance(data, list) else []

    # ============ 公开同步方法 ============

    async def sync_character(self, novel_id: str, character: BaseModel | dict) -> dict:
        """同步角色（按 name upsert）"""
        body = character.model_dump(exclude_none=False) if isinstance(character, BaseModel) else dict(character)
        return await self._post(f"/novel/{novel_id}/sync/character", body)

    async def sync_world(self, novel_id: str, world: BaseModel | dict, *, raw_yaml: str = "") -> dict:
        """同步世界观（1:1 覆盖）"""
        body = world.model_dump(exclude_none=False) if isinstance(world, BaseModel) else dict(world)
        if raw_yaml and not body.get("raw_yaml"):
            body["raw_yaml"] = raw_yaml
        return await self._post(f"/novel/{novel_id}/sync/world", body)

    async def sync_narrator(self, novel_id: str, narrator: BaseModel | dict, *, raw_markdown: str = "") -> dict:
        """同步叙述者（1:1 覆盖）"""
        body = narrator.model_dump(exclude_none=False) if isinstance(narrator, BaseModel) else dict(narrator)
        if raw_markdown and not body.get("raw_markdown"):
            body["raw_markdown"] = raw_markdown
        return await self._post(f"/novel/{novel_id}/sync/narrator", body)

    async def sync_chapter(self, novel_id: str, chapter: BaseModel | dict, **extra) -> dict:
        """同步章节（按 chapter_num upsert）

        extra 可传 tension_score / chapter_type / dialogue_ratio 等质检字段
        """
        body = chapter.model_dump(exclude_none=False) if isinstance(chapter, BaseModel) else dict(chapter)
        body.update(extra)
        return await self._post(f"/novel/{novel_id}/sync/chapter", body)

    async def sync_foreshadow(self, novel_id: str, foreshadow: BaseModel | dict) -> dict:
        """同步伏笔（按 moliu_id upsert）"""
        body = foreshadow.model_dump(exclude_none=False) if isinstance(foreshadow, BaseModel) else dict(foreshadow)
        return await self._post(f"/novel/{novel_id}/sync/foreshadow", body)

    async def sync_relationships(self, novel_id: str, relations: list[dict]) -> dict:
        """批量同步角色关系（来自 LLM 抽取）

        Args:
            relations: [{source_name, target_name, rel_type, category, ...}, ...]
        Returns:
            {"success": n, "skipped": m, "updated": k}
        """
        return await self._post(f"/novel/{novel_id}/relationships/batch-sync", relations)
