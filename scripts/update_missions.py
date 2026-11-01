#!/usr/bin/env python3
"""Fetch Fortnite Save the World V-Bucks missions and maintain daily history."""

from __future__ import annotations

import json
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "public" / "data"
MISSIONS_FILE = DATA / "missions.json"
HISTORY_FILE = DATA / "history.json"

PENNYDB_API = "https://pennydb.net/api"

FALLBACK_SOURCES = [
    ("HawkBucks", "https://hawkbucks.com/vbucks-missions"),
    ("V-Bucks Daily", "https://vbucksdaily.com/"),
    ("SaveTheWorldDB", "https://savetheworlddb.com/"),
    ("FortniteDB", "https://v2.fortnitedb.com/"),
]

ZONE_ALIASES = {
    "stonewood": "Stonewood",
    "plankerton": "Plankerton",
    "canny valley": "Canny Valley",
    "twine peaks": "Twine Peaks",
    "ventures": "Ventures",
}

MISSION_NAMES = (
    "Fight Category 4 Storm",
    "Fight Category 3 Storm",
    "Fight Category 2 Storm",
    "Fight Category 1 Storm",
    "Fight the Storm",
    "Deliver the Bomb",
    "Ride the Lightning",
    "Retrieve the Data",
    "Repair the Shelter",
    "Evacuate the Shelter",
    "Rescue the Survivors",
    "Build the Radar Grid",
    "Build the Radar",
    "Destroy the Encampments",
    "Eliminate and Collect",
    "Resupply",
)

REWARD_RE = re.compile(
    r"V[- ]?Bucks\s*(?:(?:x|×)\s*)?(\d{1,4})\b"
    r"|\b(?:x|×)\s*(\d{1,4})\s*V[- ]?Bucks"
    r"|\b(\d{1,4})\s*V[- ]?Bucks",
    re.I,
)

EXPLICIT_POWER_RE = re.compile(
    r"\bPL\s*[:#-]?\s*(\d{1,3})\b"
    r"|\bPower\s*Level\s*[:#-]?\s*(\d{1,3})\b"
    r"|\b(\d{1,3})\s*PL\b"
    r"|\b(\d{1,3})\s*Power\b",
    re.I,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        match = re.fullmatch(r"\s*(?:PL\s*)?(\d{1,3})\s*", value, re.I)
        if match:
            return int(match.group(1))
    return None


def _valid_power_level(value: Any) -> int | None:
    parsed = _as_int(value)
    return parsed if parsed is not None and 1 <= parsed <= 160 else None


def _zone_name(raw_zone: Any) -> str | None:
    value = str(raw_zone or "").replace("_", " ").strip().casefold()
    return ZONE_ALIASES.get(value)


def _mission_name(raw: Any) -> str:
    if isinstance(raw, dict):
        for key in ("name", "displayName", "type"):
            value = raw.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""
    return raw.strip() if isinstance(raw, str) else ""


def _mission_location(raw_mission: dict[str, Any]) -> str:
    """Extract a location only when it is explicitly present in source data."""

    location_keys = (
        "location",
        "locationName",
        "missionLocation",
        "missionLocationName",
        "tile",
        "tileName",
        "tileLocation",
        "tileLocationName",
        "subzone",
        "subzoneName",
        "areaName",
        "mapName",
    )

    ignored = {
        "stonewood",
        "plankerton",
        "canny valley",
        "twine peaks",
        "ventures",
    }

    def search(data: Any, depth: int = 0) -> str:
        if depth > 5 or not isinstance(data, dict):
            return ""

        for key in location_keys:
            value = data.get(key)

            if isinstance(value, str):
                value = value.strip()
                if value and value.casefold() not in ignored:
                    return value

            elif isinstance(value, dict):
                for display_key in ("displayName", "name", "label", "title", "value"):
                    display_value = value.get(display_key)
                    if isinstance(display_value, str):
                        display_value = display_value.strip()
                        if display_value and display_value.casefold() not in ignored:
                            return display_value

        for value in data.values():
            if isinstance(value, dict):
                result = search(value, depth + 1)
                if result:
                    return result

        return ""

    return search(raw_mission)


def _is_vbucks_reward(reward: Any) -> bool:
    if not isinstance(reward, dict):
        return False

    item_type = str(
        reward.get("itemType") or reward.get("templateId") or ""
    ).casefold()

    name = re.sub(
        r"[\s_-]+", "", str(reward.get("name") or "").casefold()
    )

    return (
        "currency_mtxswap" in item_type
        or "mtxswap" in item_type
        or "vbucks" in name
        or "vbuck" in name
    )


def _mission_vbucks_amount(mission: dict[str, Any]) -> int | None:
    for key in ("alertRewards", "rewards"):
        entries = mission.get(key)

        if not isinstance(entries, list):
            continue

        for reward in entries:
            if not _is_vbucks_reward(reward):
                continue

            quantity = _as_int(reward.get("quantity"))

            if quantity is not None and 0 < quantity <= 5000:
                return quantity

    return None


def _deduplicate(
    missions: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    result: dict[tuple[str, str, int], dict[str, Any]] = {}

    for mission in missions:
        key = (
            str(mission.get("mission", "")).casefold(),
            str(mission.get("zone", "")).casefold(),
            int(mission.get("vbucks", 0)),
        )

        if key not in result:
            result[key] = dict(mission)
            result[key]["sources"] = list(
                mission.get("sources")
                or [mission.get("source", "Unknown")]
            )
            continue

        existing = result[key]

        if (
            existing.get("powerLevel") is None
            and mission.get("powerLevel") is not None
        ):
            existing["powerLevel"] = mission["powerLevel"]

        if not existing.get("location") and mission.get("location"):
            existing["location"] = mission["location"]

        for source in mission.get("sources") or [
            mission.get("source", "Unknown")
        ]:
            if source and source not in existing["sources"]:
                existing["sources"].append(source)

    return list(result.values())


def parse_pennydb_payload(payload: Any) -> list[dict[str, Any]]:
    """Parse PennyDB's structured mission response."""

    if not isinstance(payload, dict) or not isinstance(
        payload.get("missions"), dict
    ):
        raise ValueError("PennyDB response is missing the missions object")

    raw_zones = payload["missions"]
    recognized_zone_arrays = 0
    parsed: list[dict[str, Any]] = []

    for raw_zone, entries in raw_zones.items():
        zone = _zone_name(raw_zone)

        if zone is None:
            continue

        if not isinstance(entries, list):
            raise ValueError(
                f"PennyDB zone {raw_zone!r} is not a list"
            )

        recognized_zone_arrays += 1

        for raw_mission in entries:
            if not isinstance(raw_mission, dict):
                continue

            quantity = _mission_vbucks_amount(raw_mission)

            if quantity is None:
                continue

            mission_name = _mission_name(
                raw_mission.get("missionType")
            )

            if not mission_name:
                continue

            item: dict[str, Any] = {
                "mission": mission_name,
                "zone": zone,
                "location": _mission_location(raw_mission),
                "vbucks": quantity,
                "source": "PennyDB",
                "sources": ["PennyDB"],
            }

            power_level = _valid_power_level(
                raw_mission.get("pl")
            )

            if power_level is not None:
                item["powerLevel"] = power_level

            parsed.append(item)

    if recognized_zone_arrays == 0:
        raise ValueError(
            "PennyDB response did not contain recognized Save the World zones"
        )

    return _deduplicate(parsed)


def fetch_json(url: str) -> Any:
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 "
                "(compatible; JadBakerX-STW-Mission-Tracker/4.0)"
            ),
            "Accept": "application/json",
        },
    )

    with urlopen(request, timeout=25) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status}")
        raw = response.read(20_000_000)

    try:
        return json.loads(raw.decode("utf-8", "replace"))
    except json.JSONDecodeError as exc:
        raise ValueError("PennyDB returned invalid JSON") from exc


class TextExtractor(HTMLParser):
    BLOCKS = {
        "p", "div", "section", "article", "tr", "li",
        "h1", "h2", "h3", "h4", "br", "td", "th",
        "main", "header", "footer",
    }

    SKIP_TAGS = {"script", "style", "noscript", "svg"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)

        if tag in self.SKIP_TAGS:
            self.skip_depth += 1
            return

        for key in (
            "alt", "aria-label", "title",
            "data-power-level", "data-powerlevel",
            "data-pl", "data-power",
        ):
            value = attrs.get(key)
            if value:
                self.parts.append("\n" + str(value) + "\n")

        if not self.skip_depth and tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP_TAGS and self.skip_depth:
            self.skip_depth -= 1
        elif not self.skip_depth and tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip_depth:
            self.parts.append(data)


def fetch_text(url: str) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 "
                "(compatible; JadBakerX-STW-Mission-Tracker/4.0)"
            ),
            "Accept": "text/html,application/xhtml+xml",
        },
    )

    with urlopen(request, timeout=25) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status}")
        raw = response.read(8_000_000)

    parser = TextExtractor()
    parser.feed(raw.decode("utf-8", "replace"))

    text = "\n".join(parser.parts)
    text = re.sub(r"[ \t\xa0]+", " ", text)

    return re.sub(r"\n\s*\n+", "\n", text)


def find_summary(text: str) -> dict[str, int]:
    labels = [
        ("today", r"(?:Today|Today’s|Today\s+V-Bucks|V-Bucks Today)"),
        ("yesterday", r"Yesterday"),
        ("last7Days", r"(?:This Week|Last 7 Days)"),
        ("last30Days", r"(?:This Month|Last 30 Days)"),
        ("thisYear", r"This Year"),
    ]

    result: dict[str, int] = {}

    for key, label in labels:
        for match in re.finditer(label, text, re.I):
            amount = re.search(
                r"(?<![\w])([\d,]+)\s*(?:V-Bucks)?",
                text[match.end():match.end() + 180],
                re.I,
            )

            if amount:
                value = int(amount.group(1).replace(",", ""))

                if value <= 1_000_000:
                    result[key] = value
                    break

    return result
