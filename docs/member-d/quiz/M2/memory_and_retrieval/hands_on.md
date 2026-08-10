题目：使用 Semantic Kernel 当前的 InMemoryCollection 建立一个小型向量集合，写入两条记录并按查询向量检索最相近记录。
答案：该练习使用手工向量，便于在没有外部数据库和嵌入模型的情况下检查完整流程：
```python
from dataclasses import dataclass
from typing import Annotated

from semantic_kernel.connectors.in_memory import InMemoryCollection
from semantic_kernel.data.vector import VectorStoreField, vectorstoremodel

@vectorstoremodel
@dataclass
class MemoryRecord:
    record_id: Annotated[str, VectorStoreField("key")]
    text: Annotated[str, VectorStoreField("data", is_full_text_indexed=True)]
    embedding: Annotated[
        list[float],
        VectorStoreField("vector", dimensions=3, distance_function="cosine"),
    ]

collection = InMemoryCollection(
    record_type=MemoryRecord,
    collection_name="semantic_kernel_notes",
)
await collection.ensure_collection_exists()
await collection.upsert([
    MemoryRecord("1", "Kernel manages services and plugins.", [1.0, 0.0, 0.0]),
    MemoryRecord("2", "Agents can cooperate through orchestration.", [0.0, 1.0, 0.0]),
])

results = await collection.search(
    vector=[0.9, 0.1, 0.0],
    vector_property_name="embedding",
    top=1,
)
async for result in results.results:
    print(result.record.text)
```
题型：Open
用途：practice
难度：advanced
评分方法：正确定义 key、data、vector 三类字段得 1 分；创建并初始化 InMemoryCollection 得 1 分；写入两条记录得 1 分；按向量搜索并读取结果得 1 分；共 4 分。
资料名称：Using the Semantic Kernel In-Memory Vector Store connector
官方链接：https://learn.microsoft.com/en-us/semantic-kernel/concepts/vector-store-connectors/out-of-the-box-connectors/inmemory-connector
出处章节：Getting started、Python
是否更新MIRT：否
