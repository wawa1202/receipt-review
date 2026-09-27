# 验证证据

`smoke-20260927-final.json` 是当前交付版本的真实 CPU OCR 冒烟报告。输入为自制演示票据，不包含用户真实收据；mode 为 synthetic，不能作为 SROIE 或线上效果。

- 字段准确率 0.75，整单准确率 0，覆盖率 1。
- 商家 `DEMO MART` 被识别为 `DEMOMART`；报告保留该错误，未使用人工改正后的结果评分。
- 重复图片复用原记录、复核历史和原始预测保留均在烟测中验证。
- 发布前运行 `python -m pytest -q`：32 passed；测试依赖有一条 Starlette/httpx 弃用提示，不影响当前测试结果。
- `python -m pip check`：No broken requirements found。

复现：在项目根目录运行 `python -m receipt_review smoke --output reports/smoke-local.json`。字体、依赖或系统变化可能影响文字识别与耗时；字体选择见 `demo.py`。

当前未运行公开 SROIE 完整评估、GPU 训练或线上负载测试。
