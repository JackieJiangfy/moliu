"""把 output/novels/{id}/chapters/ 下的 第N章 目录重命名为 chapter_NNNN

此脚本幂等。重复运行不会重复重命名。
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path


def rename_chapters(project_root: Path) -> int:
    output_dir = project_root / "output" / "novels"
    if not output_dir.exists():
        print(f"[SKIP] {output_dir} 不存在")
        return 0

    renamed = 0
    for novel_dir in output_dir.iterdir():
        if not novel_dir.is_dir():
            continue
        chapters_dir = novel_dir / "chapters"
        if not chapters_dir.exists():
            continue

        for ch_dir in list(chapters_dir.iterdir()):
            if not ch_dir.is_dir():
                continue
            # 旧格式 第N章
            m = re.match(r"^第(\d+)章$", ch_dir.name)
            if not m:
                continue

            ch_num = int(m.group(1))
            new_name = f"chapter_{ch_num:04d}"
            new_path = chapters_dir / new_name

            if new_path.exists():
                # 合并:把旧目录里的文件移动到新目录,删旧目录
                for f in ch_dir.rglob("*"):
                    if f.is_file():
                        rel = f.relative_to(ch_dir)
                        target = new_path / rel
                        if not target.exists():
                            target.parent.mkdir(parents=True, exist_ok=True)
                            shutil.move(str(f), str(target))
                shutil.rmtree(ch_dir, ignore_errors=True)
                print(f"  [MERGE] {ch_dir.name} -> {new_name} (合并)")
            else:
                ch_dir.rename(new_path)
                renamed += 1
                print(f"  [REN] {ch_dir.name} -> {new_name}")

    return renamed


if __name__ == "__main__":
    project_root = Path(__file__).parent.parent
    print(f"开始重命名章节目录 {project_root} ...")
    count = rename_chapters(project_root)
    print(f"\n重命名完成: {count} 个章节目录")
