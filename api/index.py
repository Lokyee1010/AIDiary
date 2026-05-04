"""AI 心情树洞 - Vercel Serverless API (/chat, /phq4)

Vercel 自动识别名为 `app` 的 Flask 实例并把它包成 serverless 函数。
index.html 由 Vercel 直接当静态文件返回,不走这里。
本文件与项目根的 app.py 是同一份业务逻辑(本地开发用 app.py,生产用这个)。
"""

import os
import time
from collections import deque
from threading import Lock

from flask import Flask, jsonify, request
from openai import OpenAI

API_KEY = os.environ.get("KIMI_API_KEY")
if not API_KEY:
    raise RuntimeError(
        "未检测到 KIMI_API_KEY 环境变量,请在 Vercel 项目 Settings → Environment Variables 里添加。"
    )

client = OpenAI(api_key=API_KEY, base_url="https://api.moonshot.cn/v1")

SYSTEM_PROMPT = """你是一位温柔、专业的心理倾听者，熟悉认知行为疗法（CBT）。
当用户向你倾诉时，请严格按照以下两段式格式回复，整体不超过 150 字，语气自然口语化：

第一段【共情】：用 1-2 句话识别并回应用户的情绪，让对方感到被听见。
  示例开头：「听起来你有点难过…」「我能感受到你此刻的疲惫…」「这种委屈一定让你很煎熬…」

第二段【CBT 小建议】：基于认知行为疗法，给出一个简短、具体、当下就能尝试的小行动。
  示例：「试着写下今天发生的一件让你感到一丝轻松的小事」「花两分钟做几次缓慢的深呼吸」。

注意：
- 两段之间用一个空行分隔，不要使用列表、标题或 emoji。
- 不评判、不说教，避免「你应该」「你必须」这类词。
- 不诊断疾病，不替代专业治疗。如果用户表达自伤或危机，请温柔地建议联系信任的人或拨打心理援助热线 400-161-9995。"""


# ---- 简单内存限流:每个 IP 60 秒内最多 10 次 /chat ----
# 注:Vercel serverless 是无状态的,每个实例独立计数。多实例并发时限流会松动,
# 这里仍保留作"单实例尽力而为"的轻防护,不指望它做严格控制。
RATE_LIMIT_WINDOW = 60
RATE_LIMIT_MAX = 10
_rate_buckets: "dict[str, deque]" = {}
_rate_lock = Lock()


def _client_ip() -> str:
    ip = (
        request.headers.get("CF-Connecting-IP")
        or request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or request.remote_addr
        or "unknown"
    )
    return ip


def _rate_limited(ip: str) -> bool:
    now = time.time()
    with _rate_lock:
        bucket = _rate_buckets.setdefault(ip, deque())
        while bucket and bucket[0] <= now - RATE_LIMIT_WINDOW:
            bucket.popleft()
        if len(bucket) >= RATE_LIMIT_MAX:
            return True
        bucket.append(now)
        return False


app = Flask(__name__)


@app.route("/chat", methods=["POST"])
def chat():
    if _rate_limited(_client_ip()):
        return jsonify({"error": "请慢一点，让你的话有时间被听见。等一会儿再说。"}), 429

    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify({"error": "请先写下你想说的话"}), 400

    try:
        completion = client.chat.completions.create(
            model="moonshot-v1-8k",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": message},
            ],
            temperature=0.6,
        )
        reply = completion.choices[0].message.content.strip()
        return jsonify({"reply": reply})
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": f"AI 暂时无法回应：{exc}"}), 502


@app.route("/phq4", methods=["POST"])
def phq4():
    """PHQ-4 焦虑抑郁快速筛查:接收总分,返回分层建议。"""
    data = request.get_json(silent=True) or {}
    score = data.get("score")
    if not isinstance(score, int) or score < 0 or score > 12:
        return jsonify({"error": "请传入有效的 PHQ-4 总分（0-12 的整数）"}), 400

    if score <= 2:
        tier = "正常波动"
        advice = "你的情绪在正常波动范围内，继续保持自我关怀。"
    elif score <= 5:
        tier = "轻度困扰"
        advice = "你有一些轻度情绪困扰，可以尝试我们的日常小工具和日记练习。"
    elif score <= 8:
        tier = "中度困扰"
        advice = "你的情绪困扰较明显，建议关注并考虑与亲友或专业人士聊聊。"
    else:
        tier = "重度困扰"
        advice = "你的情绪困扰程度较高，强烈建议尽快寻求专业心理帮助或咨询医生。"

    ai_comfort = None
    if score >= 6:
        try:
            completion = client.chat.completions.create(
                model="moonshot-v1-8k",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "你是一位温和的心理健康支持者。"
                            "用户刚刚完成了 PHQ-4 情绪筛查，得分偏高。"
                            "请写一段 80 字以内的安抚性话语：语气温暖、不制造焦虑、"
                            "不诊断疾病、鼓励用户照顾自己和寻求支持。"
                            "只返回正文，不加标题、emoji 或列表。"
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"我 PHQ-4 得分是 {score}，想听你说几句。",
                    },
                ],
                temperature=0.5,
            )
            ai_comfort = completion.choices[0].message.content.strip()
        except Exception:
            ai_comfort = None

    return jsonify({"tier": tier, "advice": advice, "score": score, "ai_comfort": ai_comfort})
