# 票据识别与智能审核

在笔记本本地，把收据图片变成**有原文依据、可人工修正、能追溯修改过程**的结构化记录。

当前为 **v0.1 CPU 基线**：真实 OCR + 可解释规则抽取 + 人工复核 + 评估工具。已实现的代码不是训练后的文档理解模型；尚未完成公开 SROIE 留出集实验，不能据此宣称企业级准确率。

## 先操作，不急着看代码

这台电脑的独立环境已经建立，双击根目录的 **`打开票据审核.cmd`**。

1. 浏览器打开 `http://127.0.0.1:8782`。首次识别会加载本地 OCR 模型。
2. 点击“试用自制演示收据”。它不是实际消费凭证。
3. 先看原图上的 TOTAL、CASH 和 CHANGE，理解三者区别。
4. 点击字段下面的“定位证据”，查看算法到底用了哪一行。
5. 当前自制样本的 `DEMO MART` 可能识别为 `DEMOMART`。对照原图修正，填写说明，然后“确认字段”。
6. 到“历史记录”重新打开，检查原始识别没有变、当前值和历史版本已更新。
7. 再点演示按钮，应打开同一记录。去重并不意味着发生了两次消费。
8. 侧边栏“项目构建路线”按文件依赖顺序介绍设计；“实验与边界”说明结果能证明什么。

关闭启动窗口或按 `Ctrl+C` 停止服务。重复双击会复用已经运行的本项目服务。若 8782 被其他程序占用，启动器会明确报错，不会结束其他程序。

## 项目目标和边界

**输入：** 单张 JPEG/PNG 收据，最多 8 MiB、1200 万像素。当前主要适配英文及马来西亚收据。

**输出：** 商家 company、地址 address、日期 date、总金额 total；每项带 OCR 行证据、文字识别分数、抽取方法和风险提示。

**业务闭环：** 图片 → OCR → 候选选择 → 日期/金额标准化 → 风险提示 → 待复核 → 人工确认或拒绝 → 修改历史。

本项目中的“审核”是**检查抽取质量并人工确认字段**。不鉴定真伪、不核验税务、不批准报销、不付款。每一张新图片都待复核；没有自动通过阈值。

## 为什么它值得做，而不只是调用 OCR

- OCR 只告诉你“某处出现了 20.00”；字段抽取必须判断它是总金额、实付还是找零。
- 识别结果带原文位置，人工能核对，不是只返回一个无法解释的 JSON。
- 精确内容去重、原预测保留、修改历史、版本冲突处理是完整流程的必要部分。
- 同时评估“标注文字 → 字段”和“图片 → 字段”，定位文字识别与字段抽取分别损失了多少效果。
- 公开数据对照实验和后续模型改进完成后，才能形成更有分量的算法简历项目。第一版主要建立工程闭环及基线。

## 文件地图：按构建顺序阅读

|顺序|文件|实现的功能|依赖或关联|
|---|---|---|---|
|1|`pyproject.toml`|包配置、依赖、命令入口、测试目录|让 src 下的代码可导入|
|2|`src/receipt_review/schemas.py`|OCRLine 与 Field，坐标、分数、证据格式|所有模块的数据约定|
|3|`normalize.py`|金额/日期/文本规范化|抽取、复核、评分共用|
|4|`extraction.py`|从 OCR 行选出四字段|schemas + normalize|
|5|`review.py`|缺失、低分、歧义、未来日期提示|检查 extraction 的结果和证据|
|6|`store.py`|SQLite、图片摘要去重、人工修改历史、版本冲突|接收 pipeline 和 API 的保存请求|
|7|`ocr.py`|图片内容校验、EXIF 旋正、CPU OCR 适配|将第三方输出转换成 OCRLine|
|8|`pipeline.py`|执行识别完整流程|连接 OCR、抽取、提示、保存|
|9|`demo.py`|生成已知答案的自制演示票据|UI 演示及真实 OCR 冒烟验证|
|10|`api.py`|上传、演示、列表、原图、详情、复核接口|调用 pipeline 和 store|
|11|`static/index.html`|侧边栏、原图证据框、字段表单、历史|调用 API，不重复实现抽取规则|
|12|`data.py`|SROIE 标注解析、ID 配对、文件摘要|提供评估输入，保留文字中的逗号|
|13|`evaluation.py`|字段/整单准确率、覆盖率、错误明细|只评分，不执行推理|
|14|`cli.py`|启动、演示图生成、烟测、SROIE 评估|组织以上模块的命令行调用|
|15|`__main__.py`|支持 python -m receipt_review|转交 cli.main|
|16|`launcher.py`、`打开票据审核.cmd`|双击启动、端口检查、打开浏览器|健康检查后进入本地服务|
|17|`tests/test_core.py`|金额、日期、字段、历史、评估边界|不依赖真实 OCR 模型|
|18|`tests/test_workflow.py`|上传、去重、复核、来源校验等集成测试|注入可控 FakeOCR，避免混淆测试目的|
|19|`tests/test_data.py`|公开标注配对与格式检查|保护评估入口|
|20|`requirements-lock.txt`|这次验证的完整依赖版本|Windows / Python 3.12 重建环境|
|21|`reports/`|验证报告及已知限制|其中 synthetic 结果不能当公开基准|
|22|`docs/`|策划案、按步骤学习、GPU 独立路线、面试题|解释代码的设计取舍|

`__init__.py` 提供包版本；`.gitignore` 排除环境、图片和数据库；`.gitattributes` 统一文本换行。

## 运行资源

|资源|当前是否需要|理由|
|---|---|---|
|本机 Python 3.12|需要|已创建独立 .venv|
|CPU|需要|ONNX Runtime CPU 识别，模型内部每算子两线程|
|4060 8GB|当前不需要|后续训练单列路线，不和 CPU 环境混装|
|无 GPU 的 Dify 服务器|当前不需要|图片、证据、复核均已在本机闭环|
|聊天模型 key|当前不需要|规则基线无 API 费用、无图片外传|
|Milvus / Kafka / Spark / Hive|当前不需要|这里不是向量检索或海量离线数据平台|

## 在另一台电脑复现

在项目根目录的 PowerShell 执行（不要求 activate）：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pip install -e . --no-deps
.\.venv\Scripts\python.exe -m receipt_review serve
```

本机已经安装，不需要重复执行安装。锁定的是验证时可用的版本，不表示所有第三方都是最新版本。`rapidocr-onnxruntime==1.4.4` 使用它自身的旧版接口，与当前 `rapidocr` 包的新接口不同；后续升级只改 OCR 适配器并跑回归。

手动换端口：`python -m receipt_review serve --port 8783`。只绑定 127.0.0.1；没有账户系统，不能直接公开到公网。

## 测试与报告

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m receipt_review smoke --output reports/smoke-local.json
.\.venv\Scripts\python.exe -m pip check
```

单元和接口测试用假 OCR 固定输入；`smoke` 则真实调用 CPU 模型，每次使用新临时数据库，避免将缓存命中当识别速度。它验证去重与复核历史，另外报告自制样本的字段错误，不要求识别“满分”才承认程序能运行。

## 公开 SROIE 数据怎样接入

先取得有使用权限的本地数据，记录来源、版本与许可。当前代码没有下载或分发第三方原图，Git 也忽略 `data/external/`。

适配器接收一个分区的三个平铺目录：

```text
data/external/sroie/development/
  box/       # DOC001.txt：8 个顶点坐标 + 文字
  entities/  # DOC001.txt 或 .json：company/address/date/total
  img/       # DOC001.jpg 或 .png
```

各目录中文件 stem 必须一致；拒绝只取有预测的交集造成虚高分。实体标签只送进评分函数，不能传给抽取器。标注坐标转为矩形后保留标注行顺序；复杂阅读顺序是下一轮误差分析项。

以下 `SOURCE_URL`、`SNAPSHOT_VERSION` 必须替换为真实来源和快照：

```powershell
.\.venv\Scripts\python.exe -m receipt_review evaluate-sroie `
  --boxes data/external/sroie/development/box `
  --labels data/external/sroie/development/entities `
  --mode annotation_text --partition development `
  --source SOURCE_URL --revision SNAPSHOT_VERSION `
  --output reports/sroie-development-text.json

.\.venv\Scripts\python.exe -m receipt_review evaluate-sroie `
  --boxes data/external/sroie/development/box `
  --labels data/external/sroie/development/entities `
  --images data/external/sroie/development/img `
  --mode real_ocr --partition development `
  --source SOURCE_URL --revision SNAPSHOT_VERSION `
  --output reports/sroie-development-ocr.json
```

`annotation_text` 输入人工标注文字，仅评估字段抽取；标注行分数 1.0 是占位值，不是真实 OCR 置信度。`real_ocr` 才从图片跑模型。报告带来源、版本、每个文件摘要、预测、错误与单张耗时。首次耗时包含模型初始化，后续才是热推理，不混写为 p95。

指标是本项目定义的规范化字段 exact match，不是比赛官方 Hmean。覆盖率只统计有无输出，即便输出无效也可能被计为有输出。所有标签必须有合法四字段；如果失败，应先检查标注并记录修订，而不是静默跳过。

先固定开发集和保留测试集；规则和模型只根据开发集改。`--partition` 只是显式记录你的分区声明，不会替你自动完成防泄漏划分。正式报告前还要检查重复图、同商家模板和公开 OCR 预训练数据是否可能污染基准。

## 数据保存在哪里

`runtime/images/` 保存旋正后的规范 PNG；`runtime/receipts.sqlite3` 保存预测、当前值和历史。当前不保留上传文件原始字节与 EXIF，因此不是原件存证系统。按规范 PNG 摘要做精确像素去重；重拍、压缩、裁剪可能绕过它，不声称语义或业务单据去重。

SQLite 事务和版本号解决覆盖问题，但没有用户身份记录与防篡改签名，不能叫合规审计系统。图片写入和 SQLite 不是跨介质事务；数据库失败可能留下无记录图片，需要后续做孤儿文件清理。

## 来源与后续学习

- 业务参考：[Ramp 收据自动化](https://ramp.com/blog/ramp-receipt-automation)。本项目只借鉴公开业务问题，不声称复现其内部实现。
- 标注格式参考：[SROIE 参赛团队仓库](https://github.com/zzzDavid/ICDAR-2019-SROIE)。这是团队方案及修订数据说明，不是企业内部系统；代码 MIT 不等于所有原始票据都能无条件重新分发。
- OCR 组件：[RapidOCR](https://github.com/RapidAI/RapidOCR)，相关模型体系：[PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR)。选择原因是 Windows CPU 部署、坐标输出和替换成本，不是为了堆高 star 库。

完整设计见 `docs/PROJECT-DESIGN.md`；动手路线见 `docs/LEARNING.md`；面试问答见 `docs/INTERVIEW.md`；GPU 独立阶段见 `docs/GPU-ROADMAP.md`。网页侧边栏已经内嵌当前阶段的学习流程，不必来回跳转这些文件才能使用。
