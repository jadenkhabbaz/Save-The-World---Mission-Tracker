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
