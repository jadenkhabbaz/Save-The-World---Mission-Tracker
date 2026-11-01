#!/usr/bin/env python3
"""Fetch Fortnite Save the World V-Bucks missions and keep a daily archive.

Primary source: PennyDB's public structured JSON API (https://pennydb.net/api).
PennyDB exposes each mission's `pl`, `missionType`, and `alertRewards` fields.
Fallback sources: public HTML mission trackers, used only if PennyDB is down or
its response schema is not usable.

Power Levels are never inferred from mission names, zones, rewards, or dates.
A PL is written only when it comes from PennyDB's `pl` field or an explicitly
labelled Power Level in a fallback source.
"""

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
    ("HawkBucks", "https://hawkbucks.com/"),
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


def _is_vbucks_reward(reward: Any) -> bool:
    if not isinstance(reward, dict):
        return False
    item_type = str(reward.get("itemType") or reward.get("templateId") or "").casefold()
    name = re.sub(r"[\s_-]+", "", str(reward.get("name") or "").casefold())
    return (
        "currency_mtxswap" in item_type
        or "mtxswap" in item_type
        or "vbucks" in name
        or "vbuck" in name
    )


def _mission_vbucks_amount(mission: dict[str, Any]) -> int | None:
    # PennyDB models V-Bucks mission rewards in alertRewards. `rewards` is
    # accepted as a fallback for compatible response variants.
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


def parse_pennydb_payload(payload: Any) -> list[dict[str, Any]]:
    """Convert PennyDB `/api` response into this tracker's mission schema.

    Expected public shape: {"missions": {"canny_valley": [
      {"pl": "70", "missionType": {"name": "..."},
       "alertRewards": [{"itemType": "...currency_mtxswap", "quantity": 50}]}
    ]}}
    """
    if not isinstance(payload, dict) or not isinstance(payload.get("missions"), dict):
        raise ValueError("PennyDB response is missing the missions object")

    raw_zones = payload["missions"]
    recognized_zone_arrays = 0
    parsed: list[dict[str, Any]] = []

    for raw_zone, entries in raw_zones.items():
        zone = _zone_name(raw_zone)
        if zone is None:
            continue
        if not isinstance(entries, list):
            raise ValueError(f"PennyDB zone {raw_zone!r} is not a list")
        recognized_zone_arrays += 1

        for raw_mission in entries:
            if not isinstance(raw_mission, dict):
                continue
            quantity = _mission_vbucks_amount(raw_mission)
            if quantity is None:
                continue

            mission_name = _mission_name(raw_mission.get("missionType"))
            if not mission_name:
                # Do not generate a misleading mission card with an unknown name.
                continue

            item: dict[str, Any] = {
                "mission": mission_name,
                "zone": zone,
                "location": str(raw_mission.get("location") or raw_mission.get("zoneName") or ""),
                "vbucks": quantity,
                "source": "PennyDB",
                "sources": ["PennyDB"],
            }

            # `pl` is PennyDB's explicit mission Power Level field. No guessing.
            power_level = _valid_power_level(raw_mission.get("pl"))
            if power_level is not None:
                item["powerLevel"] = power_level

            parsed.append(item)

    if recognized_zone_arrays == 0:
        raise ValueError("PennyDB response did not contain recognized Save the World zones")

    return _deduplicate(parsed)


def _deduplicate(missions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: dict[tuple[str, str, int], dict[str, Any]] = {}
    for mission in missions:
        key = (
            str(mission.get("mission", "")).casefold(),
            str(mission.get("zone", "")).casefold(),
            int(mission.get("vbucks", 0)),
        )
        if key not in result:
            result[key] = dict(mission)
            result[key]["sources"] = list(mission.get("sources") or [mission.get("source", "Unknown")])
            continue

        existing = result[key]
        if existing.get("powerLevel") is None and mission.get("powerLevel") is not None:
            existing["powerLevel"] = mission["powerLevel"]
        if not existing.get("location") and mission.get("location"):
            existing["location"] = mission["location"]
        for source in mission.get("sources") or [mission.get("source", "Unknown")]:
            if source and source not in existing["sources"]:
                existing["sources"].append(source)

    return list(result.values())


def fetch_json(url: str) -> Any:
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; JadBakerX-STW-Mission-Tracker/4.0)",
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
        "p", "div", "section", "article", "tr", "li", "h1", "h2",
        "h3", "h4", "br", "td", "th", "main", "header", "footer",
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
        for key in ("alt", "aria-label", "title", "data-power-level", "data-powerlevel", "data-pl", "data-power"):
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
            "User-Agent": "Mozilla/5.0 (compatible; JadBakerX-STW-Mission-Tracker/4.0)",
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
            amount = re.search(r"(?<![\w])([\d,]+)\s*(?:V-Bucks)?", text[match.end():match.end() + 180], re.I)
            if amount:
                value = int(amount.group(1).replace(",", ""))
                if value <= 1_000_000:
                    result[key] = value
                    break
    return result


def extract_html_missions(text: str, source: str) -> list[dict[str, Any]]:
    """Conservative fallback parser for sources that server-render card text."""
    lines = [re.sub(r"\s+", " ", x).strip(" -|•·") for x in text.splitlines()]
    lines = [x for x in lines if x]
    reward_rows: list[tuple[int, int]] = []
    for index, line in enumerate(lines):
        match = REWARD_RE.search(line)
        if match:
            raw = next((group for group in match.groups() if group is not None), None)
            if raw:
                amount = int(raw)
                if 0 < amount <= 5000:
                    reward_rows.append((index, amount))

    parsed: list[dict[str, Any]] = []
    for row_number, (reward_index, reward) in enumerate(reward_rows):
        previous = reward_rows[row_number - 1][0] if row_number else -1
        next_index = reward_rows[row_number + 1][0] if row_number + 1 < len(reward_rows) else len(lines)
        start = max(previous + 1, reward_index - 40, 0)
        end = min(next_index, reward_index + 4, len(lines))
        card_lines = lines[start:end]
        mission_candidates = []
        for idx, line in enumerate(card_lines, start):
            for name in MISSION_NAMES:
                if re.search(re.escape(name), line, re.I):
                    mission_candidates.append((abs(idx - reward_index), -len(name), idx, name))
        if not mission_candidates:
            continue
        _, _, mission_index, mission = min(mission_candidates)

        zone_candidates = []
        for idx, line in enumerate(card_lines, start):
            for raw_zone, zone in ZONE_ALIASES.items():
                if re.search(re.escape(raw_zone), line.replace("_", " "), re.I):
                    zone_candidates.append((abs(idx - mission_index), idx, zone))
        if not zone_candidates:
            continue
        _, zone_index, zone = min(zone_candidates)

        power_level = None
        for line in card_lines:
            match = EXPLICIT_POWER_RE.search(line)
            if match:
                candidate = next((group for group in match.groups() if group is not None), None)
                power_level = _valid_power_level(candidate)
                if power_level is not None:
                    break

        location = ""
        for line in lines[mission_index + 1:min(end, mission_index + 5)]:
            if len(line) < 80 and not re.search(r"V[- ]?Bucks|Power|Founders|reward|mission|Category", line, re.I):
                location = line
                break

        item: dict[str, Any] = {
            "mission": mission,
            "zone": zone,
            "location": location,
            "vbucks": reward,
            "source": source,
            "sources": [source],
        }
        if power_level is not None:
            item["powerLevel"] = power_level
        parsed.append(item)
    return _deduplicate(parsed)


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _clean_power_levels(value: Any) -> Any:
    if isinstance(value, dict):
        if "powerLevel" in value:
            pl = _valid_power_level(value.get("powerLevel"))
            if pl is None:
                value.pop("powerLevel", None)
            else:
                value["powerLevel"] = pl
        for child in value.values():
            _clean_power_levels(child)
    elif isinstance(value, list):
        for child in value:
            _clean_power_levels(child)
    return value


def _find_day(history_days: list[dict[str, Any]], day: str) -> dict[str, Any] | None:
    return next((entry for entry in history_days if entry.get("date") == day), None)


def _recover_today(old: dict[str, Any], history_days: list[dict[str, Any]], today: str) -> list[dict[str, Any]]:
    """Recover a previously confirmed same-day snapshot if a source fails."""
    saved_day = _find_day(history_days, today)
    if saved_day and saved_day.get("confirmed") and isinstance(saved_day.get("missions"), list):
        return saved_day["missions"]
    if old.get("confirmed") and isinstance(old.get("today"), list) and old["today"]:
        return old["today"]
    return []


def _yesterday_missions(old: dict[str, Any], history_days: list[dict[str, Any]], today: str) -> list[dict[str, Any]]:
    yesterday_date = (date.fromisoformat(today) - timedelta(days=1)).isoformat()
    saved = _find_day(history_days, yesterday_date)
    if saved and isinstance(saved.get("missions"), list):
        return saved["missions"]
    value = old.get("yesterday", [])
    return value if isinstance(value, list) else []


def main() -> None:
    now_dt = utc_now()
    now = iso_z(now_dt)
    today = now_dt.date().isoformat()

    old = _clean_power_levels(load_json(MISSIONS_FILE, {"today": [], "confirmed": False, "sources": []}))
    history = _clean_power_levels(load_json(HISTORY_FILE, {"days": []}))
    history_days = history.get("days", []) if isinstance(history, dict) else []
    if not isinstance(history_days, list):
        history_days = []

    source_results: list[dict[str, Any]] = []
    selected_missions: list[dict[str, Any]] = []
    authoritative_feed = False

    # Primary: PennyDB structured JSON. A valid missions object is authoritative
    # even when it contains no V-Bucks alerts for the day (a genuine zero).
    penny_entry: dict[str, Any] = {
        "name": "PennyDB",
        "url": PENNYDB_API,
        "ok": False,
        "summary": {},
        "missionCount": 0,
        "powerLevelCount": 0,
        "checkedAt": now,
    }
    try:
        payload = fetch_json(PENNYDB_API)
        penny_missions = parse_pennydb_payload(payload)
        authoritative_feed = True
        selected_missions = penny_missions
        penny_entry.update({
            "ok": True,
            "missionCount": len(penny_missions),
            "powerLevelCount": sum(item.get("powerLevel") is not None for item in penny_missions),
            "status": "Fetched structured mission JSON",
        })
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, RuntimeError) as error:
        penny_entry["status"] = "Structured API unavailable: " + str(error)[:180]
    source_results.append(penny_entry)

    # Fallback: only scrape HTML trackers if PennyDB did not provide a valid
    # structured mission payload. This prevents stale HTML data overriding a
    # valid (including legitimately empty) PennyDB rotation.
    if not authoritative_feed:
        fallback_missions: list[dict[str, Any]] = []
        for name, url in FALLBACK_SOURCES:
            entry = {
                "name": name,
                "url": url,
                "ok": False,
                "summary": {},
                "missionCount": 0,
                "powerLevelCount": 0,
                "checkedAt": now,
            }
            try:
                page = fetch_text(url)
                missions = extract_html_missions(page, name)
                entry.update({
                    "ok": True,
                    "summary": find_summary(page),
                    "missionCount": len(missions),
                    "powerLevelCount": sum(item.get("powerLevel") is not None for item in missions),
                    "status": "Fetched public HTML page",
                })
                fallback_missions.extend(missions)
            except (HTTPError, URLError, TimeoutError, OSError, ValueError, RuntimeError) as error:
                entry["status"] = "Fetch failed: " + str(error)[:180]
            source_results.append(entry)
            time.sleep(0.25)
        selected_missions = _deduplicate(fallback_missions)

    # A valid PennyDB response is authoritative, including an empty daily set.
    # If all live sources fail, recover today's last confirmed archive instead
    # of publishing a misleading empty board.
    source_reachable = any(source.get("ok") for source in source_results)
    if authoritative_feed:
        today_missions = selected_missions
        confirmed = True
        status = "confirmed"
    elif selected_missions:
        today_missions = selected_missions
        confirmed = True
        status = "confirmed"
    else:
        today_missions = _recover_today(old, history_days, today)
        confirmed = False
        status = "partial" if source_reachable else "unavailable"

    # Always maintain consistent source attribution, even for merged fallback rows.
    today_missions = _deduplicate(today_missions)

    archive_record = {
        "date": today,
        "checkedAt": now,
        "confirmed": confirmed,
        "missions": today_missions,
        "sourceSummaries": [
            {
                "name": source["name"],
                "url": source["url"],
                "ok": source["ok"],
                "summary": source.get("summary", {}),
                "missionCount": source.get("missionCount", 0),
                "powerLevelCount": source.get("powerLevelCount", 0),
                "status": source.get("status", "No status"),
            }
            for source in source_results
        ],
    }

    existing_index = next((i for i, item in enumerate(history_days) if item.get("date") == today), None)
    if existing_index is None:
        history_days.append(archive_record)
    else:
        prior = history_days[existing_index]
        # A failed/partial fetch must not erase a previously confirmed same-day snapshot.
        if confirmed or not prior.get("confirmed"):
            history_days[existing_index] = archive_record
        else:
            prior["checkedAt"] = now
            prior["sourceSummaries"] = archive_record["sourceSummaries"]

    history_days = sorted(history_days, key=lambda item: item.get("date", ""))[-400:]
    history_output = {"updatedAt": now, "days": history_days}

    output = {
        "updatedAt": now,
        "confirmed": confirmed,
        "status": status,
        "today": today_missions,
        "yesterday": _yesterday_missions(old, history_days, today),
        "sources": source_results,
        "historyDays": len(history_days),
        "historyAvailable": bool(history_days),
    }

    DATA.mkdir(parents=True, exist_ok=True)
    MISSIONS_FILE.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    HISTORY_FILE.write_text(json.dumps(history_output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    power_count = sum(item.get("powerLevel") is not None for item in today_missions)
    print(
        f"Checked {len(source_results)} source(s); "
        f"{sum(bool(source.get('ok')) for source in source_results)} reachable; "
        f"{len(today_missions)} mission rows; "
        f"{power_count} rows with source-provided Power Levels; "
        f"source={'PennyDB structured API' if authoritative_feed else 'HTML fallback / archive'}; "
        f"{len(history_days)} archived days."
    )

    if not source_reachable:
        sys.exit("All live mission sources failed; preserved any last confirmed data without inventing missions or Power Levels.")


if __name__ == "__main__":
    main()
