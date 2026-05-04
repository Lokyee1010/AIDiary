---
title: AI 心情树洞
emoji: 🌱
colorFrom: purple
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
short_description: 基于 CBT 与 PHQ-4 的 AI 心理倾听树洞
---

# AI 心情树洞

一个温柔的心理倾听网页应用：写下心事，AI 用认知行为疗法（CBT）的视角回应你。
内置 PHQ-4 焦虑抑郁快速筛查、三件好事日记、本地化历史记录。

> 本工具仅用于自我了解，不能替代专业诊断。如有持续困扰，请拨打心理援助热线 **400-161-9995**。

## 部署需要的环境变量

| Key | 说明 |
|---|---|
| `KIMI_API_KEY` | Moonshot/Kimi 的 API key（在 Space Settings → Secrets 里加） |

## 本地启动

```bash
pip install -r requirements.txt
export KIMI_API_KEY=sk-...
python app.py    # http://127.0.0.1:5000
```
