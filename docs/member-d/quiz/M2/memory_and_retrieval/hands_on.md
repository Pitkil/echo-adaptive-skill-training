题目：在 Python 中使用 Semantic Kernel 的 TextSearch 功能，配置一个简单的内存向量存储，执行语义搜索。
答案：参考实现如下：
from semantic_kernel import Kernel
from semantic_kernel.text_search import TextSearch, MemoryTextSearch
from semantic_kernel.memory import VolatileMemoryStore

memory_store = VolatileMemoryStore()
text_search = MemoryTextSearch(memory_store)

# 添加文档
await text_search.add_text("Semantic Kernel is an open-source SDK for AI agents.")
await text_search.add_text("Plugins allow you to encapsulate functions for AI use.")

# 执行搜索
results = await text_search.search("What is Semantic Kernel?")
for result in results:
    print(result.text)
题型：Open
用途：practice
难度：advanced
评分方法：正确创建 VolatileMemoryStore 得 1 分；正确创建 MemoryTextSearch 得 1 分；正确添加文本得 1 分；正确执行搜索得 1 分；共 4 分。
资料名称：Memory in Semantic Kernel
官方链接：https://learn.microsoft.com/zh-cn/semantic-kernel/memories/
出处章节：全文
是否更新MIRT：否