from __future__ import annotations

import json
import os
import random
import socket
import threading
import uuid
from copy import deepcopy
from datetime import datetime
from typing import Any, Dict, Tuple

from flask import Flask, jsonify, make_response, request

HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", "5000"))
SAVE_FILE = os.environ.get("SAVE_FILE", "cat_save.json")
COOKIE_NAME = "pocket_cat_player_id"
SAVE_VERSION = 3
SAVE_LOCK = threading.Lock()

DEFAULT_STATE: Dict[str, Any] = {
    "version": SAVE_VERSION,
    "cat_name": "张予涵",
    "hunger": 82,
    "mood": 76,
    "clean": 72,
    "energy": 86,
    "affection": 0,
    "coins": 100,
    "day": 1,
    "level": 1,
    "exp": 0,
    "action_count": 0,
    "items": [],
    "badges": [],
    "diary": ["你遇见了一只软乎乎的小猫，它好像很喜欢这间小屋。"],
    "last_action": "欢迎来到喵喵治愈屋！今天也要好好照顾小猫呀。",
    "ending": False,
    "updated_at": "",
}

SHOP_ITEMS: Dict[str, Dict[str, Any]] = {
    "fish": {
        "name": "小鱼干套餐",
        "emoji": "🐟",
        "cost": 28,
        "effect": {"hunger": 36, "mood": 8, "affection": 4, "exp": 5},
        "type": "consumable",
        "message": "小猫吃到了小鱼干，开心地蹭了蹭你。",
    },
    "milk": {
        "name": "温热猫牛奶",
        "emoji": "🥛",
        "cost": 22,
        "effect": {"hunger": 20, "energy": 12, "affection": 3, "exp": 4},
        "type": "consumable",
        "message": "小猫喝完温热猫牛奶，舒服地打了个小呼噜。",
    },
    "ribbon": {
        "name": "草莓蝴蝶结",
        "emoji": "🎀",
        "cost": 65,
        "effect": {"mood": 18, "affection": 12, "exp": 12},
        "unique": True,
        "message": "小猫戴上了草莓蝴蝶结，漂亮得像一颗软糖。",
    },
    "toy": {
        "name": "铃铛逗猫棒",
        "emoji": "🪄",
        "cost": 90,
        "effect": {"mood": 18, "affection": 10, "exp": 15},
        "unique": True,
        "message": "铃铛一响，小猫马上进入快乐模式。以后玩耍收益会更高。",
    },
    "brush": {
        "name": "云朵毛刷",
        "emoji": "🪮",
        "cost": 110,
        "effect": {"clean": 22, "mood": 10, "affection": 12, "exp": 15},
        "unique": True,
        "message": "小猫被梳得蓬蓬软软。以后洗澡不会那么抗拒啦。",
    },
    "bed": {
        "name": "云朵猫窝",
        "emoji": "☁️",
        "cost": 130,
        "effect": {"energy": 32, "mood": 12, "affection": 14, "exp": 18},
        "unique": True,
        "message": "云朵猫窝软乎乎的，小猫睡得更安心了。",
    },
    "camera": {
        "name": "爱心拍立得",
        "emoji": "📷",
        "cost": 150,
        "effect": {"mood": 15, "affection": 16, "exp": 20},
        "unique": True,
        "message": "你获得了爱心拍立得。以后拍照能获得更多爱心币。",
    },
    "curtain": {
        "name": "小花窗帘",
        "emoji": "🌸",
        "cost": 170,
        "effect": {"mood": 26, "affection": 18, "exp": 22},
        "unique": True,
        "message": "房间变得更温柔，小猫一直趴在窗边晒太阳。",
    },
    "wallpaper": {
        "name": "星星墙纸",
        "emoji": "🌟",
        "cost": 210,
        "effect": {"mood": 30, "affection": 22, "exp": 28},
        "unique": True,
        "message": "墙上亮起小星星，治愈小屋正式升级啦。",
    },
}

BADGE_RULES = [
    ("first_care", "新手铲屎官", lambda s: s.get("action_count", 0) >= 5),
    ("warm_heart", "温柔陪伴者", lambda s: s.get("affection", 0) >= 40),
    ("best_friend", "小猫最好的朋友", lambda s: s.get("affection", 0) >= 80),
    ("little_rich", "爱心币收藏家", lambda s: s.get("coins", 0) >= 250),
    ("decor_master", "小屋装饰师", lambda s: len([i for i in s.get("items", []) if SHOP_ITEMS.get(i, {}).get("unique")]) >= 4),
    ("happy_home", "治愈小屋毕业", lambda s: bool(s.get("ending"))),
]

RANDOM_EVENTS = [
    {"text": "窗边飞来一只小鸟，小猫看得眼睛亮亮的。", "effect": {"mood": 5, "exp": 2}},
    {"text": "小猫把毛线球滚到了你脚边，好像在邀请你继续陪它。", "effect": {"affection": 3}},
    {"text": "阳光刚好落在猫窝上，小猫舒服地伸了个懒腰。", "effect": {"energy": 5}},
    {"text": "小猫偷偷扒拉零食袋，被你发现后装作无事发生。", "effect": {"hunger": 4, "clean": -2}},
    {"text": "你整理房间时找到了几枚掉在角落里的爱心币。", "effect": {"coins": 8}},
]


def clamp(value: int, minimum: int = 0, maximum: int = 100) -> int:
    return max(minimum, min(maximum, int(value)))


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


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
    tmp = f"{SAVE_FILE}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, SAVE_FILE)


def make_new_player_id() -> str:
    return uuid.uuid4().hex


def migrate_state(state: Dict[str, Any]) -> Dict[str, Any]:
    merged = deepcopy(DEFAULT_STATE)
    if isinstance(state, dict):
        for key, value in state.items():
            if key in merged:
                merged[key] = value
    merged["version"] = SAVE_VERSION
    if not isinstance(merged.get("items"), list):
        merged["items"] = []
    if not isinstance(merged.get("badges"), list):
        merged["badges"] = []
    if not isinstance(merged.get("diary"), list):
        merged["diary"] = []
    if len(merged["diary"]) == 0:
        merged["diary"] = deepcopy(DEFAULT_STATE["diary"])
    normalize_state(merged)
    return merged


def get_state(player_id: str) -> Dict[str, Any]:
    with SAVE_LOCK:
        saves = load_all_saves()
        if player_id not in saves:
            state = deepcopy(DEFAULT_STATE)
            state["updated_at"] = now_text()
            saves[player_id] = state
            save_all_saves(saves)
            return state
        state = migrate_state(saves[player_id])
        saves[player_id] = state
        save_all_saves(saves)
        return state


def update_state(player_id: str, state: Dict[str, Any]) -> None:
    normalize_state(state)
    state["updated_at"] = now_text()
    with SAVE_LOCK:
        saves = load_all_saves()
        saves[player_id] = state
        save_all_saves(saves)


def normalize_state(state: Dict[str, Any]) -> None:
    for key in ["hunger", "mood", "clean", "energy", "affection"]:
        state[key] = clamp(state.get(key, 0))
    state["coins"] = max(0, safe_int(state.get("coins", 0)))
    state["day"] = max(1, safe_int(state.get("day", 1), 1))
    state["exp"] = max(0, safe_int(state.get("exp", 0)))
    state["level"] = max(1, min(20, safe_int(state.get("level", 1), 1)))
    state["action_count"] = max(0, safe_int(state.get("action_count", 0)))
    state["items"] = list(dict.fromkeys([str(i) for i in state.get("items", []) if str(i) in SHOP_ITEMS]))
    state["badges"] = list(dict.fromkeys([str(b) for b in state.get("badges", [])]))
    state["diary"] = [str(x)[:80] for x in state.get("diary", [])][-8:]
    state["cat_name"] = str(state.get("cat_name", "奶糖"))[:8] or "奶糖"


def progress_score(state: Dict[str, Any]) -> int:
    return (
        safe_int(state.get("day")) * 3
        + safe_int(state.get("level")) * 30
        + safe_int(state.get("exp"))
        + safe_int(state.get("affection")) * 2
        + len(state.get("items", [])) * 30
        + len(state.get("badges", [])) * 50
        + (300 if state.get("ending") else 0)
    )


def add_diary(state: Dict[str, Any], text: str) -> None:
    diary = state.setdefault("diary", [])
    if not diary or diary[-1] != text:
        diary.append(text)
    state["diary"] = diary[-8:]


def apply_effect(state: Dict[str, Any], effect: Dict[str, int]) -> None:
    for key, value in effect.items():
        if key in ["hunger", "mood", "clean", "energy", "affection"]:
            state[key] = clamp(state.get(key, 0) + value)
        elif key == "coins":
            state["coins"] = max(0, safe_int(state.get("coins", 0)) + int(value))
        elif key == "exp":
            state["exp"] = max(0, safe_int(state.get("exp", 0)) + int(value))


def has_item(state: Dict[str, Any], item_id: str) -> bool:
    return item_id in state.get("items", [])


def apply_time_cost(state: Dict[str, Any], cost: int = 1) -> None:
    state["day"] = safe_int(state.get("day", 1), 1) + cost
    state["hunger"] = clamp(state.get("hunger", 0) - random.randint(2, 5))
    state["clean"] = clamp(state.get("clean", 0) - random.randint(1, 4))
    state["energy"] = clamp(state.get("energy", 0) - random.randint(1, 4))
    state["action_count"] = safe_int(state.get("action_count", 0)) + 1


def maybe_random_event(state: Dict[str, Any]) -> str:
    if random.random() > 0.22:
        return ""
    event = random.choice(RANDOM_EVENTS)
    apply_effect(state, event["effect"])
    add_diary(state, event["text"])
    return "\n小事件：" + event["text"]


def update_level_and_badges(state: Dict[str, Any]) -> str:
    messages = []
    old_level = safe_int(state.get("level", 1), 1)
    new_level = min(20, safe_int(state.get("exp", 0)) // 55 + 1)
    if new_level > old_level:
        state["level"] = new_level
        reward = (new_level - old_level) * 25
        state["coins"] += reward
        messages.append(f"等级提升到 Lv.{new_level}，奖励 {reward} 枚爱心币。")
        add_diary(state, f"你和小猫的默契提升到了 Lv.{new_level}。")

    owned_badges = set(state.get("badges", []))
    for badge_id, badge_name, predicate in BADGE_RULES:
        try:
            ok = predicate(state)
        except Exception:
            ok = False
        if ok and badge_id not in owned_badges:
            state.setdefault("badges", []).append(badge_id)
            owned_badges.add(badge_id)
            state["coins"] += 18
            messages.append(f"获得成就「{badge_name}」，奖励 18 枚爱心币。")
            add_diary(state, f"获得成就：{badge_name}。")
    return "\n" + "\n".join(messages) if messages else ""


def get_badge_public(state: Dict[str, Any]) -> list[Dict[str, Any]]:
    owned = set(state.get("badges", []))
    return [
        {"id": badge_id, "name": badge_name, "owned": badge_id in owned}
        for badge_id, badge_name, _ in BADGE_RULES
    ]


def get_cat_face(state: Dict[str, Any]) -> str:
    if state.get("ending"):
        return "😻"
    if state.get("energy", 0) < 22:
        return "😴"
    if state.get("hunger", 0) < 22:
        return "😿"
    if state.get("clean", 0) < 22:
        return "🙀"
    if state.get("mood", 0) > 86 and state.get("affection", 0) > 65:
        return "😻"
    if state.get("mood", 0) > 70:
        return "😺"
    if state.get("mood", 0) < 35:
        return "😾"
    return "🐱"


def get_room_decoration(state: Dict[str, Any]) -> Dict[str, str]:
    return {
        "window": "🌸" if has_item(state, "curtain") else "🪟",
        "bed": "☁️" if has_item(state, "bed") else "🧺",
        "neck": "🎀" if has_item(state, "ribbon") else "",
        "toy": "🪄" if has_item(state, "toy") else "🧶",
        "camera": "📷" if has_item(state, "camera") else "",
        "wallpaper": "🌟" if has_item(state, "wallpaper") else "",
    }


def get_status_text(state: Dict[str, Any]) -> str:
    if state.get("ending"):
        return "隐藏结局已解锁"
    low = []
    if state.get("hunger", 0) < 35:
        low.append("有点饿")
    if state.get("mood", 0) < 35:
        low.append("需要陪伴")
    if state.get("clean", 0) < 35:
        low.append("需要洗澡")
    if state.get("energy", 0) < 35:
        low.append("想睡觉")
    return "、".join(low) if low else "状态很好"


def check_ending(state: Dict[str, Any]) -> str:
    average_status = (state["hunger"] + state["mood"] + state["clean"] + state["energy"]) / 4
    unique_items = len([i for i in state.get("items", []) if SHOP_ITEMS.get(i, {}).get("unique")])
    if not state.get("ending") and state["affection"] >= 100 and average_status >= 72 and unique_items >= 3:
        state["ending"] = True
        text = "隐藏结局解锁：小猫最喜欢你了！它决定永远住在你的治愈小屋里。"
        state["last_action"] = text
        add_diary(state, text)
        return "\n" + text
    return ""


def public_state(state: Dict[str, Any]) -> Dict[str, Any]:
    state = deepcopy(state)
    normalize_state(state)
    state["cat_face"] = get_cat_face(state)
    state["decor"] = get_room_decoration(state)
    state["status_text"] = get_status_text(state)
    state["progress_score"] = progress_score(state)
    state["next_level_exp"] = min(20 * 55, (state["level"] * 55))
    state["badges_public"] = get_badge_public(state)
    state["shop"] = [
        {
            "id": item_id,
            "name": info["name"],
            "emoji": info.get("emoji", "🎁"),
            "cost": info["cost"],
            "owned": item_id in state.get("items", []),
            "unique": bool(info.get("unique", False)),
            "type": info.get("type", "decor"),
        }
        for item_id, info in SHOP_ITEMS.items()
    ]
    return state


def do_game_action(player_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    state = get_state(player_id)
    action = data.get("action")

    if state.get("ending") and action not in ["reset", "rename", "export_sync"]:
        return public_state(state)

    msg_extra = ""

    if action == "feed":
        cost = 8
        if state["coins"] < cost:
            state["last_action"] = "爱心币不够啦，可以先陪小猫玩耍、拍照或摸摸它。"
        else:
            state["coins"] -= cost
            apply_effect(state, {"hunger": 28, "mood": 5, "affection": 4, "exp": 6})
            apply_time_cost(state)
            msg_extra += maybe_random_event(state)
            state["last_action"] = "你喂了猫粮，小猫满足地眯起了眼睛。" + msg_extra
            add_diary(state, "你给小猫喂了猫粮。")

    elif action == "pet":
        apply_effect(state, {"mood": 10, "affection": 7, "exp": 5})
        apply_time_cost(state)
        msg_extra += maybe_random_event(state)
        state["last_action"] = "你摸了摸小猫的脑袋，它把尾巴轻轻绕在你手边。" + msg_extra
        add_diary(state, "小猫今天被温柔摸摸了。")

    elif action == "play":
        if state["energy"] < 16:
            state["last_action"] = "小猫太困啦，先让它睡一会儿吧。"
        else:
            bonus = 5 if has_item(state, "toy") else 0
            gained = random.randint(4, 10) + bonus
            apply_effect(state, {"mood": 23 + bonus, "energy": -12, "hunger": -5, "clean": -3, "affection": 8, "coins": gained, "exp": 9 + bonus})
            apply_time_cost(state)
            msg_extra += maybe_random_event(state)
            state["last_action"] = f"你陪小猫玩毛线球，亲密度上升，还获得了 {gained} 枚爱心币。" + msg_extra
            add_diary(state, "你和小猫玩了一会儿。")

    elif action == "bath":
        brush_bonus = 8 if has_item(state, "brush") else 0
        mood_cost = -1 if has_item(state, "brush") else -5
        apply_effect(state, {"clean": 32 + brush_bonus, "mood": mood_cost, "energy": -4, "affection": 4, "exp": 7})
        apply_time_cost(state)
        msg_extra += maybe_random_event(state)
        state["last_action"] = "你给小猫洗了澡，现在它香香软软的。" + ("云朵毛刷让小猫没那么抗拒。" if has_item(state, "brush") else "") + msg_extra
        add_diary(state, "小猫今天洗得香喷喷。")

    elif action == "sleep":
        bed_bonus = 10 if has_item(state, "bed") else 0
        apply_effect(state, {"energy": 36 + bed_bonus, "mood": 8, "hunger": -9, "affection": 3, "exp": 5})
        apply_time_cost(state)
        msg_extra += maybe_random_event(state)
        state["last_action"] = "小猫在你身边睡了一觉，醒来后轻轻蹭了蹭你。" + ("云朵猫窝让它恢复得更好。" if has_item(state, "bed") else "") + msg_extra
        add_diary(state, "小猫睡了一个安心觉。")

    elif action == "photo":
        if state["mood"] < 48 or state["clean"] < 38:
            state["last_action"] = "小猫现在不太想拍照，先让它开心一点、干净一点吧。"
        else:
            camera_bonus = 10 if has_item(state, "camera") else 0
            gained = random.randint(12, 24) + camera_bonus
            apply_effect(state, {"coins": gained, "mood": -3, "energy": -4, "affection": 5, "exp": 8})
            apply_time_cost(state)
            msg_extra += maybe_random_event(state)
            state["last_action"] = f"你给小猫拍了一张可爱照片，收获了 {gained} 枚爱心币。" + msg_extra
            add_diary(state, "你拍下了一张小猫的可爱照片。")

    elif action == "shop":
        item_id = str(data.get("item", ""))
        item = SHOP_ITEMS.get(item_id)
        if not item:
            state["last_action"] = "没有找到这个商品。"
        elif item.get("unique") and item_id in state.get("items", []):
            state["last_action"] = "这个装饰已经买过啦。"
        elif state["coins"] < item["cost"]:
            state["last_action"] = "爱心币不够，先照顾小猫赚一些吧。"
        else:
            state["coins"] -= item["cost"]
            apply_effect(state, item["effect"])
            if item.get("unique"):
                state.setdefault("items", []).append(item_id)
            state["last_action"] = item["message"]
            add_diary(state, f"你购买了{item['name']}。")

    elif action == "rename":
        name = str(data.get("name", "")).strip()
        if not name:
            state["last_action"] = "名字不能为空哦。"
        elif len(name) > 8:
            state["last_action"] = "名字太长啦，最多 8 个字符。"
        else:
            state["cat_name"] = name
            state["last_action"] = f"小猫有新名字啦：{name}。"
            add_diary(state, f"小猫有了新名字：{name}。")

    elif action == "import":
        incoming = data.get("state")
        if isinstance(incoming, dict):
            incoming = migrate_state(incoming)
            if progress_score(incoming) >= progress_score(state):
                state = incoming
                state["last_action"] = "已恢复本机备份存档。"
            else:
                state["last_action"] = "当前云端进度更高，没有覆盖存档。"
        else:
            state["last_action"] = "导入失败，存档格式不正确。"

    elif action == "reset":
        state = deepcopy(DEFAULT_STATE)
        state["updated_at"] = now_text()

    else:
        state["last_action"] = "这个动作暂时还不能做。"

    check_ending(state)
    state["last_action"] += update_level_and_badges(state)
    normalize_state(state)
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
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
  <meta name="theme-color" content="#fff1f7" />
  <meta name="apple-mobile-web-app-capable" content="yes" />
  <meta name="apple-mobile-web-app-title" content="喵喵治愈屋" />
  <link rel="manifest" href="/manifest.webmanifest" />
  <link rel="apple-touch-icon" href="/icon.svg" />
  <title>喵喵治愈屋</title>
  <style>
    :root {
      --bg1: #fff7fb;
      --bg2: #edf8ff;
      --card: rgba(255, 255, 255, 0.86);
      --text: #493a50;
      --muted: #8d7d93;
      --pink: #ff9fc7;
      --rose: #ffd7e8;
      --blue: #a7ddff;
      --gold: #f2c94c;
      --shadow: 0 18px 46px rgba(158, 112, 150, 0.22);
      --line: rgba(190, 157, 185, 0.28);
      --safe-bottom: env(safe-area-inset-bottom, 0px);
    }
    * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
    html, body { margin: 0; min-height: 100%; }
    body {
      min-height: 100vh;
      min-height: 100dvh;
      font-family: "Microsoft YaHei", "PingFang SC", system-ui, sans-serif;
      color: var(--text);
      background:
        radial-gradient(circle at 16% 8%, #ffe0ee 0 13%, transparent 29%),
        radial-gradient(circle at 90% 7%, #dff4ff 0 12%, transparent 31%),
        radial-gradient(circle at 50% 100%, #fff1c9 0 16%, transparent 36%),
        linear-gradient(135deg, var(--bg1), var(--bg2));
      display: flex;
      justify-content: center;
      padding: 18px;
      overflow-x: hidden;
    }
    .app {
      width: min(1180px, 100%);
      display: grid;
      grid-template-columns: 1.02fr .98fr;
      gap: 18px;
    }
    .card {
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 30px;
      box-shadow: var(--shadow);
      backdrop-filter: blur(10px);
    }
    .hero {
      padding: 20px;
      min-height: 720px;
      position: relative;
      overflow: hidden;
      display: flex;
      flex-direction: column;
    }
    .title-row {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 12px;
      margin-bottom: 10px;
    }
    h1 { margin: 0; font-size: 32px; letter-spacing: 1px; }
    .sub { margin-top: 8px; color: var(--muted); font-size: 14px; line-height: 1.55; }
    .top-badges { display: flex; gap: 8px; flex-wrap: wrap; justify-content: flex-end; }
    .pill {
      border: 1px solid var(--line);
      background: rgba(255,255,255,.72);
      border-radius: 999px;
      padding: 9px 12px;
      font-weight: 900;
      white-space: nowrap;
      font-size: 14px;
    }
    .status-overview {
      display: grid;
      grid-template-columns: repeat(5, 1fr);
      gap: 8px;
      margin: 10px 0 12px;
    }
    .mini-stat {
      min-width: 0;
      border: 1px solid var(--line);
      background: rgba(255,255,255,.72);
      border-radius: 18px;
      padding: 8px 9px;
      box-shadow: 0 8px 18px rgba(160, 112, 150, .08);
    }
    .mini-stat .label { font-size: 12px; color: var(--muted); font-weight: 900; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .mini-stat .num { font-size: 18px; font-weight: 950; margin-top: 2px; }
    .mini-bar { height: 7px; border-radius: 999px; background: rgba(180,160,185,.18); overflow: hidden; margin-top: 5px; }
    .mini-fill { height: 100%; width: 0%; border-radius: 999px; background: linear-gradient(90deg, #ffc9df, #bfeaff); transition: width .25s ease; }
    .room {
      flex: 1;
      min-height: 370px;
      border-radius: 30px;
      border: 1px dashed rgba(180, 130, 174, 0.42);
      background:
        linear-gradient(180deg, rgba(255,255,255,0.64), rgba(255,241,249,0.86)),
        repeating-linear-gradient(90deg, rgba(255, 204, 224, 0.28) 0 18px, rgba(255,255,255,0.2) 18px 36px);
      position: relative;
      overflow: hidden;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .room::before {
      content: "";
      position: absolute;
      left: 0; right: 0; bottom: 0;
      height: 32%;
      background: linear-gradient(180deg, rgba(255,255,255,0), rgba(255,230,241,.78));
      border-top: 1px solid rgba(180,130,174,.16);
    }
    .room.flash::after {
      content: "";
      position: absolute;
      inset: 0;
      background: rgba(255,255,255,.78);
      animation: flash .38s ease-out forwards;
      pointer-events: none;
      z-index: 6;
    }
    @keyframes flash { from { opacity: 1; } to { opacity: 0; } }
    .wallpaper {
      position: absolute; inset: 0; opacity: 0; pointer-events: none;
      background-image: radial-gradient(circle, rgba(242,201,76,.72) 1.5px, transparent 2.8px);
      background-size: 34px 34px;
      transition: opacity .25s ease;
    }
    .window { position: absolute; top: 22px; right: 30px; font-size: 52px; filter: drop-shadow(0 8px 14px rgba(120, 90, 130, .16)); }
    .toy { position: absolute; bottom: 48px; right: 58px; font-size: 44px; transform: rotate(8deg); opacity: .92; }
    .camera-dec { position: absolute; top: 100px; left: 34px; font-size: 34px; opacity: .9; }
    .cat-bed { position: absolute; bottom: 34px; left: 42px; font-size: 58px; transform: rotate(-6deg); opacity: .92; }
    .cat-stage {
      position: relative;
      width: 300px;
      height: 280px;
      display: flex;
      justify-content: center;
      align-items: flex-end;
      cursor: pointer;
      z-index: 2;
      transform: translateY(8px);
    }
    .feedback-layer {
      position: absolute;
      inset: -20px;
      pointer-events: none;
      z-index: 5;
      overflow: visible;
    }
    .floaty {
      position: absolute;
      left: 50%; top: 50%;
      font-size: 26px;
      animation: floaty 900ms ease-out forwards;
      filter: drop-shadow(0 8px 12px rgba(120,80,120,.18));
    }
    @keyframes floaty {
      0% { transform: translate(-50%, -10%) scale(.72) rotate(0deg); opacity: 0; }
      20% { opacity: 1; }
      100% { transform: translate(calc(-50% + var(--dx)), calc(-90% + var(--dy))) scale(1.08) rotate(var(--rot)); opacity: 0; }
    }
    .royal-cat {
      position: relative;
      width: 220px;
      height: 230px;
      animation: royalFloat 3.2s ease-in-out infinite;
      transform-origin: 50% 88%;
      filter: drop-shadow(0 20px 24px rgba(110, 82, 125, .22));
    }
    @keyframes royalFloat { 0%, 100% { transform: translateY(3px); } 50% { transform: translateY(-7px); } }
    .cat-tail {
      position: absolute;
      width: 92px;
      height: 136px;
      right: -22px;
      bottom: 39px;
      border-radius: 70px 70px 70px 20px;
      background: linear-gradient(130deg, #ffffff, #edf0f4 72%);
      border: 2px solid rgba(214,218,226,.85);
      transform: rotate(30deg);
      transform-origin: 25% 85%;
      box-shadow: inset -12px -10px 18px rgba(199,207,218,.42);
    }
    .cat-tail::after {
      content: "";
      position: absolute;
      width: 52px;
      height: 88px;
      left: 8px;
      top: 16px;
      border-radius: 50%;
      background: rgba(255,255,255,.92);
    }
    .cat-body {
      position: absolute;
      width: 150px;
      height: 128px;
      left: 39px;
      bottom: 20px;
      border-radius: 48% 48% 42% 42%;
      background: radial-gradient(circle at 42% 24%, #fff, #fbfcff 45%, #e8edf4 100%);
      border: 2px solid rgba(214,218,226,.85);
      box-shadow: inset -10px -16px 20px rgba(199,207,218,.34);
    }
    .cat-chest {
      position: absolute;
      width: 86px;
      height: 88px;
      left: 70px;
      bottom: 36px;
      border-radius: 50%;
      background: radial-gradient(circle, #fff 0 48%, rgba(245,247,252,.96) 76%, transparent 78%);
    }
    .cat-head {
      position: absolute;
      width: 140px;
      height: 124px;
      left: 45px;
      top: 16px;
      border-radius: 46% 46% 42% 42%;
      background: radial-gradient(circle at 44% 24%, #ffffff, #fbfcff 50%, #e8edf4 100%);
      border: 2px solid rgba(214,218,226,.86);
      box-shadow: inset -9px -12px 16px rgba(199,207,218,.32);
      z-index: 3;
    }
    .cat-ear {
      position: absolute;
      width: 44px;
      height: 54px;
      top: -31px;
      background: linear-gradient(135deg, #ffffff, #edf0f4);
      border: 2px solid rgba(214,218,226,.86);
      border-radius: 10px 34px 10px 34px;
      z-index: -1;
    }
    .cat-ear.left { left: 13px; transform: rotate(-23deg); }
    .cat-ear.right { right: 13px; transform: rotate(68deg); }
    .cat-ear::after {
      content: "";
      position: absolute;
      width: 19px;
      height: 25px;
      left: 11px;
      top: 16px;
      border-radius: 10px 20px 10px 20px;
      background: rgba(255, 197, 219, .58);
    }
    .crown {
      position: absolute;
      left: 50%;
      top: -42px;
      transform: translateX(-50%) rotate(-4deg);
      font-size: 36px;
      color: var(--gold);
      text-shadow: 0 2px 0 #fff, 0 6px 14px rgba(160, 112, 80, .28);
      z-index: 6;
      user-select: none;
    }
    .cat-eye {
      position: absolute;
      width: 18px;
      height: 24px;
      top: 47px;
      border-radius: 50%;
      background: radial-gradient(circle at 35% 32%, #fff 0 12%, #89c6dc 13% 32%, #335969 33% 100%);
      box-shadow: 0 0 0 2px rgba(48,70,80,.05);
    }
    .cat-eye.left { left: 38px; }
    .cat-eye.right { right: 38px; }
    .cat-nose {
      position: absolute;
      width: 14px;
      height: 10px;
      left: 63px;
      top: 73px;
      background: #ef9eb6;
      border-radius: 50% 50% 56% 56%;
    }
    .cat-mouth {
      position: absolute;
      width: 36px;
      height: 20px;
      left: 52px;
      top: 82px;
    }
    .cat-mouth::before,
    .cat-mouth::after {
      content: "";
      position: absolute;
      width: 17px;
      height: 12px;
      border-bottom: 2px solid #7f697a;
      border-radius: 50%;
      top: 0;
    }
    .cat-mouth::before { left: 2px; transform: rotate(8deg); }
    .cat-mouth::after { right: 2px; transform: rotate(-8deg); }
    .whisker {
      position: absolute;
      width: 38px;
      height: 2px;
      background: rgba(126, 111, 130, .58);
      border-radius: 999px;
      top: 74px;
    }
    .whisker.l1 { left: -22px; transform: rotate(8deg); }
    .whisker.l2 { left: -24px; top: 86px; transform: rotate(-8deg); }
    .whisker.r1 { right: -22px; transform: rotate(-8deg); }
    .whisker.r2 { right: -24px; top: 86px; transform: rotate(8deg); }
    .cat-paw {
      position: absolute;
      width: 42px;
      height: 34px;
      bottom: 12px;
      border-radius: 50%;
      background: linear-gradient(180deg, #fff, #eef2f7);
      border: 2px solid rgba(214,218,226,.82);
      z-index: 4;
    }
    .cat-paw.left { left: 65px; }
    .cat-paw.right { right: 54px; }
    .necklace {
      position: absolute;
      left: 49%;
      top: 102px;
      transform: translateX(-50%);
      font-size: 30px;
      z-index: 5;
      filter: drop-shadow(0 4px 8px rgba(120,80,120,.12));
    }
    .royal-cat.low-hunger .cat-eye { transform: scaleY(.72); }
    .royal-cat.low-energy .cat-eye { transform: scaleY(.35); }
    .royal-cat.low-mood .cat-mouth { transform: rotate(180deg); top: 92px; }
    .royal-cat.dirty .cat-body::after,
    .royal-cat.dirty .cat-head::after {
      content: ""; position: absolute; width: 16px; height: 10px; border-radius: 50%; background: rgba(155,118,88,.18);
    }
    .royal-cat.dirty .cat-body::after { left: 28px; top: 42px; }
    .royal-cat.dirty .cat-head::after { right: 28px; top: 32px; }
    .royal-cat.anim-feed .cat-head { animation: feedHead .62s ease; }
    .royal-cat.anim-feed .cat-mouth { animation: chew .62s ease; }
    @keyframes feedHead { 0%,100%{ transform: translateY(0); } 35%{ transform: translateY(8px) rotate(2deg); } 70%{ transform: translateY(3px) rotate(-1deg); } }
    @keyframes chew { 0%,100%{ transform: scaleX(1); } 40%{ transform: scaleX(.72); } 70%{ transform: scaleX(1.2); } }
    .royal-cat.anim-pet { animation: petNuzzle .72s ease; }
    @keyframes petNuzzle { 0%,100%{ transform: translateY(0) rotate(0); } 30%{ transform: translate(-10px,-4px) rotate(-4deg); } 65%{ transform: translate(8px,-3px) rotate(3deg); } }
    .royal-cat.anim-play { animation: playJump .74s cubic-bezier(.2,.7,.2,1); }
    .royal-cat.anim-play .cat-tail { animation: tailSwing .7s ease; }
    @keyframes playJump { 0%,100%{ transform: translateY(0) rotate(0); } 45%{ transform: translateY(-42px) rotate(-6deg); } 70%{ transform: translateY(-12px) rotate(5deg); } }
    @keyframes tailSwing { 0%,100%{ transform: rotate(30deg); } 35%{ transform: rotate(55deg); } 70%{ transform: rotate(12deg); } }
    .royal-cat.anim-bath { animation: bathShake .75s ease; }
    @keyframes bathShake { 0%,100%{ transform: translateX(0); } 15%{ transform: translateX(-9px) rotate(-3deg); } 30%{ transform: translateX(8px) rotate(3deg); } 45%{ transform: translateX(-7px) rotate(-2deg); } 60%{ transform: translateX(6px) rotate(2deg); } }
    .royal-cat.anim-sleep { animation: sleepCurl 1.0s ease; }
    .royal-cat.anim-sleep .cat-eye { transform: scaleY(.2); }
    @keyframes sleepCurl { 0%,100%{ transform: translateY(0) scale(1); } 50%{ transform: translateY(8px) scale(.94) rotate(2deg); } }
    .royal-cat.anim-photo { animation: photoPose .72s ease; }
    @keyframes photoPose { 0%,100%{ transform: translateY(0) rotate(0); } 25%{ transform: translateY(-8px) rotate(-3deg); } 55%{ transform: translateY(-8px) rotate(3deg); } }
    .cat-name-row { text-align: center; z-index: 3; position: relative; margin-top: -2px; }
    .name { font-size: 24px; font-weight: 950; }
    .status-line { margin-top: 3px; color: var(--muted); font-size: 13px; }
    .speech {
      margin-top: 12px;
      min-height: 64px;
      padding: 13px 16px;
      border-radius: 22px;
      background: rgba(255,255,255,.76);
      border: 1px solid var(--line);
      line-height: 1.5;
      white-space: pre-line;
      font-size: 14px;
    }
    .ending {
      margin-top: 10px;
      padding: 13px 15px;
      border-radius: 18px;
      background: #fff4d8;
      border: 1px solid rgba(200, 165, 85, .28);
      font-weight: 900;
      display: none;
    }
    .actions { margin-top: 12px; display: grid; grid-template-columns: repeat(6, 1fr); gap: 10px; }
    button {
      border: none;
      cursor: pointer;
      border-radius: 18px;
      padding: 13px 12px;
      font-size: 15px;
      font-weight: 900;
      color: #5b455c;
      background: linear-gradient(180deg, #fff, #ffeaf3);
      box-shadow: 0 8px 18px rgba(160, 112, 150, .15);
      transition: transform .12s ease, box-shadow .12s ease, opacity .12s ease;
    }
    button:hover { transform: translateY(-2px); box-shadow: 0 12px 24px rgba(160, 112, 150, .22); }
    button:active { transform: translateY(0) scale(.98); }
    button:disabled { opacity: .55; cursor: not-allowed; transform: none; }
    .side { display: flex; flex-direction: column; gap: 18px; }
    .panel { padding: 18px; }
    .panel-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 14px; }
    .panel h2 { margin: 0; font-size: 21px; }
    .close-panel { display: none; padding: 8px 12px; border-radius: 999px; font-size: 13px; background: rgba(255,255,255,.82); }
    .stats { display: grid; gap: 12px; }
    .stat-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 7px; font-size: 14px; font-weight: 900; }
    .bar { height: 14px; border-radius: 999px; background: rgba(180, 160, 185, .20); overflow: hidden; border: 1px solid rgba(180, 160, 185, .18); }
    .fill { height: 100%; width: 0%; border-radius: 999px; background: linear-gradient(90deg, #ffd2e4, #cceeff); transition: width .28s ease; }
    .shop-grid { display: grid; gap: 10px; max-height: 410px; overflow: auto; padding-right: 4px; }
    .shop-item { display: grid; grid-template-columns: 38px 1fr auto; gap: 10px; align-items: center; padding: 12px; border-radius: 18px; border: 1px solid var(--line); background: rgba(255,255,255,.58); }
    .shop-emoji { font-size: 28px; }
    .shop-name { font-weight: 950; }
    .shop-cost { color: var(--muted); font-size: 13px; margin-top: 4px; }
    .shop-item button { padding: 10px 13px; font-size: 13px; }
    .mini { display: grid; grid-template-columns: 1fr auto; gap: 10px; align-items: center; }
    input, textarea {
      width: 100%; border: 1px solid var(--line); border-radius: 15px; padding: 12px 13px; font-size: 15px; outline: none; background: rgba(255,255,255,.72); color: var(--text);
    }
    textarea { min-height: 76px; resize: vertical; }
    .footer { margin-top: 12px; font-size: 12px; color: var(--muted); line-height: 1.65; }
    .badge-list { display: flex; gap: 8px; flex-wrap: wrap; }
    .badge { padding: 8px 10px; border-radius: 999px; border: 1px solid var(--line); background: rgba(255,255,255,.6); font-size: 12px; font-weight: 900; }
    .badge.locked { opacity: .42; filter: grayscale(.7); }
    .diary { display: grid; gap: 8px; font-size: 13px; color: var(--muted); line-height: 1.55; }
    .diary div { padding: 9px 11px; border-radius: 14px; background: rgba(255,255,255,.52); border: 1px solid rgba(190,157,185,.20); }
    .sync-box { display: none; margin-top: 10px; padding: 12px; border-radius: 16px; border: 1px solid rgba(255, 172, 90, .35); background: rgba(255, 245, 225, .8); font-size: 13px; line-height: 1.6; }
    .sync-box button { margin-top: 8px; padding: 9px 12px; font-size: 13px; }
    .toast { position: fixed; left: 50%; bottom: 18px; transform: translateX(-50%) translateY(20px); opacity: 0; background: rgba(73,58,80,.92); color: #fff; padding: 12px 16px; border-radius: 999px; box-shadow: var(--shadow); transition: all .2s ease; z-index: 50; font-size: 14px; }
    .toast.show { opacity: 1; transform: translateX(-50%) translateY(0); }
    .mobile-tabs { display: none; }
    @media (max-width: 960px) {
      body { padding: 12px; }
      .app { grid-template-columns: 1fr; }
      .hero { min-height: auto; }
      .title-row { flex-direction: column; }
      .top-badges { justify-content: flex-start; }
      .actions { grid-template-columns: repeat(3, 1fr); }
      .side { display: flex; }
    }
    @media (max-width: 720px) {
      body { padding: 0; overflow: hidden; }
      .app {
        width: 100%;
        height: 100vh;
        height: 100dvh;
        display: block;
        padding: 8px 8px calc(70px + var(--safe-bottom));
      }
      .hero {
        height: calc(100vh - 78px - var(--safe-bottom));
        height: calc(100dvh - 78px - var(--safe-bottom));
        min-height: 0;
        padding: 11px;
        border-radius: 24px;
      }
      h1 { font-size: 22px; }
      .sub { display: none; }
      .title-row { flex-direction: row; align-items: center; margin-bottom: 4px; }
      .top-badges { gap: 5px; justify-content: flex-end; }
      .pill { font-size: 12px; padding: 7px 8px; }
      .status-overview { grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 5px; margin: 7px 0 8px; }
      .mini-stat { padding: 6px 4px; border-radius: 13px; text-align: center; }
      .mini-stat .label { font-size: 10px; }
      .mini-stat .num { font-size: 15px; }
      .mini-bar { height: 5px; margin-top: 3px; }
      .room { min-height: 0; flex: 1; border-radius: 22px; }
      .cat-stage { width: 240px; height: 218px; transform: translateY(2px) scale(.88); }
      .window { top: 14px; right: 18px; font-size: 40px; }
      .cat-bed { left: 22px; bottom: 24px; font-size: 42px; }
      .toy { right: 26px; bottom: 34px; font-size: 34px; }
      .camera-dec { left: 20px; top: 70px; font-size: 28px; }
      .cat-name-row { margin-top: -3px; }
      .name { font-size: 20px; }
      .status-line { font-size: 12px; }
      .speech { min-height: 52px; max-height: 72px; overflow: auto; margin-top: 8px; padding: 10px 12px; border-radius: 18px; font-size: 13px; }
      .ending { margin-top: 6px; padding: 9px 10px; font-size: 12px; }
      .sync-box { position: fixed; left: 12px; right: 12px; bottom: calc(78px + var(--safe-bottom)); z-index: 30; }
      .actions { margin-top: 8px; grid-template-columns: repeat(3, 1fr); gap: 7px; }
      button { border-radius: 15px; padding: 10px 6px; font-size: 13px; }
      .side {
        position: fixed;
        left: 8px; right: 8px;
        bottom: calc(74px + var(--safe-bottom));
        z-index: 22;
        display: none;
        max-height: 62vh;
        gap: 0;
      }
      .side.open { display: block; }
      .panel { display: none; padding: 14px; border-radius: 24px; max-height: 62vh; overflow: auto; }
      .panel.active { display: block; }
      .panel h2 { font-size: 19px; }
      .close-panel { display: inline-flex; }
      .shop-grid { max-height: 44vh; }
      .shop-item { grid-template-columns: 34px 1fr auto; padding: 10px; }
      .shop-emoji { font-size: 25px; }
      .mobile-tabs {
        position: fixed;
        left: 0; right: 0; bottom: 0;
        height: calc(66px + var(--safe-bottom));
        padding: 8px 8px calc(8px + var(--safe-bottom));
        background: rgba(255,255,255,.86);
        border-top: 1px solid var(--line);
        backdrop-filter: blur(12px);
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 7px;
        z-index: 24;
      }
      .mobile-tabs button { box-shadow: none; padding: 9px 4px; font-size: 12px; background: linear-gradient(180deg, #fff, #f7edff); }
      .toast { bottom: calc(78px + var(--safe-bottom)); max-width: 92vw; text-align: center; }
    }
    @media (max-height: 720px) and (max-width: 720px) {
      .cat-stage { transform: translateY(0) scale(.78); }
      .speech { max-height: 58px; }
      .actions button { padding: 8px 5px; }
    }
  </style>
</head>
<body>
  <main class="app">
    <section class="hero card">
      <div class="title-row">
        <div>
          <h1>喵喵治愈屋</h1>
          <div class="sub">照顾高贵白猫，赚爱心币，升级小屋，解锁隐藏结局。</div>
        </div>
        <div class="top-badges">
          <div class="pill">💗 <span id="coins">0</span></div>
          <div class="pill">Lv.<span id="level">1</span></div>
          <div class="pill">第 <span id="day">1</span> 天</div>
        </div>
      </div>

      <div class="status-overview" id="quickStats"></div>

      <div class="room" id="room">
        <div class="wallpaper" id="wallpaper"></div>
        <div class="window" id="window">🪟</div>
        <div class="camera-dec" id="cameraDec"></div>
        <div class="cat-bed" id="bed">🧺</div>
        <div class="toy" id="toy">🧶</div>
        <div class="cat-stage" onclick="doAction('pet')" aria-label="摸摸小猫">
          <div class="feedback-layer" id="feedbackLayer"></div>
          <div class="royal-cat" id="catModel">
            <div class="cat-tail"></div>
            <div class="cat-body"></div>
            <div class="cat-chest"></div>
            <div class="cat-head">
              <div class="cat-ear left"></div>
              <div class="cat-ear right"></div>
              <div class="crown">♛</div>
              <div class="cat-eye left"></div>
              <div class="cat-eye right"></div>
              <div class="cat-nose"></div>
              <div class="cat-mouth"></div>
              <div class="whisker l1"></div>
              <div class="whisker l2"></div>
              <div class="whisker r1"></div>
              <div class="whisker r2"></div>
            </div>
            <div class="necklace" id="neck"></div>
            <div class="cat-paw left"></div>
            <div class="cat-paw right"></div>
          </div>
        </div>
      </div>

      <div class="cat-name-row">
        <div class="name" id="catName">奶糖</div>
        <div class="status-line" id="statusText">状态很好</div>
      </div>
      <div class="speech" id="message">正在加载...</div>
      <div class="ending" id="endingBox">隐藏结局已解锁：小猫最喜欢你了！</div>
      <div class="sync-box" id="syncBox">
        检测到你手机/浏览器里有一份更高进度的本地备份，可以恢复到云端。
        <br><button onclick="restoreLocalBackup()">恢复本机备份</button>
      </div>

      <div class="actions">
        <button onclick="doAction('feed')">🍚 喂食</button>
        <button onclick="doAction('pet')">🤲 摸摸</button>
        <button onclick="doAction('play')">🧶 玩耍</button>
        <button onclick="doAction('bath')">🛁 洗澡</button>
        <button onclick="doAction('sleep')">🌙 睡觉</button>
        <button onclick="doAction('photo')">📷 拍照</button>
      </div>
    </section>

    <aside class="side" id="sidePanels">
      <section class="panel card active" id="panel-status">
        <div class="panel-head"><h2>小猫状态</h2><button class="close-panel" onclick="closeWindow()">收起</button></div>
        <div class="stats" id="stats"></div>
        <div class="footer">目标：亲密度达到 100，整体状态保持较好，并至少拥有 3 个房间装饰。</div>
      </section>

      <section class="panel card" id="panel-shop">
        <div class="panel-head"><h2>爱心商店</h2><button class="close-panel" onclick="closeWindow()">收起</button></div>
        <div class="shop-grid" id="shop"></div>
      </section>

      <section class="panel card" id="panel-diary">
        <div class="panel-head"><h2>日记与成就</h2><button class="close-panel" onclick="closeWindow()">收起</button></div>
        <div class="badge-list" id="badges"></div>
        <div class="diary" id="diary" style="margin-top:12px;"></div>
      </section>

      <section class="panel card" id="panel-settings">
        <div class="panel-head"><h2>设置</h2><button class="close-panel" onclick="closeWindow()">收起</button></div>
        <div class="mini">
          <input id="nameInput" maxlength="8" placeholder="给小猫改名，最多8字" />
          <button onclick="renameCat()">改名</button>
        </div>
        <div class="mini" style="margin-top: 10px; grid-template-columns: 1fr 1fr;">
          <button onclick="exportSave()" style="background:linear-gradient(180deg,#fff,#eef6ff);">导出存档</button>
          <button onclick="resetGame()" style="background:linear-gradient(180deg,#fff,#fff0ef);">重新开始</button>
        </div>
        <textarea id="importText" placeholder="把导出的存档粘贴到这里，可以恢复进度" style="margin-top:10px;"></textarea>
        <button onclick="importSaveText()" style="width:100%; margin-top:10px; background:linear-gradient(180deg,#fff,#eef6ff);">导入存档</button>
        <div class="footer">手机端底部按钮就是多个窗口入口。主界面不需要下滑，就能看到主要状态和操作按钮。</div>
      </section>
    </aside>
  </main>

  <nav class="mobile-tabs">
    <button onclick="switchWindow('status')">📊 状态</button>
    <button onclick="switchWindow('shop')">🛍 商店</button>
    <button onclick="switchWindow('diary')">📖 日记</button>
    <button onclick="switchWindow('settings')">⚙️ 设置</button>
  </nav>

  <div class="toast" id="toast"></div>

  <script>
    const LOCAL_KEY = 'pocketCatSaveV3';
    let currentState = null;
    let pendingLocalBackup = null;
    const statLabels = [
      ['hunger', '🍚 饱腹'],
      ['mood', '🌈 心情'],
      ['clean', '✨ 清洁'],
      ['energy', '🌙 体力'],
      ['affection', '💞 亲密']
    ];
    const fullStatLabels = [
      ['hunger', '🍚 饱腹值'],
      ['mood', '🌈 心情值'],
      ['clean', '✨ 清洁值'],
      ['energy', '🌙 体力值'],
      ['affection', '💞 亲密度']
    ];

    async function loadState() {
      const res = await fetch('/api/state');
      const state = await res.json();
      const local = readLocalBackup();
      if (local && Number(local.progress_score || 0) > Number(state.progress_score || 0) + 10) {
        pendingLocalBackup = local;
      }
      render(state);
    }

    async function doAction(action) {
      showImmediateFeedback(action);
      const res = await fetch('/api/action', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action })
      });
      const state = await res.json();
      render(state, action);
    }

    async function buyItem(item) {
      const res = await fetch('/api/action', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'shop', item })
      });
      render(await res.json(), 'shop');
    }

    async function renameCat() {
      const name = document.getElementById('nameInput').value.trim();
      const res = await fetch('/api/action', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'rename', name })
      });
      document.getElementById('nameInput').value = '';
      render(await res.json(), 'pet');
    }

    async function resetGame() {
      if (!confirm('确定要重新开始吗？当前云端进度会被覆盖，但浏览器本地备份仍可手动导入。')) return;
      const res = await fetch('/api/action', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'reset' })
      });
      pendingLocalBackup = null;
      localStorage.removeItem(LOCAL_KEY);
      render(await res.json(), 'pet');
    }

    function switchWindow(name) {
      const side = document.getElementById('sidePanels');
      const target = document.getElementById(`panel-${name}`);
      if (!target) return;
      const alreadyOpen = side.classList.contains('open') && target.classList.contains('active');
      document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
      target.classList.add('active');
      side.classList.toggle('open', !alreadyOpen);
    }

    function closeWindow() {
      document.getElementById('sidePanels').classList.remove('open');
    }

    function readLocalBackup() {
      try {
        const raw = localStorage.getItem(LOCAL_KEY) || localStorage.getItem('pocketCatSaveV2');
        if (!raw) return null;
        const parsed = JSON.parse(raw);
        return parsed && typeof parsed === 'object' ? parsed : null;
      } catch (e) { return null; }
    }

    function saveLocalBackup(state) {
      try { localStorage.setItem(LOCAL_KEY, JSON.stringify(state)); } catch (e) {}
    }

    async function restoreLocalBackup() {
      if (!pendingLocalBackup) return;
      const res = await fetch('/api/action', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'import', state: pendingLocalBackup })
      });
      pendingLocalBackup = null;
      render(await res.json(), 'pet');
      toast('已恢复本机备份');
    }

    async function importSaveText() {
      const text = document.getElementById('importText').value.trim();
      if (!text) { toast('请先粘贴存档内容'); return; }
      try {
        const parsed = JSON.parse(text);
        const state = parsed.state || parsed;
        const res = await fetch('/api/action', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action: 'import', state })
        });
        document.getElementById('importText').value = '';
        render(await res.json(), 'pet');
        toast('导入完成');
      } catch (e) {
        toast('导入失败，内容不是正确的 JSON 存档');
      }
    }

    async function exportSave() {
      if (!currentState) return;
      const text = JSON.stringify({ exported_at: new Date().toISOString(), state: currentState }, null, 2);
      try {
        await navigator.clipboard.writeText(text);
        toast('存档已复制到剪贴板');
      } catch (e) {
        document.getElementById('importText').value = text;
        toast('浏览器不允许复制，已放到输入框里');
      }
    }

    function getMoodClasses(state) {
      const classes = [];
      if (state.hunger < 35) classes.push('low-hunger');
      if (state.energy < 35) classes.push('low-energy');
      if (state.mood < 35) classes.push('low-mood');
      if (state.clean < 35) classes.push('dirty');
      return classes.join(' ');
    }

    function showImmediateFeedback(action) {
      triggerActionFeedback(action);
      animateCat(action);
    }

    function animateCat(action) {
      const cat = document.getElementById('catModel');
      if (!cat) return;
      ['anim-feed','anim-pet','anim-play','anim-bath','anim-sleep','anim-photo'].forEach(c => cat.classList.remove(c));
      if (!['feed','pet','play','bath','sleep','photo'].includes(action)) return;
      void cat.offsetWidth;
      cat.classList.add(`anim-${action}`);
      setTimeout(() => cat.classList.remove(`anim-${action}`), 1050);
    }

    function triggerActionFeedback(action) {
      const map = {
        feed: ['🐟','🍚','✨','💗'],
        pet: ['💗','💕','✨','ฅ'],
        play: ['🧶','✨','🎀','💫'],
        bath: ['🫧','💧','✨','🛁'],
        sleep: ['💤','🌙','⭐','☁️'],
        photo: ['📸','✨','💗','🌟'],
        shop: ['🎁','✨','💗','🛍️']
      };
      const layer = document.getElementById('feedbackLayer');
      if (!layer) return;
      const symbols = map[action] || ['✨'];
      if (action === 'photo') {
        const room = document.getElementById('room');
        room.classList.remove('flash');
        void room.offsetWidth;
        room.classList.add('flash');
        setTimeout(() => room.classList.remove('flash'), 450);
      }
      for (let i = 0; i < 7; i++) {
        const span = document.createElement('span');
        span.className = 'floaty';
        span.textContent = symbols[Math.floor(Math.random() * symbols.length)];
        span.style.setProperty('--dx', `${Math.round((Math.random() - 0.5) * 190)}px`);
        span.style.setProperty('--dy', `${Math.round(-80 - Math.random() * 95)}px`);
        span.style.setProperty('--rot', `${Math.round((Math.random() - 0.5) * 70)}deg`);
        span.style.left = `${42 + Math.random() * 16}%`;
        span.style.top = `${38 + Math.random() * 28}%`;
        layer.appendChild(span);
        setTimeout(() => span.remove(), 950);
      }
    }

    function render(state, action = null) {
      currentState = state;
      saveLocalBackup(state);
      document.getElementById('coins').textContent = state.coins;
      document.getElementById('level').textContent = state.level;
      document.getElementById('day').textContent = state.day;
      document.getElementById('catName').textContent = state.cat_name;
      document.getElementById('statusText').textContent = state.status_text;
      document.getElementById('message').textContent = `第 ${state.day} 天：${state.last_action}`;
      document.getElementById('window').textContent = state.decor.window;
      document.getElementById('bed').textContent = state.decor.bed;
      document.getElementById('neck').textContent = state.decor.neck || '♕';
      document.getElementById('toy').textContent = state.decor.toy;
      document.getElementById('cameraDec').textContent = state.decor.camera;
      document.getElementById('wallpaper').style.opacity = state.decor.wallpaper ? '.36' : '0';
      document.getElementById('endingBox').style.display = state.ending ? 'block' : 'none';
      document.getElementById('syncBox').style.display = pendingLocalBackup ? 'block' : 'none';

      const cat = document.getElementById('catModel');
      cat.className = `royal-cat ${getMoodClasses(state)}`;
      if (action) {
        setTimeout(() => {
          animateCat(action);
          if (['feed','pet','play','bath','sleep','photo','shop'].includes(action)) triggerActionFeedback(action);
        }, 40);
      }

      const quickStats = document.getElementById('quickStats');
      quickStats.innerHTML = statLabels.map(([key, label]) => `
        <div class="mini-stat">
          <div class="label">${label}</div>
          <div class="num">${state[key]}</div>
          <div class="mini-bar"><div class="mini-fill" style="width:${state[key]}%"></div></div>
        </div>
      `).join('');

      const stats = document.getElementById('stats');
      stats.innerHTML = fullStatLabels.map(([key, label]) => `
        <div>
          <div class="stat-head"><span>${label}</span><span>${state[key]}</span></div>
          <div class="bar"><div class="fill" style="width:${state[key]}%"></div></div>
        </div>
      `).join('') + `
        <div>
          <div class="stat-head"><span>⭐ 经验值</span><span>${state.exp} / ${state.next_level_exp}</span></div>
          <div class="bar"><div class="fill" style="width:${Math.min(100, (state.exp % 55) / 55 * 100)}%"></div></div>
        </div>
      `;

      const shop = document.getElementById('shop');
      shop.innerHTML = state.shop.map(item => {
        const disabled = item.owned && item.unique;
        const btnText = disabled ? '已拥有' : '购买';
        return `
          <div class="shop-item">
            <div class="shop-emoji">${item.emoji}</div>
            <div>
              <div class="shop-name">${item.name}</div>
              <div class="shop-cost">${item.type === 'consumable' ? '消耗品' : '装饰'} · 需要 ${item.cost} 枚爱心币</div>
            </div>
            <button ${disabled ? 'disabled' : ''} onclick="buyItem('${item.id}')">${btnText}</button>
          </div>
        `;
      }).join('');

      const badges = document.getElementById('badges');
      badges.innerHTML = state.badges_public.map(b => `
        <span class="badge ${b.owned ? '' : 'locked'}">${b.owned ? '🏅' : '🔒'} ${b.name}</span>
      `).join('');

      const diary = document.getElementById('diary');
      diary.innerHTML = (state.diary || []).slice().reverse().map(x => `<div>${escapeHtml(x)}</div>`).join('');
    }

    function escapeHtml(str) {
      return String(str).replace(/[&<>\"]/g, s => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;' }[s]));
    }

    let toastTimer = null;
    function toast(text) {
      const el = document.getElementById('toast');
      el.textContent = text;
      el.classList.add('show');
      clearTimeout(toastTimer);
      toastTimer = setTimeout(() => el.classList.remove('show'), 1800);
    }

    if ('serviceWorker' in navigator) {
      window.addEventListener('load', () => {
        navigator.serviceWorker.register('/service-worker.js').catch(() => {});
      });
    }

    loadState();
  </script>
</body>
</html>
'''

MANIFEST = {
    "name": "喵喵治愈屋",
    "short_name": "喵喵治愈屋",
    "start_url": "/",
    "display": "standalone",
    "background_color": "#fff7fb",
    "theme_color": "#ffd7e8",
    "icons": [
        {
            "src": "/icon.svg",
            "sizes": "128x128",
            "type": "image/svg+xml",
            "purpose": "any maskable",
        }
    ],
}

ICON_SVG = r'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">
  <defs>
    <linearGradient id="bg" x1="0" x2="1" y1="0" y2="1"><stop stop-color="#fff7fb"/><stop offset="1" stop-color="#dff4ff"/></linearGradient>
  </defs>
  <rect width="128" height="128" rx="30" fill="url(#bg)"/>
  <path d="M34 84c2-22 16-36 34-36s32 14 34 36c1 12-11 23-34 23S33 96 34 84Z" fill="#fff" stroke="#d8dde6" stroke-width="3"/>
  <path d="M44 51 55 28l9 22M84 50l9-22 11 24" fill="#fff" stroke="#d8dde6" stroke-width="3" stroke-linejoin="round"/>
  <circle cx="54" cy="68" r="5" fill="#2f5666"/><circle cx="82" cy="68" r="5" fill="#2f5666"/>
  <path d="M66 77q2 3 4 0" stroke="#e998b2" stroke-width="4" stroke-linecap="round"/>
  <text x="64" y="37" font-size="25" text-anchor="middle" fill="#f2c94c">♛</text>
</svg>'''

SERVICE_WORKER = r'''
const CACHE_NAME = 'pocket-cat-v3';
const CORE = ['/', '/manifest.webmanifest'];
self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE_NAME).then(cache => cache.addAll(CORE)));
  self.skipWaiting();
});
self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))));
  self.clients.claim();
});
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  if (url.pathname.startsWith('/api/')) return;
  event.respondWith(fetch(event.request).then(res => {
    const copy = res.clone();
    caches.open(CACHE_NAME).then(cache => cache.put(event.request, copy));
    return res;
  }).catch(() => caches.match(event.request).then(res => res || caches.match('/'))));
});
'''

app = Flask(__name__)


def get_request_player() -> Tuple[str, bool]:
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
            secure=request.is_secure,
            httponly=False,
        )
    return response


@app.get("/")
def index():
    player_id, is_new = get_request_player()
    # Ensure save exists after opening home page.
    get_state(player_id)
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


@app.get("/manifest.webmanifest")
def manifest():
    response = jsonify(MANIFEST)
    response.headers["Content-Type"] = "application/manifest+json; charset=utf-8"
    return response


@app.get("/icon.svg")
def icon_svg():
    response = make_response(ICON_SVG)
    response.headers["Content-Type"] = "image/svg+xml; charset=utf-8"
    response.headers["Cache-Control"] = "public, max-age=86400"
    return response


@app.get("/service-worker.js")
def service_worker():
    response = make_response(SERVICE_WORKER)
    response.headers["Content-Type"] = "application/javascript; charset=utf-8"
    response.headers["Cache-Control"] = "no-cache"
    return response


if __name__ == "__main__":
    local_ip = get_local_ip()
    print("\n====== 喵喵治愈屋优化版启动成功 ======")
    print(f"本机浏览器打开： http://127.0.0.1:{PORT}")
    print(f"同一 WiFi 下手机/其他电脑打开： http://{local_ip}:{PORT}")
    print("云部署时，平台会自动提供公网网址。")
    print("====================================\n")
    app.run(host=HOST, port=PORT, debug=False)
