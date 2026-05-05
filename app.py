"""AI 心情树洞 - Flask 后端"""

import os
import time
from collections import deque
from threading import Lock

from flask import Flask, jsonify, request, send_from_directory
from openai import OpenAI

API_KEY = os.environ.get("KIMI_API_KEY")
if not API_KEY:
    raise RuntimeError(
        "未检测到 KIMI_API_KEY 环境变量，请先 `export KIMI_API_KEY=sk-...` 后再启动。"
    )

# Kimi 提供 OpenAI 兼容协议，使用官方 openai SDK 即可
client = OpenAI(api_key=API_KEY, base_url="https://api.moonshot.cn/v1")

SYSTEM_PROMPT = """你是一位温柔且专业的 CBT（认知行为疗法）心理倾听者。每次回复严格按下面三段式输出，段与段之间用一个空行分隔，整体不超过 150 字，语气自然口语化。

【共情】用 1 句话回应用户当下的情绪，最好引用 ta 自己的话让 ta 感到被听见。不评判、不说教，避免「你应该 / 你必须」。

【识别】从下面 10 个心理模式里挑 1-3 个最贴合的，用顿号分隔；每个标签后用括号简短点出依据（最好引用用户原话）。如果信息不够就写「信息还不够，我们再聊聊」。
- 社交焦虑：在意他人评价、害怕被讨厌或拒绝
- 自我否定：用「我不行」「我不如别人」给自己贴贬低标签
- 决策困难·拖延：在「该做的」和「想做的」之间反复纠结、回避
- 情绪低落：难过、想哭、说不清原因的低能量
- 反刍思维：反复想同一件事走不出来
- 完美主义：对自己设过高标准，做不到就否定整个人
- 关系焦虑：担心被亲近的人拒绝或失去关系
- 读心术：未经核实就替别人下结论（如「ta 一定觉得我…」）
- 灾难化：把不确定结果想成最坏剧本
- 黑白思维：把自己或事情看成全好/全坏

【行动】给一个 5 分钟内当下就能做的具体 CBT 小练习，例如：重写一个灾难化念头、列出 3 个反例、把「必须现在做完」改成「先做 10 分钟」、做几次方块呼吸。不要鸡汤式建议。

注意：
- 不诊断疾病，不替代专业治疗。
- 不用列表序号、不用 emoji、不用标题之外的 markdown。
- 用户表达自伤或危机时，温柔建议联系信任的人或拨打心理援助热线 400-161-9995。"""


# ---- 简单内存限流：每个 IP 60 秒内最多 10 次 /chat ----
RATE_LIMIT_WINDOW = 60   # 秒
RATE_LIMIT_MAX = 10      # 同一 IP 在窗口内最多次数
_rate_buckets: "dict[str, deque]" = {}
_rate_lock = Lock()


def _client_ip() -> str:
    """从反向代理 header 中拿真实 IP；本地直连时退回 remote_addr。"""
    # Cloudflare Tunnel 会通过 CF-Connecting-IP 传真实 IP
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


app = Flask(__name__, static_folder=".", static_url_path="")


@app.route("/")
def index():
    return send_from_directory(".", "index.html")


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
    except Exception as exc:  # noqa: BLE001 — 把任何上游错误转成可读提示
        return jsonify({"error": f"AI 暂时无法回应：{exc}"}), 502


@app.route("/phq4", methods=["POST"])
def phq4():
    """PHQ-4 焦虑抑郁快速筛查：接收总分，返回分层建议。"""
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


if __name__ == "__main__":
    # 公网通过 Cloudflare Tunnel 转发到本机 5000，这里只监听 localhost
    app.run(host="127.0.0.1", port=5000, debug=False)
