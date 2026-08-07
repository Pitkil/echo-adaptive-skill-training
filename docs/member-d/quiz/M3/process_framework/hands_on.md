题目：在 Python 中创建一个包含两个 Step 的简单 Process：Step1 接收产品名称并生成产品信息，Step2 根据产品信息生成文档。
答案：参考实现如下：
from semantic_kernel import Kernel
from semantic_kernel.processes import ProcessBuilder, KernelProcessStep

class GatherProductInfoStep(KernelProcessStep):
    @kernel_function
    def gather_product_information(self, product_name: str) -> str:
        return f"Product: {product_name}, Category: Electronics"

class GenerateDocumentationStep(KernelProcessStep):
    @kernel_function
    def generate_documentation(self, product_info: str) -> str:
        return f"Documentation for {product_info}: This is a high-quality product."

kernel = Kernel()
builder = ProcessBuilder("DocumentationProcess")
step1 = builder.add_step(GatherProductInfoStep)
step2 = builder.add_step(GenerateDocumentationStep)
builder.add_edge(step1, step2)
process = builder.build()
result = await process.run(kernel=kernel, initial_data={"product_name": "GlowBrew"})
题型：Open
用途：practice
难度：advanced
评分方法：正确创建两个 Step 类（继承 KernelProcessStep）各得 1 分（共 2 分）；正确使用 ProcessBuilder 添加 Step 和 Edge 得 1 分；正确调用 run 得 1 分；共 4 分。
资料名称：How-To: Create your first Process
官方链接：https://learn.microsoft.com/en-us/semantic-kernel/frameworks/process/examples/example-first-process
出处章节：全文
是否更新MIRT：否