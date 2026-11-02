#!/usr/bin/env python3
"""Automatic Save the World V-Bucks mission updater."""

import json
import re
import sys
from datetime import datetime, timezone, date, timedelta
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "public" / "data"
MISSIONS_FILE = DATA / "missions.json"
HISTORY_FILE = DATA / "history.json"

PENNYDB_API = "https://pennydb.net/api"
HAWKBUCKS_URL = "https://hawkbucks.com/en"

ZONES = {
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
    r"V[- ]?Bucks\s*(?:(?:x|×)\s*)?(\d{1,4})"
    r"|\b(?:x|×)\s*(\d{1,4})\s*V[- ]?Bucks"
    r"|\b(\d{1,4})\s*V[- ]?Bucks",
    re.I,
)

POWER_RE = re.compile(
    r"\bPL\s*[:#-]?\s*(\d{1,3})\b"
    r"|\bPower\s*Level\s*[:#-]?\s*(\d{1,3})\b"
    r"|\b(\d{1,3})\s*PL\b"
    r"|\b(\d{1,3})\s*Power\b",
    re.I,
)

LOCATION_LABEL_RE = re.compile(
    r"^(?:location|city|area|tile|subzone|mission location)"
    r"\s*[:\-]\s*(.+)$",
    re.I,
)


def now_utc():
    return datetime.now(timezone.utc).replace(microsecond=0)


def timestamp():
    return now_utc().isoformat().replace("+00:00", "Z")


def get_json(url):
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 JadBakerX-STW-Tracker",
            "Accept": "application/json",
        },
    )
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8", "replace"))


def get_html(url):
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 JadBakerX-STW-Tracker",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", "replace")


class PageParser(HTMLParser):
    """Extract visible text and useful location attributes."""

    BLOCKS = {
        "div", "section", "article", "p", "li", "tr",
        "td", "th", "h1", "h2", "h3", "h4", "br",
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.skip_depth = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)

        if tag in ("script", "style", "noscript", "svg"):
            self.skip_depth += 1
            return

        if self.skip_depth:
            return

        for key in (
            "alt", "aria-label", "title",
            "data-location", "data-city",
            "data-tile", "data-subzone",
            "data-power-level", "data-powerlevel",
            "data-pl", "data-power",
        ):
            value = attrs.get(key)
            if value:
                self.parts.append("\n" + value + "\n")

        if tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg"):
            if self.skip_depth:
                self.skip_depth -= 1
            return

        if not self.skip_depth and tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip_depth:
            self.parts.append(data)


def html_to_lines(html):
    parser = PageParser()
    parser.feed(html)

    text = "\n".join(parser.parts)
    text = re.sub(r"[ \t\xa0]+", " ", text)

    return [
        re.sub(r"\s+", " ", line).strip(" -|•·")
        for line in text.splitlines()
        if line.strip()
    ]


def zone_name(value):
    value = str(value or "").replace("_", " ").strip().casefold()
    return ZONES.get(value)


def valid_pl(value):
    try:
        number = int(value)
        return number if 1 <= number <= 160 else None
    except (TypeError, ValueError):
        return None


def mission_name(value):
    if isinstance(value, dict):
        for key in ("name", "displayName", "type"):
            if value.get(key):
                return str(value[key]).strip()
    return str(value or "").strip()


def is_vbucks_reward(reward):
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


def pennydb_missions(payload):
    """Get verified mission, Zone and Power Level from PennyDB."""

    if not isinstance(payload, dict):
        raise ValueError("Invalid PennyDB response")

    raw_zones = payload.get("missions")
    if not isinstance(raw_zones, dict):
        raise ValueError("PennyDB missions object missing")

    result = []

    for raw_zone, entries in raw_zones.items():
        zone = zone_name(raw_zone)

        if not zone or not isinstance(entries, list):
            continue

        for mission in entries:
            if not isinstance(mission, dict):
                continue

            rewards = (
                mission.get("alertRewards")
                or mission.get("rewards")
                or []
            )

            amount = None

            for reward in rewards:
                if not is_vbucks_reward(reward):
                    continue

                try:
                    amount = int(reward.get("quantity"))
                except (TypeError, ValueError):
                    continue

                if 0 < amount <= 5000:
                    break

                amount = None

            if amount is None:
                continue

            name = mission_name(mission.get("missionType"))
            if not name:
                continue

            item = {
                "mission": name,
                "zone": zone,
                "location": "",
                "vbucks": amount,
                "source": "PennyDB",
                "sources": ["PennyDB"],
            }

            pl = valid_pl(mission.get("pl"))
            if pl is not None:
                item["powerLevel"] = pl

            result.append(item)

    return result


def is_bad_location(value, zone):
    """Reject zone names, mission names and unrelated page text."""

    value = str(value or "").strip()

    if not value or len(value) > 65:
        return True

    if value.casefold() == zone.casefold():
        return True

    if zone_name(value):
        return True

    if REWARD_RE.search(value) or POWER_RE.search(value):
        return True

    if any(
        re.search(re.escape(name), value, re.I)
        for name in MISSION_NAMES
    ):
        return True

    if re.search(
        r"v-bucks|founders|mission alert|daily|weekly|"
        r"reward|available|completed|details|"
        r"save the world|fortnite|power level",
        value,
        re.I,
    ):
        return True

    return False


def find_location(card_lines, mission_index, zone):
    """
    Find the location in the HawkBucks mission card.

    Prefer explicit location labels and location attributes.
    Otherwise use the short location text immediately after
    the mission title, excluding the Zone itself.
    """

    # First: explicitly labelled location.
    for line in card_lines:
        match = LOCATION_LABEL_RE.match(line)
        if match:
            candidate = match.group(1).strip()
            if not is_bad_location(candidate, zone):
                return candidate

    # Second: location text directly after the mission title.
    for line in card_lines:
        candidate = line.strip()
        if is_bad_location(candidate, zone):
            continue

        return candidate

    return ""


def hawkbucks_missions(html):
    """Extract HawkBucks mission cards and their city/location."""

    lines = html_to_lines(html)
    reward_rows = []

    for index, line in enumerate(lines):
        match = REWARD_RE.search(line)
        if not match:
            continue

        raw = next(
            (group for group in match.groups() if group is not None),
            None,
        )

        if raw:
            amount = int(raw)
            if 0 < amount <= 5000:
                reward_rows.append((index, amount))

    result = []

    for row_number, (reward_index, reward) in enumerate(reward_rows):
        previous = (
            reward_rows[row_number - 1][0]
            if row_number else -1
        )

        next_index = (
            reward_rows[row_number + 1][0]
            if row_number + 1 < len(reward_rows)
            else len(lines)
        )

        start = max(previous + 1, reward_index - 40, 0)
        end = min(next_index, reward_index + 5, len(lines))
        card_lines = lines[start:end]

        mission_candidates = []

        for index, line in enumerate(card_lines):
            for name in MISSION_NAMES:
                if re.search(re.escape(name), line, re.I):
                    mission_candidates.append(
                        (abs((start + index) - reward_index), -len(name), name)
                    )

        if not mission_candidates:
            continue

        _, _, name = min(mission_candidates)

        zone_candidates = []

        for line in card_lines:
            for raw_zone, zone in ZONES.items():
                if re.search(re.escape(raw_zone), line, re.I):
                    zone_candidates.append(zone)

        if not zone_candidates:
            continue

        # Use the recognized Zone from the mission card.
        zone = zone_candidates[0]

        pl = None
        for line in card_lines:
            match = POWER_RE.search(line)
            if match:
                raw = next(
                    (group for group in match.groups() if group is not None),
                    None,
                )
                pl = valid_pl(raw)
                if pl is not None:
                    break

        mission_index = next(
            (
                start + i for i, line in enumerate(card_lines)
                if re.search(re.escape(name), line, re.I)
            ),
            start,
        )

        location = find_location(
            card_lines[mission_index - start + 1:],
            mission_index,
            zone,
        )

        item = {
            "mission": name,
            "zone": zone,
            "location": location,
            "vbucks": reward,
            "source": "HawkBucks",
            "sources": ["HawkBucks"],
        }

        if pl is not None:
            item["powerLevel"] = pl

        result.append(item)

    return result


def merge_missions(penny, hawk):
    """Merge matching mission records without losing source fields."""

    merged = {}

    for item in penny + hawk:
        key = (
            re.sub(r"\s+", " ", item["mission"]).casefold(),
            item["zone"].casefold(),
            int(item["vbucks"]),
        )

        if key not in merged:
            merged[key] = dict(item)
            merged[key]["sources"] = list(item.get("sources", []))
            continue

        current = merged[key]

        # PennyDB remains preferred for Zone and Power Level.
        if not current.get("powerLevel") and item.get("powerLevel"):
            current["powerLevel"] = item["powerLevel"]

        # Only accept a location that is not the Zone itself.
        location = item.get("location", "")
        if location and not is_bad_location(location, current["zone"]):
            if not current.get("location"):
                current["location"] = location

        for source in item.get("sources", []):
            if source not in current["sources"]:
                current["sources"].append(source)

    return list(merged.values())


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def find_history_day(days, target):
    for entry in days:
        if entry.get("date") == target:
            return entry
    return None


def main():
    now = now_utc()
    checked_at = timestamp()
    today = now.date().isoformat()
    yesterday = (now.date() - timedelta(days=1)).isoformat()

    old = load_json(
        MISSIONS_FILE,
        {"today": [], "yesterday": [], "sources": []},
    )

    history = load_json(HISTORY_FILE, {"days": []})
    days = history.get("days", [])

    if not isinstance(days, list):
        days = []

    source_results = []
    penny = []
    hawk = []

    # 1. PennyDB: mission, Zone and Power Level.
    penny_status = {
        "name": "PennyDB",
        "url": PENNYDB_API,
        "ok": False,
        "missionCount": 0,
        "powerLevelCount": 0,
        "locationCount": 0,
        "checkedAt": checked_at,
    }

    try:
        penny = pennydb_missions(get_json(PENNYDB_API))
        penny_status.update({
            "ok": True,
            "missionCount": len(penny),
            "powerLevelCount": sum(
                item.get("powerLevel") is not None for item in penny
            ),
            "locationCount": sum(
                bool(item.get("location")) for item in penny
            ),
            "status": "Fetched structured mission data",
        })
    except Exception as error:
        penny_status["status"] = f"Fetch failed: {str(error)[:180]}"

    source_results.append(penny_status)

    # 2. HawkBucks: mission city/location and supplementary data.
    hawk_status = {
        "name": "HawkBucks",
        "url": HAWKBUCKS_URL,
        "ok": False,
        "missionCount": 0,
        "powerLevelCount": 0,
        "locationCount": 0,
        "checkedAt": checked_at,
    }

    try:
        hawk_html = get_html(HAWKBUCKS_URL)
        hawk = hawkbucks_missions(hawk_html)

        hawk_status.update({
            "ok": True,
            "missionCount": len(hawk),
            "powerLevelCount": sum(
                item.get("powerLevel") is not None for item in hawk
            ),
            "locationCount": sum(
                bool(item.get("location")) for item in hawk
            ),
            "status": (
                "Fetched HawkBucks mission cards"
                if hawk else
                "Page fetched, but mission cards were not parsed"
            ),
        })
    except Exception as error:
        hawk_status["status"] = f"Fetch failed: {str(error)[:180]}"

    source_results.append(hawk_status)

    # 3. Merge the two sources.
    missions = merge_missions(penny, hawk)

    # Preserve last confirmed data if both sources return no rows.
    if missions:
        confirmed = True
        status = "confirmed"
    else:
        saved_today = find_history_day(days, today)

        if saved_today and saved_today.get("missions"):
            missions = saved_today["missions"]
        elif old.get("today"):
            missions = old["today"]

        confirmed = False
        status = "partial" if any(
            item.get("ok") for item in source_results
        ) else "unavailable"

    # 4. Remove any location that duplicates its Zone.
    for item in missions:
        location = str(item.get("location") or "").strip()
        zone = str(item.get("zone") or "").strip()

        if location.casefold() == zone.casefold():
            item["location"] = ""

    # 5. Preserve yesterday's saved missions.
    saved_yesterday = find_history_day(days, yesterday)

    if saved_yesterday:
        yesterday_missions = saved_yesterday.get("missions", [])
    else:
        yesterday_missions = old.get("yesterday", [])

    # 6. Update today's history.
    record = {
        "date": today,
        "checkedAt": checked_at,
        "confirmed": confirmed,
        "missions": missions,
        "sourceSummaries": source_results,
    }

    existing = find_history_day(days, today)

    if existing:
        index = days.index(existing)

        if confirmed or not existing.get("confirmed"):
            days[index] = record
        else:
            existing["checkedAt"] = checked_at
            existing["sourceSummaries"] = source_results
    else:
        days.append(record)

    days.sort(key=lambda item: item.get("date", ""))
    days = days[-400:]

    # 7. Save website data.
    output = {
        "updatedAt": checked_at,
        "confirmed": confirmed,
        "status": status,
        "today": missions,
        "yesterday": yesterday_missions,
        "sources": source_results,
        "historyDays": len(days),
        "historyAvailable": bool(days),
    }

    history_output = {
        "updatedAt": checked_at,
        "days": days,
    }

    save_json(MISSIONS_FILE, output)
    save_json(HISTORY_FILE, history_output)

    print(f"Date: {today}")
    print(f"Mission rows: {len(missions)}")

    for item in missions:
        print(
            f"{item.get('mission')} | "
            f"{item.get('zone')} | "
            f"{item.get('location') or 'Location unavailable'} | "
            f"{item.get('vbucks')} V-Bucks | "
            f"PL {item.get('powerLevel', 'Unknown')}"
        )

    for source in source_results:
        print(
            f"{source['name']}: "
            f"{source.get('status', 'No status')} | "
            f"Locations: {source.get('locationCount', 0)}"
        )

    if not any(source.get("ok") for source in source_results):
        sys.exit("All mission sources failed. Previous data was preserved.")


if __name__ == "__main__":
    main()
