from __future__ import annotations

import json
import os
import random
import socket
import uuid

from flask import Flask, jsonify, make_response, request
from copy import deepcopy
from datetime import datetime
from typing import Any, Dict

HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", "5000"))
SAVE_FILE = os.environ.get("SAVE_FILE", "cat_save.json")
COOKIE_NAME = "pocket_cat_player_id"

DEFAULT_STATE: Dict[str, Any] = {
    "cat_name": "奶糖",
    "hunger": 80,
    "mood": 75,
    "clean": 70,
    "energy": 85,
    "affection": 0,
    "coins": 80,
    "day": 1,
    "items": [],
    "last_action": "欢迎来到喵喵治愈屋！今天也要好好照顾小猫呀。",
    "ending": False,
    "updated_at": "",
}

SHOP_ITEMS = {
    "fish": {
        "name": "小鱼干套餐",
        "cost": 25,
        "effect": {"hunger": 35, "mood": 8, "affection": 4},
        "message": "小猫吃到了小鱼干，开心地蹭了蹭你。",
    },
    "ribbon": {
        "name": "蝴蝶结项圈",
        "cost": 55,
        "effect": {"mood": 18, "affection": 12},
        "unique": True,
        "message": "小猫戴上了蝴蝶结，漂亮得像一颗草莓糖。",
    },
    "bed": {
        "name": "云朵猫窝",
        "cost": 85,
        "effect": {"energy": 35, "mood": 10, "affection": 10},
        "unique": True,
        "message": "云朵猫窝软乎乎的，小猫睡得更安心了。",
    },
    "flower": {
        "name": "小花窗帘",
        "cost": 120,
        "effect": {"mood": 25, "affection": 15},
        "unique": True,
        "message": "房间变得更温柔，小猫一直趴在窗边晒太阳。",
    },
}


def clamp(value: int, minimum: int = 0, maximum: int = 100) -> int:
    return max(minimum, min(maximum, int(value)))


def load_all_saves() -> Dict[str, Dict[str, Any]]:
    if not os.path.exists(SAVE_FILE):
        return {}
    try:
        with open(SAVE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def save_all_saves(data: Dict[str, Dict[str, Any]]) -> None:
    with open(SAVE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def make_new_player_id() -> str:
    return uuid.uuid4().hex


def get_state(player_id: str) -> Dict[str, Any]:
    saves = load_all_saves()
    if player_id not in saves:
        state = deepcopy(DEFAULT_STATE)
        state["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        saves[player_id] = state
        save_all_saves(saves)
    return saves[player_id]


def update_state(player_id: str, state: Dict[str, Any]) -> None:
    state["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for key in ["hunger", "mood", "clean", "energy", "affection"]:
        state[key] = clamp(state.get(key, 0))
    state["coins"] = max(0, int(state.get("coins", 0)))
    saves = load_all_saves()
    saves[player_id] = state
    save_all_saves(saves)


def apply_time_cost(state: Dict[str, Any], cost: int = 1) -> None:
    # 每次行动都会消耗一点状态，让游戏形成“照顾 -> 恢复 -> 解锁”的循环。
    state["day"] = int(state.get("day", 1)) + cost
    state["hunger"] = clamp(state.get("hunger", 0) - random.randint(2, 5))
    state["clean"] = clamp(state.get("clean", 0) - random.randint(1, 4))
    state["energy"] = clamp(state.get("energy", 0) - random.randint(1, 4))


def get_cat_face(state: Dict[str, Any]) -> str:
    if state.get("ending"):
        return "😻"
    if state.get("energy", 0) < 25:
        return "😴"
    if state.get("hunger", 0) < 25:
        return "😿"
    if state.get("clean", 0) < 25:
        return "🙀"
    if state.get("mood", 0) > 85 and state.get("affection", 0) > 60:
        return "😻"
    if state.get("mood", 0) > 70:
        return "😺"
    if state.get("mood", 0) < 35:
        return "😾"
    return "🐱"


def get_room_decoration(state: Dict[str, Any]) -> Dict[str, str]:
    items = set(state.get("items", []))
    return {
        "window": "🌸" if "flower" in items else "🪟",
        "bed": "☁️" if "bed" in items else "🧺",
        "neck": "🎀" if "ribbon" in items else "",
    }


def check_ending(state: Dict[str, Any]) -> None:
    average_status = (state["hunger"] + state["mood"] + state["clean"] + state["energy"]) / 4
    if state["affection"] >= 100 and average_status >= 70:
        state["ending"] = True
        state["last_action"] = "隐藏结局解锁：小猫最喜欢你了！它决定永远住在你的治愈小屋里。"


def public_state(state: Dict[str, Any]) -> Dict[str, Any]:
    state = deepcopy(state)
    state["cat_face"] = get_cat_face(state)
    state["decor"] = get_room_decoration(state)
    state["shop"] = [
        {
            "id": item_id,
            "name": info["name"],
            "cost": info["cost"],
            "owned": item_id in state.get("items", []),
            "unique": info.get("unique", False),
        }
        for item_id, info in SHOP_ITEMS.items()
    ]
    return state


def do_game_action(player_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    state = get_state(player_id)
    action = data.get("action")

    if state.get("ending") and action != "reset":
        return public_state(state)

    if action == "feed":
        if state["coins"] < 8:
            state["last_action"] = "金币不够啦，可以先陪小猫玩一会儿或者拍照赚爱心币。"
        else:
            state["coins"] -= 8
            state["hunger"] = clamp(state["hunger"] + 28)
            state["mood"] = clamp(state["mood"] + 5)
            state["affection"] = clamp(state["affection"] + 4)
            state["last_action"] = "你喂了猫粮，小猫满足地眯起了眼睛。"
            apply_time_cost(state)

    elif action == "play":
        if state["energy"] < 15:
            state["last_action"] = "小猫太困啦，先让它睡一会儿吧。"
        else:
            state["mood"] = clamp(state["mood"] + 24)
            state["energy"] = clamp(state["energy"] - 10)
            state["hunger"] = clamp(state["hunger"] - 4)
            state["affection"] = clamp(state["affection"] + 8)
            gained = random.randint(3, 9)
            state["coins"] += gained
            state["last_action"] = f"你陪小猫玩毛线球，亲密度上升，还捡到了 {gained} 枚爱心币。"
            apply_time_cost(state)

    elif action == "bath":
        state["clean"] = clamp(state["clean"] + 32)
        state["mood"] = clamp(state["mood"] - 4)
        state["energy"] = clamp(state["energy"] - 4)
        state["affection"] = clamp(state["affection"] + 3)
        state["last_action"] = "你给小猫洗了澡，虽然它有点不情愿，但现在香香软软的。"
        apply_time_cost(state)

    elif action == "sleep":
        state["energy"] = clamp(state["energy"] + 36)
        state["mood"] = clamp(state["mood"] + 8)
        state["hunger"] = clamp(state["hunger"] - 8)
        state["affection"] = clamp(state["affection"] + 2)
        state["last_action"] = "小猫在你身边睡了一觉，醒来后轻轻蹭了蹭你。"
        apply_time_cost(state)

    elif action == "photo":
        if state["mood"] < 50 or state["clean"] < 40:
            state["last_action"] = "小猫现在不太想拍照，先让它开心一点、干净一点吧。"
        else:
            gained = random.randint(10, 22)
            state["coins"] += gained
            state["mood"] = clamp(state["mood"] - 3)
            state["energy"] = clamp(state["energy"] - 4)
            state["affection"] = clamp(state["affection"] + 5)
            state["last_action"] = f"你给小猫拍了一张可爱照片，收获了 {gained} 枚爱心币。"
            apply_time_cost(state)

    elif action == "shop":
        item_id = data.get("item")
        item = SHOP_ITEMS.get(item_id)
        if not item:
            state["last_action"] = "没有找到这个商品。"
        elif item.get("unique") and item_id in state.get("items", []):
            state["last_action"] = "这个装饰已经买过啦。"
        elif state["coins"] < item["cost"]:
            state["last_action"] = "爱心币不够，先照顾小猫赚一些吧。"
        else:
            state["coins"] -= item["cost"]
            for key, value in item["effect"].items():
                state[key] = clamp(state.get(key, 0) + value)
            if item.get("unique"):
                state.setdefault("items", []).append(item_id)
            state["last_action"] = item["message"]

    elif action == "rename":
        name = str(data.get("name", "")).strip()
        if not name:
            state["last_action"] = "名字不能为空哦。"
        elif len(name) > 8:
            state["last_action"] = "名字太长啦，最多 8 个字符。"
        else:
            state["cat_name"] = name
            state["last_action"] = f"小猫有新名字啦：{name}。"

    elif action == "reset":
        state = deepcopy(DEFAULT_STATE)
        state["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    else:
        state["last_action"] = "这个动作暂时还不能做。"

    check_ending(state)
    update_state(player_id, state)
    return public_state(state)


def get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"


INDEX_HTML = r'''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>喵喵治愈屋</title>
  <style>
    :root {
      --bg1: #fff6fb;
      --bg2: #f0f7ff;
      --card: rgba(255, 255, 255, 0.82);
      --text: #4b3d4f;
      --muted: #8d7d93;
      --shadow: 0 18px 45px rgba(160, 112, 150, 0.22);
      --line: rgba(190, 157, 185, 0.28);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      font-family: "Microsoft YaHei", "PingFang SC", system-ui, sans-serif;
      color: var(--text);
      background:
        radial-gradient(circle at 20% 12%, #ffe1ee 0 13%, transparent 30%),
        radial-gradient(circle at 90% 8%, #dff3ff 0 12%, transparent 28%),
        linear-gradient(135deg, var(--bg1), var(--bg2));
      display: flex;
      justify-content: center;
      padding: 24px;
    }
    .app {
      width: min(1100px, 100%);
      display: grid;
      grid-template-columns: 1.08fr 0.92fr;
      gap: 20px;
    }
    .card {
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 28px;
      box-shadow: var(--shadow);
      backdrop-filter: blur(10px);
    }
    .hero {
      padding: 24px;
      min-height: 670px;
      position: relative;
      overflow: hidden;
    }
    .title-row {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 12px;
      margin-bottom: 14px;
    }
    h1 {
      margin: 0;
      font-size: 32px;
      letter-spacing: 1px;
    }
    .sub {
      margin-top: 8px;
      color: var(--muted);
      font-size: 14px;
    }
    .coin {
      border: 1px solid var(--line);
      background: #fffaf2;
      border-radius: 18px;
      padding: 10px 14px;
      font-weight: 800;
      white-space: nowrap;
    }
    .room {
      margin-top: 18px;
      height: 350px;
      border-radius: 28px;
      border: 1px dashed rgba(180, 130, 174, 0.4);
      background:
        linear-gradient(180deg, rgba(255,255,255,0.7), rgba(255,241,249,0.82)),
        repeating-linear-gradient(90deg, rgba(255, 204, 224, 0.28) 0 18px, rgba(255,255,255,0.2) 18px 36px);
      position: relative;
      overflow: hidden;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .window {
      position: absolute;
      top: 28px;
      right: 34px;
      font-size: 52px;
      filter: drop-shadow(0 8px 14px rgba(120, 90, 130, .16));
    }
    .cat-bed {
      position: absolute;
      bottom: 42px;
      left: 48px;
      font-size: 58px;
      transform: rotate(-6deg);
      opacity: .9;
    }
    .cat-wrap {
      position: relative;
      text-align: center;
      transform: translateY(10px);
      animation: floatCat 3s ease-in-out infinite;
    }
    @keyframes floatCat {
      0%, 100% { transform: translateY(10px); }
      50% { transform: translateY(-2px); }
    }
    .cat {
      font-size: 130px;
      line-height: 1;
      filter: drop-shadow(0 18px 22px rgba(120, 80, 120, .20));
      user-select: none;
    }
    .neck {
      position: absolute;
      left: 50%;
      top: 90px;
      transform: translateX(-50%);
      font-size: 34px;
    }
    .name {
      margin-top: 12px;
      font-size: 24px;
      font-weight: 900;
    }
    .speech {
      margin-top: 18px;
      min-height: 66px;
      padding: 16px 18px;
      border-radius: 22px;
      background: #ffffffb5;
      border: 1px solid var(--line);
      line-height: 1.55;
    }
    .actions {
      margin-top: 18px;
      display: grid;
      grid-template-columns: repeat(5, 1fr);
      gap: 10px;
    }
    button {
      border: none;
      cursor: pointer;
      border-radius: 17px;
      padding: 13px 12px;
      font-size: 15px;
      font-weight: 800;
      color: #5b455c;
      background: linear-gradient(180deg, #fff, #ffeaf3);
      box-shadow: 0 8px 18px rgba(160, 112, 150, .16);
      transition: transform .12s ease, box-shadow .12s ease, opacity .12s ease;
    }
    button:hover { transform: translateY(-2px); box-shadow: 0 12px 24px rgba(160, 112, 150, .22); }
    button:active { transform: translateY(0); }
    .side {
      display: flex;
      flex-direction: column;
      gap: 20px;
    }
    .panel { padding: 20px; }
    .panel h2 {
      margin: 0 0 14px;
      font-size: 21px;
    }
    .stats { display: grid; gap: 14px; }
    .stat-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 7px;
      font-size: 14px;
      font-weight: 800;
    }
    .bar {
      height: 14px;
      border-radius: 999px;
      background: rgba(180, 160, 185, .20);
      overflow: hidden;
      border: 1px solid rgba(180, 160, 185, .18);
    }
    .fill {
      height: 100%;
      width: 0%;
      border-radius: 999px;
      background: linear-gradient(90deg, #ffd2e4, #cceeff);
      transition: width .28s ease;
    }
    .shop-grid {
      display: grid;
      gap: 10px;
    }
    .shop-item {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 10px;
      align-items: center;
      padding: 12px;
      border-radius: 18px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,.56);
    }
    .shop-name { font-weight: 850; }
    .shop-cost { color: var(--muted); font-size: 13px; margin-top: 4px; }
    .shop-item button { padding: 10px 13px; font-size: 13px; }
    .mini {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 10px;
      align-items: center;
    }
    input {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 15px;
      padding: 12px 13px;
      font-size: 15px;
      outline: none;
      background: rgba(255,255,255,.72);
    }
    .footer {
      margin-top: 12px;
      font-size: 12px;
      color: var(--muted);
      line-height: 1.6;
    }
    .ending {
      margin-top: 14px;
      padding: 14px 16px;
      border-radius: 18px;
      background: #fff4d8;
      border: 1px solid rgba(200, 165, 85, .28);
      font-weight: 850;
      display: none;
    }
    @media (max-width: 900px) {
      body { padding: 14px; }
      .app { grid-template-columns: 1fr; }
      .hero { min-height: auto; }
      .actions { grid-template-columns: repeat(2, 1fr); }
      .cat { font-size: 110px; }
    }
  </style>
</head>
<body>
  <main class="app">
    <section class="hero card">
      <div class="title-row">
        <div>
          <h1>喵喵治愈屋</h1>
          <div class="sub">照顾小猫，赚爱心币，解锁温柔小房间。</div>
        </div>
        <div class="coin">💗 <span id="coins">0</span></div>
      </div>

      <div class="room">
        <div class="window" id="window">🪟</div>
        <div class="cat-bed" id="bed">🧺</div>
        <div class="cat-wrap">
          <div class="cat" id="cat">🐱</div>
          <div class="neck" id="neck"></div>
          <div class="name" id="catName">奶糖</div>
        </div>
      </div>

      <div class="speech" id="message">正在加载...</div>
      <div class="ending" id="endingBox">隐藏结局已解锁：小猫最喜欢你了！</div>

      <div class="actions">
        <button onclick="doAction('feed')">🍚 喂食</button>
        <button onclick="doAction('play')">🧶 玩耍</button>
        <button onclick="doAction('bath')">🛁 洗澡</button>
        <button onclick="doAction('sleep')">🌙 睡觉</button>
        <button onclick="doAction('photo')">📷 拍照</button>
      </div>
    </section>

    <aside class="side">
      <section class="panel card">
        <h2>小猫状态</h2>
        <div class="stats" id="stats"></div>
        <div class="footer">目标：亲密度达到 100，并保持整体状态较好，就能触发隐藏结局。</div>
      </section>

      <section class="panel card">
        <h2>爱心商店</h2>
        <div class="shop-grid" id="shop"></div>
      </section>

      <section class="panel card">
        <h2>设置</h2>
        <div class="mini">
          <input id="nameInput" maxlength="8" placeholder="给小猫改名，最多8字" />
          <button onclick="renameCat()">改名</button>
        </div>
        <div class="mini" style="margin-top: 10px;">
          <button onclick="resetGame()" style="width:100%; background:linear-gradient(180deg,#fff,#eef6ff);">重新开始</button>
        </div>
        <div class="footer">进度会保存在项目目录下的 cat_save.json，刷新网页不会丢。</div>
      </section>
    </aside>
  </main>

  <script>
    const statLabels = [
      ['hunger', '🍚 饱腹值'],
      ['mood', '🌈 心情值'],
      ['clean', '✨ 清洁值'],
      ['energy', '🌙 体力值'],
      ['affection', '💞 亲密度']
    ];

    async function loadState() {
      const res = await fetch('/api/state');
      render(await res.json());
    }

    async function doAction(action) {
      const res = await fetch('/api/action', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action })
      });
      render(await res.json());
    }

    async function buyItem(item) {
      const res = await fetch('/api/action', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'shop', item })
      });
      render(await res.json());
    }

    async function renameCat() {
      const name = document.getElementById('nameInput').value.trim();
      const res = await fetch('/api/action', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'rename', name })
      });
      document.getElementById('nameInput').value = '';
      render(await res.json());
    }

    async function resetGame() {
      if (!confirm('确定要重新开始吗？当前进度会被覆盖。')) return;
      const res = await fetch('/api/action', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'reset' })
      });
      render(await res.json());
    }

    function render(state) {
      document.getElementById('coins').textContent = state.coins;
      document.getElementById('cat').textContent = state.cat_face;
      document.getElementById('catName').textContent = state.cat_name;
      document.getElementById('message').textContent = `第 ${state.day} 天：${state.last_action}`;
      document.getElementById('window').textContent = state.decor.window;
      document.getElementById('bed').textContent = state.decor.bed;
      document.getElementById('neck').textContent = state.decor.neck;
      document.getElementById('endingBox').style.display = state.ending ? 'block' : 'none';

      const stats = document.getElementById('stats');
      stats.innerHTML = statLabels.map(([key, label]) => `
        <div>
          <div class="stat-head"><span>${label}</span><span>${state[key]}</span></div>
          <div class="bar"><div class="fill" style="width:${state[key]}%"></div></div>
        </div>
      `).join('');

      const shop = document.getElementById('shop');
      shop.innerHTML = state.shop.map(item => {
        const disabled = item.owned && item.unique;
        const btnText = disabled ? '已拥有' : '购买';
        return `
          <div class="shop-item">
            <div>
              <div class="shop-name">${item.name}</div>
              <div class="shop-cost">需要 ${item.cost} 枚爱心币</div>
            </div>
            <button ${disabled ? 'disabled style="opacity:.55;cursor:not-allowed"' : ''} onclick="buyItem('${item.id}')">${btnText}</button>
          </div>
        `;
      }).join('');
    }

    loadState();
  </script>
</body>
</html>'''


app = Flask(__name__)


def get_request_player() -> tuple[str, bool]:
    player_id = request.cookies.get(COOKIE_NAME)
    if player_id:
        return player_id, False
    return make_new_player_id(), True


def attach_player_cookie(response, player_id: str, is_new_player: bool):
    if is_new_player:
        response.set_cookie(
            COOKIE_NAME,
            player_id,
            max_age=31536000,
            path="/",
            samesite="Lax",
        )
    return response


@app.get("/")
def index():
    player_id, is_new = get_request_player()
    response = make_response(INDEX_HTML)
    response.headers["Content-Type"] = "text/html; charset=utf-8"
    response.headers["Cache-Control"] = "no-store"
    return attach_player_cookie(response, player_id, is_new)


@app.get("/api/state")
def api_state():
    player_id, is_new = get_request_player()
    response = jsonify(public_state(get_state(player_id)))
    response.headers["Cache-Control"] = "no-store"
    return attach_player_cookie(response, player_id, is_new)


@app.post("/api/action")
def api_action():
    player_id, is_new = get_request_player()
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        data = {}
    response = jsonify(do_game_action(player_id, data))
    response.headers["Cache-Control"] = "no-store"
    return attach_player_cookie(response, player_id, is_new)


if __name__ == "__main__":
    local_ip = get_local_ip()
    print("\n====== 喵喵治愈屋启动成功 ======")
    print(f"本机浏览器打开： http://127.0.0.1:{PORT}")
    print(f"同一 WiFi 下手机/其他电脑打开： http://{local_ip}:{PORT}")
    print("云部署时，平台会自动提供公网网址。")
    print("================================\n")
    app.run(host=HOST, port=PORT, debug=False)
