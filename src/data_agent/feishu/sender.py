from __future__ import annotations

import io
import json
import time
from typing import Any

import httpx

from data_agent.config import get_settings


FEISHU_API_BASE = "https://open.feishu.cn/open-apis"
_token_cache: dict[str, Any] = {"token": None, "expires_at": 0.0}
_bot_info_cache: dict[str, Any] = {"open_id": None, "expires_at": 0.0}


def get_tenant_token() -> str:
    settings = get_settings()
    if not settings.feishu_app_id or not settings.feishu_app_secret:
        raise RuntimeError("飞书 App ID / App Secret 未配置")

    if _token_cache["token"] and time.time() < _token_cache["expires_at"]:
        return str(_token_cache["token"])

    with httpx.Client(timeout=15) as client:
        resp = client.post(
            f"{FEISHU_API_BASE}/auth/v3/tenant_access_token/internal",
            json={
                "app_id": settings.feishu_app_id,
                "app_secret": settings.feishu_app_secret,
            },
        )
        data = resp.json()

    if data.get("code") != 0:
        raise RuntimeError(f"获取飞书 tenant_access_token 失败：{data}")

    _token_cache["token"] = data["tenant_access_token"]
    _token_cache["expires_at"] = time.time() + int(data.get("expire", 7200)) - 60
    return str(_token_cache["token"])


def get_bot_open_id() -> str:
    if _bot_info_cache["open_id"] and time.time() < _bot_info_cache["expires_at"]:
        return str(_bot_info_cache["open_id"])

    token = get_tenant_token()
    with httpx.Client(timeout=15) as client:
        resp = client.get(
            f"{FEISHU_API_BASE}/bot/v3/info",
            headers={"Authorization": f"Bearer {token}"},
        )
        data = resp.json()

    if data.get("code") != 0:
        raise RuntimeError(f"获取飞书机器人信息失败：{data}")

    open_id = data.get("bot", {}).get("open_id", "")
    if not open_id:
        raise RuntimeError(f"飞书机器人信息缺少 open_id：{data}")

    _bot_info_cache["open_id"] = open_id
    _bot_info_cache["expires_at"] = time.time() + 3600
    return str(open_id)


def upload_image(image_bytes: bytes) -> str | None:
    token = get_tenant_token()
    with httpx.Client(timeout=30) as client:
        resp = client.post(
            f"{FEISHU_API_BASE}/im/v1/images",
            headers={"Authorization": f"Bearer {token}"},
            data={"image_type": "message"},
            files={"image": ("chart.png", io.BytesIO(image_bytes), "image/png")},
        )
        data = resp.json()

    if data.get("code") == 0:
        return data["data"]["image_key"]
    print(f"[feishu] upload image failed: {data}")
    return None


def send_card_message(
    receive_id: str,
    receive_id_type: str,
    card_content: dict,
) -> str | None:
    token = get_tenant_token()
    payload = {
        "receive_id": receive_id,
        "msg_type": "interactive",
        "content": json.dumps(card_content, ensure_ascii=False),
    }
    with httpx.Client(timeout=20) as client:
        resp = client.post(
            f"{FEISHU_API_BASE}/im/v1/messages",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            params={"receive_id_type": receive_id_type},
            json=payload,
        )
        data = resp.json()

    if data.get("code") == 0:
        return data["data"]["message_id"]
    print(f"[feishu] send message failed: {data}")
    return None


def reply_to_message(message_id: str, card_content: dict, reply_in_thread: bool = True) -> str | None:
    token = get_tenant_token()
    with httpx.Client(timeout=20) as client:
        resp = client.post(
            f"{FEISHU_API_BASE}/im/v1/messages/{message_id}/reply",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={
                "msg_type": "interactive",
                "content": json.dumps(card_content, ensure_ascii=False),
                "reply_in_thread": reply_in_thread,
            },
        )
        data = resp.json()

    if data.get("code") == 0:
        return data["data"]["message_id"]
    print(f"[feishu] reply message failed: {data}")
    return None
