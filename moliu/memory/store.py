"""记忆存储 — ChromaDB (首选) 或 JSON 文件 (回退)"""

from __future__ import annotations

import json
from pathlib import Path


class MemoryStore:
    """向量 + 结构化记忆存储。

    优先使用 ChromaDB，安装失败则回退到 JSON 文件模式。
    """

    def __init__(self, persist_dir: str | Path):
        self._dir = Path(persist_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._collections: dict[str, list[dict]] = {}
        self._chroma = None
        self._use_chroma = False

        try:
            import chromadb as _c
            client = _c.PersistentClient(
                path=str(self._dir),
                settings=_c.Settings(anonymized_telemetry=False),
            )
            # 测试兼容性：尝试创建/获取一个 collection
            try:
                client.get_or_create_collection("_compat_test", metadata={"hnsw:space": "cosine"})
                client.delete_collection("_compat_test")
            except Exception:
                pass
            self._chroma = client
            self._use_chroma = True
        except Exception:
            self._chroma = None
            self._use_chroma = False
            self._load_json()

    def _load_json(self) -> None:
        for name in ["chapter_summaries", "character_states", "plot_threads", "creative_notes", "world_fragments"]:
            f = self._dir / f"{name}.json"
            if f.exists():
                try:
                    self._collections[name] = json.loads(f.read_text(encoding="utf-8"))
                except Exception:
                    self._collections[name] = []
            else:
                self._collections[name] = []

    def _save_json(self, name: str) -> None:
        f = self._dir / f"{name}.json"
        f.write_text(json.dumps(self._collections.get(name, []), ensure_ascii=False, indent=2), encoding="utf-8")

    def _get_chroma_coll(self, name: str):
        try:
            return self._chroma.get_or_create_collection(name, metadata={"hnsw:space": "cosine"})
        except Exception:
            return self._chroma.get_or_create_collection(name)

    # === 写入 ===

    def add_summary(self, chapter_num: int, summary: str, emotion: str, characters: list[str]) -> None:
        if self._use_chroma:
            coll = self._get_chroma_coll("chapter_summaries")
            coll.add(documents=[summary], metadatas=[{"emotion": emotion, "characters": ", ".join(characters)}], ids=[f"ch_{chapter_num:04d}"])
        else:
            self._collections.setdefault("chapter_summaries", []).append({
                "id": f"ch_{chapter_num:04d}", "document": summary, "emotion": emotion, "characters": characters,
            })
            self._save_json("chapter_summaries")

    def add_character_snapshot(self, chapter_num: int, snapshot: str) -> None:
        if self._use_chroma:
            coll = self._get_chroma_coll("character_states")
            coll.add(documents=[snapshot], ids=[f"snapshot_{chapter_num:04d}"])
        else:
            self._collections.setdefault("character_states", []).append({
                "id": f"snapshot_{chapter_num:04d}", "document": snapshot,
            })
            self._save_json("character_states")

    def add_plot_thread(self, thread_id: str, description: str, status: str, chapter_num: int) -> None:
        if self._use_chroma:
            coll = self._get_chroma_coll("plot_threads")
            coll.add(documents=[description], metadatas=[{"status": status, "last_chapter": chapter_num}], ids=[thread_id])
        else:
            self._collections.setdefault("plot_threads", []).append({
                "id": thread_id, "document": description, "status": status, "last_chapter": chapter_num,
            })
            self._save_json("plot_threads")

    def update_plot_thread(self, thread_id: str, description: str, status: str, chapter_num: int) -> None:
        if self._use_chroma:
            coll = self._get_chroma_coll("plot_threads")
            try:
                coll.upsert(documents=[description], metadatas=[{"status": status, "last_chapter": chapter_num}], ids=[thread_id])
            except Exception:
                coll.add(documents=[description], metadatas=[{"status": status, "last_chapter": chapter_num}], ids=[thread_id])
        else:
            items = self._collections.setdefault("plot_threads", [])
            for item in items:
                if item["id"] == thread_id:
                    item["document"] = description
                    item["status"] = status
                    item["last_chapter"] = chapter_num
                    break
            else:
                items.append({"id": thread_id, "document": description, "status": status, "last_chapter": chapter_num})
            self._save_json("plot_threads")

    def add_note(self, note_id: str, content: str, tags: list[str] | None = None) -> None:
        if self._use_chroma:
            coll = self._get_chroma_coll("creative_notes")
            coll.add(documents=[content], metadatas=[{"tags": json.dumps(tags or [])}], ids=[note_id])
        else:
            self._collections.setdefault("creative_notes", []).append({
                "id": note_id, "document": content, "tags": tags or [],
            })
            self._save_json("creative_notes")

    # === 检索 ===

    def query_summaries(self, query: str, n: int = 5) -> list[str]:
        if self._use_chroma:
            try:
                coll = self._get_chroma_coll("chapter_summaries")
                results = coll.query(query_texts=[query], n_results=n)
                return results["documents"][0] if results.get("documents") and results["documents"][0] else []
            except Exception:
                return []
        items = self._collections.get("chapter_summaries", [])
        # 分词匹配：按双字 bigram 切分 query，匹配文档
        scored = []
        query_terms = [query[i:i+2] for i in range(len(query)-1)]
        for item in items:
            doc = item.get("document", "")
            score = sum(1 for t in query_terms if t in doc)
            if score > 0:
                scored.append((score, doc))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [doc for _, doc in scored[:n]]

    def query_notes(self, query: str, n: int = 5) -> list[str]:
        if self._use_chroma:
            try:
                coll = self._get_chroma_coll("creative_notes")
                results = coll.query(query_texts=[query], n_results=n)
                return results["documents"][0] if results.get("documents") and results["documents"][0] else []
            except Exception:
                return []
        items = self._collections.get("creative_notes", [])
        scored = []
        query_terms = [query[i:i+2] for i in range(len(query)-1)]
        for item in items:
            doc = item.get("document", "")
            score = sum(1 for t in query_terms if t in doc)
            if score > 0:
                scored.append((score, doc))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [doc for _, doc in scored[:n]]

    def get_active_plot_threads(self) -> list[dict]:
        if self._use_chroma:
            try:
                coll = self._get_chroma_coll("plot_threads")
                results = coll.get()
                active = []
                if results.get("metadatas"):
                    for i, meta in enumerate(results["metadatas"]):
                        if meta and meta.get("status") in ("planted", "building"):
                            active.append({
                                "id": results["ids"][i],
                                "description": results["documents"][i] if results.get("documents") else "",
                                "status": meta["status"],
                                "last_chapter": meta.get("last_chapter", 0),
                            })
                return active
            except Exception:
                return []
        return [
            {"id": i["id"], "description": i["document"], "status": i["status"], "last_chapter": i.get("last_chapter", 0)}
            for i in self._collections.get("plot_threads", [])
            if i["status"] in ("planted", "building")
        ]

    def count(self, collection_name: str) -> int:
        if self._use_chroma:
            try:
                return self._get_chroma_coll(collection_name).count()
            except Exception:
                return 0
        return len(self._collections.get(collection_name, []))

    def chapter_count(self) -> int:
        return self.count("chapter_summaries")
