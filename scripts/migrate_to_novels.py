"""数据迁移脚本 — 把旧的扁平 data/ 和 output/chapters/ 迁移到多小说结构

旧结构:
  data/characters/
  data/world/
  data/volumes/index.json
  data/narrator.md
  output/chapters/第1章/
  ...

新结构:
  data/novels/index.json          # 所有小说的索引
  data/novels/1/                  # novel_id=1 的数据
    characters/
    world/
    volumes/index.json
    narrator.md
  output/novels/1/chapters/第1章/

此脚本幂等 — 重复运行不会重复移动。
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

# 需要从 data/ 迁移到 data/novels/1/ 的子目录和文件
DATA_SUBDIRS = ["characters", "outlines", "volumes", "world"]
DATA_FILES = [
    "narrator.md", "narrator.yaml",
    "rhythm_log.jsonl", "usage_log.jsonl",
    "directions.txt", "章节名.txt", "评估报告.md",
    "foreshadow.json", "relationships.json",
]


def migrate(project_root: Path) -> None:
    data_dir = project_root / "data"
    output_dir = project_root / "output"

    novels_dir = data_dir / "novels"
    novels_dir.mkdir(parents=True, exist_ok=True)

    novel_1_dir = novels_dir / "1"
    novel_1_dir.mkdir(parents=True, exist_ok=True)

    # --- 1. 迁移 data/ 子目录 ---
    moved_dirs = 0
    for sub in DATA_SUBDIRS:
        src = data_dir / sub
        dst = novel_1_dir / sub
        if src.exists() and not dst.exists():
            shutil.move(str(src), str(dst))
            moved_dirs += 1
            print(f"  [DIR] {sub}/ -> novels/1/{sub}/")
        elif src.exists() and dst.exists():
            # 合并:src 里没有的文件拷过去
            for f in src.rglob("*"):
                if f.is_file():
                    rel = f.relative_to(src)
                    target = dst / rel
                    if not target.exists():
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(f), str(target))
                        print(f"  [MERGE] {sub}/{rel} -> novels/1/{sub}/{rel}")
            shutil.rmtree(src, ignore_errors=True)

    # --- 2. 迁移 data/ 散文件 ---
    moved_files = 0
    for fname in DATA_FILES:
        src = data_dir / fname
        dst = novel_1_dir / fname
        if src.exists() and not dst.exists():
            shutil.move(str(src), str(dst))
            moved_files += 1
            print(f"  [FILE] {fname} -> novels/1/{fname}")
        elif src.exists() and dst.exists():
            # 已存在,删旧的
            src.unlink()
            print(f"  [SKIP] {fname} (已在 novels/1/ 存在)")

    # --- 3. 迁移 data/chapter_NNN/ 段落目录(测试或生成产生) ---
    moved_seg = 0
    for ch_dir in list(data_dir.glob("chapter_*")):
        if ch_dir.is_dir():
            dst = novel_1_dir / ch_dir.name
            if not dst.exists():
                shutil.move(str(ch_dir), str(dst))
                moved_seg += 1
                print(f"  [SEG] {ch_dir.name}/ -> novels/1/{ch_dir.name}/")

    # --- 4. 迁移 output/chapters/ -> output/novels/1/chapters/ ---
    old_output = output_dir / "chapters"
    new_output = output_dir / "novels" / "1" / "chapters"
    if old_output.exists() and not new_output.exists():
        new_output.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(old_output), str(new_output))
        print(f"  [OUTPUT] output/chapters/ -> output/novels/1/chapters/ ({len(list(new_output.iterdir()))} 章目录)")
    elif old_output.exists() and new_output.exists():
        # 合并
        moved_ch = 0
        for ch_dir in list(old_output.iterdir()):
            dst = new_output / ch_dir.name
            if not dst.exists():
                shutil.move(str(ch_dir), str(dst))
                moved_ch += 1
        if moved_ch:
            print(f"  [OUTPUT-MERGE] 合并 {moved_ch} 章到 output/novels/1/chapters/")
        if old_output.exists() and not any(old_output.iterdir()):
            old_output.rmdir()

    # --- 5. 创建/更新 novels/index.json ---
    index_path = novels_dir / "index.json"
    now = datetime.now(timezone.utc).isoformat()

    if index_path.exists():
        index = json.loads(index_path.read_text(encoding="utf-8"))
    else:
        index = {"novels": [], "next_id": 1}

    # 检查是否已有 id=1
    if not any(n.get("id") == 1 for n in index["novels"]):
        # 从 volumes/index.json 读小说名
        vol_index_path = novel_1_dir / "volumes" / "index.json"
        novel_title = "未命名小说"
        if vol_index_path.exists():
            try:
                vol_data = json.loads(vol_index_path.read_text(encoding="utf-8"))
                novel_title = vol_data.get("novel_title", novel_title)
            except Exception:
                pass

        novel_1 = {
            "id": 1,
            "title": novel_title,
            "subtitle": "",
            "genre": "",
            "premise": "",
            "target_chapters": 1000,
            "status": "active",
            "created_at": now,
            "updated_at": now,
        }
        index["novels"].append(novel_1)
        index["next_id"] = max(2, index.get("next_id", 1))
        index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  [INDEX] 创建 novels/index.json,小说: {novel_title}")
    else:
        print(f"  [INDEX] novels/index.json 已存在,跳过")

    print(f"\n迁移完成: {moved_dirs} 目录, {moved_files} 文件, {moved_seg} 段落目录")


if __name__ == "__main__":
    project_root = Path(__file__).parent.parent
    print(f"开始迁移 {project_root} ...")
    migrate(project_root)
