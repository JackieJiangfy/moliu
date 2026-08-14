"""[已废弃] 分层检索 — 已合并到 StructuredAssembler

保留此类仅为向后兼容 — 老代码导入 `Retriever` 时,会自动转用
`moliu.context.assembler.StructuredAssembler`。新代码请直接用
StructuredAssembler。
"""

from __future__ import annotations

from moliu.config import Config
from moliu.context.assembler import StructuredAssembler
from moliu.data.schemas import CharacterCard, NarratorCard, WorldSetting
from moliu.memory.store import MemoryStore


class Retriever(StructuredAssembler):
    """[已废弃] Retriever 已合并到 StructuredAssembler

    此类仅为向后兼容保留。功能已全部迁移到 StructuredAssembler。
    memory 参数仍接受但不再使用 — StructuredAssembler 直接读文件,
    无需向量索引。如需 RAG,在 pipeline 层手动注入。
    """

    def __init__(self, config: Config, memory: MemoryStore | None = None):
        super().__init__(config)
        # memory 保留为属性供老代码引用,但实际不再使用
        self.memory = memory
