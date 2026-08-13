"""墨流 → 墨脉图 同步钩子

封装 quickstart/write 命令末尾的同步逻辑：
- 同步失败只警告，不阻塞主流程
- 未配置（is_momaitu_enabled=False）时静默跳过
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import typer
import yaml

from moliu.config import Config
from moliu.engines.gateway import DeepSeekGateway
from moliu.sync.client import MomaituSyncClient, MomaituSyncError
from moliu.sync.relation_extractor import RelationExtractor

if TYPE_CHECKING:
    from moliu.data.schemas import (
        ChapterResult,
        CharacterCard,
        NarratorCard,
        WorldSetting,
    )
    from moliu.orchestrator.pipeline import QualityReport

logger = logging.getLogger(__name__)


async def sync_quickstart_artifacts(
    config: Config,
    world_yaml_path: Path,
    characters_dir: Path,
    narrator_md_path: Path,
) -> None:
    """quickstart 完成后同步：世界观 + 所有角色 + 叙述者"""
    if not config.is_momaitu_enabled():
        return

    novel_id = config.momaitu_novel_id
    typer.echo("=== 同步到墨脉图 ===")

    client = MomaituSyncClient(
        base_url=config.momaitu_base_url,
        username=config.momaitu_username,
        password=config.momaitu_password,
    )

    ok, fail = 0, 0

    # 1. 世界观
    if world_yaml_path.exists():
        try:
            raw = world_yaml_path.read_text(encoding="utf-8")
            data = yaml.safe_load(raw) or {}
            data["raw_yaml"] = raw
            await client.sync_world(novel_id, data)
            typer.echo("  [OK] 世界观")
            ok += 1
        except MomaituSyncError as e:
            typer.echo(f"  [FAIL] 世界观: {e}")
            fail += 1
    else:
        typer.echo("  [SKIP] 世界观（文件不存在）")

    # 2. 角色（遍历 data/characters/*.yaml）
    if characters_dir.exists():
        char_files = sorted(characters_dir.glob("*.yaml"))
        for cf in char_files:
            try:
                raw = cf.read_text(encoding="utf-8")
                data = yaml.safe_load(raw) or {}
                await client.sync_character(novel_id, data)
                typer.echo(f"  [OK] 角色 {data.get('name', cf.stem)}")
                ok += 1
            except MomaituSyncError as e:
                typer.echo(f"  [FAIL] 角色 {cf.stem}: {e}")
                fail += 1
    else:
        typer.echo("  [SKIP] 角色（目录不存在）")

    # 3. 叙述者
    if narrator_md_path.exists():
        try:
            from moliu.data.schemas import NarratorCard

            card = NarratorCard.from_markdown(narrator_md_path)
            body = card.model_dump(exclude_none=False)
            body["raw_markdown"] = narrator_md_path.read_text(encoding="utf-8")
            await client.sync_narrator(novel_id, body)
            typer.echo("  [OK] 叙述者")
            ok += 1
        except MomaituSyncError as e:
            typer.echo(f"  [FAIL] 叙述者: {e}")
            fail += 1
    else:
        typer.echo("  [SKIP] 叙述者（文件不存在）")

    await client.close()
    typer.echo(f"=== 同步完成: {ok} 成功 / {fail} 失败 ===")


async def sync_chapter_artifacts(
    config: Config,
    chapter_num: int,
    result: "ChapterResult",
    qr: "QualityReport | None",
    emotion: str,
    characters: list["CharacterCard"],
) -> None:
    """write 命令完成后同步章节 + 角色最新状态 + 关系抽取"""
    if not config.is_momaitu_enabled():
        return

    novel_id = config.momaitu_novel_id
    typer.echo("=== 同步章节到墨脉图 ===")

    client = MomaituSyncClient(
        base_url=config.momaitu_base_url,
        username=config.momaitu_username,
        password=config.momaitu_password,
    )

    ok, fail = 0, 0

    # 1. 同步角色（章末状态已由 generator 更新）
    for c in characters:
        try:
            await client.sync_character(novel_id, c)
            ok += 1
        except MomaituSyncError as e:
            typer.echo(f"  [FAIL] 角色 {c.name}: {e}")
            fail += 1

    # 2. 同步章节（含质检数据）
    try:
        body = result.model_dump(exclude_none=False)
        body["emotion"] = emotion
        if qr is not None:
            body["tension_score"] = qr.tension_score
            body["consistency_fatal"] = qr.consistency_fatal
            body["consistency_warn"] = qr.consistency_warn
            body["reader_want_next"] = 1 if qr.reader_want_next else 0
        await client.sync_chapter(novel_id, body)
        typer.echo(f"  [OK] 第 {chapter_num} 章")
        ok += 1
    except MomaituSyncError as e:
        typer.echo(f"  [FAIL] 第 {chapter_num} 章: {e}")
        fail += 1

    # 3. 关系抽取（角色数 >=2 时用 LLM 从章节正文抽取关系并同步）
    if len(characters) >= 2 and config.deepseek_api_key:
        gw = None
        try:
            typer.echo("  关系抽取中...", nl=False)
            gw = DeepSeekGateway(config)
            extractor = RelationExtractor(config, gw)
            relations = await extractor.extract(chapter_num, result.content, characters)
            if relations:
                sync_result = await client.sync_relationships(novel_id, relations)
                typer.echo(
                    f"\r  [OK] 关系抽取: {len(relations)} 条 → "
                    f"成功 {sync_result.get('success', 0)} / 跳过 {sync_result.get('skipped', 0)}"
                )
                ok += 1
            else:
                typer.echo("\r  [SKIP] 关系抽取: 无关系")
        except MomaituSyncError as e:
            typer.echo(f"\r  [FAIL] 关系同步: {e}")
            fail += 1
        except Exception as e:
            typer.echo(f"\r  [WARN] 关系抽取异常: {e}")
        finally:
            if gw is not None:
                await gw.close()

    await client.close()
    typer.echo(f"=== 同步完成: {ok} 成功 / {fail} 失败 ===")
