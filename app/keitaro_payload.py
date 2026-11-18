"""Сборка тел запросов Keitaro и разбор справочников фильтров."""

from __future__ import annotations

import re
import secrets

GOOGLE_URL = "https://google.com"


def normalize_base_url(value: str) -> str:
    url = value.strip().rstrip("/")
    suffix = "/admin_api/v1"
    if url.endswith(suffix):
        url = url[: -len(suffix)]
    return url


def parse_countries(value: str) -> list[str]:
    parts = re.split(r"[\s,;]+", value.strip().upper())
    codes = [part for part in parts if part]
    if not codes:
        raise ValueError("Укажите гео-код страны, например AU или MX,RO")
    invalid = [code for code in codes if not re.fullmatch(r"[A-Z]{2}", code)]
    if invalid:
        raise ValueError(
            "Гео-код — это две латинские буквы. Не распознано: " + ", ".join(invalid)
        )
    unique: list[str] = []
    for code in codes:
        if code not in unique:
            unique.append(code)
    return unique


def make_alias(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:24]
    suffix = secrets.token_hex(2)
    return f"{slug}-{suffix}" if slug else suffix


def pick_country_filter(filters: list) -> str:
    for item in filters:
        if not isinstance(item, dict):
            continue
        value = str(item.get("value") or item.get("key") or item.get("name") or "").strip()
        if value.lower() in {"country", "geo"}:
            return value
    return "country"


def pick_redirect_action(actions: list) -> str:
    keys: list[str] = []
    for item in actions:
        if isinstance(item, dict):
            key = str(item.get("key") or item.get("name") or "").strip()
        else:
            key = str(item).strip()
        if key:
            keys.append(key)
    for preferred in ("http", "redirect"):
        for key in keys:
            if key.lower() == preferred:
                return key
    return "http"


def campaign_body(
    *,
    name: str,
    alias: str,
    domain_id: int,
    group_id: int,
    source_id: int,
) -> dict:
    return {
        "name": name,
        "alias": alias,
        "type": "position",
        "state": "active",
        "cost_type": "CPC",
        "cost_value": 0,
        "cost_currency": "USD",
        "cost_auto": True,
        "domain_id": domain_id,
        "group_id": group_id,
        "traffic_source_id": source_id,
        "cookies_ttl": 24,
    }


def geo_stream_body(
    *,
    campaign_id: int,
    countries: list[str],
    filter_name: str,
    action_type: str,
) -> dict:
    return {
        "campaign_id": campaign_id,
        "type": "regular",
        "name": "Geo " + ",".join(countries),
        "schema": "redirect",
        "action_type": action_type,
        "action_payload": GOOGLE_URL,
        "position": 1,
        "state": "active",
        "collect_clicks": True,
        "filter_or": False,
        "filters": [
            {"name": filter_name, "mode": "accept", "payload": countries},
        ],
        "triggers": [],
        "landings": [],
        "offers": [],
    }


def offer_stream_body(*, campaign_id: int, offer_id: int, action_type: str) -> dict:
    return {
        "campaign_id": campaign_id,
        "type": "default",
        "name": "Offers",
        "schema": "landings",
        "action_type": action_type,
        "position": 2,
        "state": "active",
        "collect_clicks": True,
        "filter_or": False,
        "filters": [],
        "triggers": [],
        "landings": [],
        "offers": [{"offer_id": offer_id, "share": 100, "state": "active"}],
    }


def prefer_item(items: list[dict], saved_id: int | None) -> dict | None:
    if saved_id is not None:
        for item in items:
            if int(item.get("id") or 0) == int(saved_id):
                return item
    for item in items:
        if str(item.get("name") or "").upper() == "FORTESTS":
            return item
    return items[0] if items else None
