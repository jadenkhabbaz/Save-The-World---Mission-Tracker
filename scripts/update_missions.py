#!/usr/bin/env python3
"""Fetch Save the World V-Bucks missions and maintain a daily archive.

Power Levels are taken only from source-labelled values (for example
"70 Power", "PL 70", or an explicitly labelled Power Level column).
The updater never guesses a Power Level from a mission name or zone.
"""

import json
import re
import sys
import time
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "public" / "data"
MISSIONS_FILE = DATA / "missions.json"
HISTORY_FILE = DATA / "history.json"

# HawkBucks' public page displays the live card details, including "70 Power".
# The other public trackers are fallbacks and can also expose a PL column.
SOURCES = [
    ("HawkBucks", "https://hawkbucks.com/"),
    ("V-Bucks Daily", "https://vbucksdaily.com/"),
    ("SaveTheWorldDB", "https://savetheworlddb.com/"),
    ("FortniteDB", "https://v2.fortnitedb.com/"),
]

ZONES = (
    "Stonewood",
    "Plankerton",
    "Canny Valley",
    "Twine Peaks",
    "Ventures",
)

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
    "Build the Radar",
    "Destroy the Encampments",
    "Eliminate and Collect",
    "Resupply",
    "Fight Category",
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


class TextExtractor(HTMLParser):
    """Extract readable page text and useful accessibility/data attributes."""

    BLOCKS = {
        "p", "div", "section", "article", "tr", "li", "h1", "h2",
        "h3", "h4", "br", "td", "th", "main", "header", "footer",
    }
    SKIP_TAGS = {"script", "style", "noscript", "svg"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.skip_depth = 0
        self.script_depth = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)

        if tag in self.SKIP_TAGS:
            self.skip_depth += 1
            return

        # Do not discard useful data attributes. Some pages expose PL in
        # aria-label/title or data-power-level attributes rather than text.
        for key in (
            "alt", "aria-label", "title", "data-power-level",
            "data-powerlevel", "data-pl", "data-power",
        ):
            value = attrs.get(key)
            if value:
                self.parts.append("\n" + str(value) + "\n")

        if self.skip_depth:
            return

        if tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP_TAGS and self.skip_depth:
            self.skip_depth -= 1
        elif not self.skip_depth and tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip_depth:
            self.parts.append(data)


def fetch(url):
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (compatible; "
                "SaveTheWorldMissionTracker/3.0; public fan project)"
            ),
            "Accept": "text/html,application/xhtml+xml,application/json",
        },
    )

    with urlopen(request, timeout=30) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status}")
        raw = response.read(8_000_000)

    decoded = raw.decode("utf-8", "replace")
    parser = TextExtractor()
    parser.feed(decoded)

    # HTMLParser extracts server-rendered text and useful accessibility/data
    # attributes. Do not append the raw markup: that would merge unrelated
    # cards into one enormous line and make their PL/location association noisy.
    readable = "\n".join(parser.parts)
    readable = re.sub(r"[ \t\xa0]+", " ", readable)
    return re.sub(r"\n\s*\n+", "\n", readable)


def find_summary(text):
    labels = [
        ("today", r"(?:Today|Today’s|Today\s+V-Bucks|V-Bucks Today)"),
        ("yesterday", r"Yesterday"),
        ("last7Days", r"(?:This Week|Last 7 Days)"),
        ("last30Days", r"(?:This Month|Last 30 Days)"),
        ("thisYear", r"This Year"),
    ]
    result = {}

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


def _normal_lines(text):
    lines = [re.sub(r"\s+", " ", line).strip(" -|•·") for line in text.splitlines()]
    return [line for line in lines if line]


def _mission_at(lines, start, end, reward_index):
    candidates = []
    for index in range(start, end):
        line = lines[index]
        for name in MISSION_NAMES:
            if re.search(re.escape(name), line, re.I):
                candidates.append((abs(index - reward_index), -len(name), index, name))
    return min(candidates) if candidates else None


def _zone_at(lines, start, end, mission_index):
    candidates = []
    for index in range(start, end):
        for zone in ZONES:
            if re.search(re.escape(zone), lines[index], re.I):
                candidates.append((abs(index - mission_index), index, zone))
    return min(candidates) if candidates else None


def _power_level(lines, start, end, mission_index, has_power_column):
    candidates = []

    # First preference: an explicitly labelled value such as "70 Power".
    for index in range(start, end):
        match = EXPLICIT_POWER_RE.search(lines[index])
        if not match:
            continue
        value = next((group for group in match.groups() if group is not None), None)
        if value and 2 <= int(value) <= 160:
            candidates.append((abs(index - mission_index), 0, int(value)))

    if candidates:
        return min(candidates)[2]

    # Some trackers render a table with a separate "PL" / "Power Level"
    # column, leaving a bare number in the same row. Only use a bare number
    # when that column heading is present on the source page.
    if has_power_column:
        for index in range(max(start, mission_index - 5), mission_index + 1):
            match = re.fullmatch(r"\s*(\d{1,3})\s*", lines[index])
            if match:
                value = int(match.group(1))
                if 2 <= value <= 160:
                    candidates.append((abs(index - mission_index), 1, value))

    return min(candidates)[2] if candidates else None


def extract_missions(text, source):
    lines = _normal_lines(text)
    if not lines:
        return []

    # Only use a bare PL number if the page itself labels a PL/Power Level
    # column alongside mission information. This prevents arbitrary numbers
    # (reward amounts, mission category numbers, etc.) becoming Power Levels.
    has_power_column = bool(
        re.search(r"\bPower\s*Level\b", text, re.I)
        or re.search(r"\bPL\b.{0,100}\bMISSION\b", text, re.I | re.S)
        or re.search(r"\bMISSION\b.{0,100}\bPL\b", text, re.I | re.S)
    )

    reward_rows = []
    for index, line in enumerate(lines):
        match = REWARD_RE.search(line)
        if not match:
            continue
        reward_text = next((group for group in match.groups() if group is not None), None)
        if not reward_text:
            continue
        reward = int(reward_text)
        if 0 < reward <= 5000:
            reward_rows.append((index, reward))

    found = []
    seen = set()

    for row_number, (reward_index, reward) in enumerate(reward_rows):
        # Restrict each search to the text between adjacent reward rows. A
        # wider card window is needed because nested page markup creates many
        # text breaks between mission title, location, PL and reward.
        previous_reward = reward_rows[row_number - 1][0] if row_number else -1
        start = max(previous_reward + 1, reward_index - 45, 0)
        end = min(
            reward_rows[row_number + 1][0] if row_number + 1 < len(reward_rows) else len(lines),
            reward_index + 4,
        )
        if end <= start:
            continue

        mission_info = _mission_at(lines, start, end, reward_index)
        if not mission_info:
            continue
        _, _, mission_index, mission = mission_info

        zone_info = _zone_at(lines, start, end, mission_index)
        if not zone_info:
            continue
        _, zone_index, zone = zone_info

        location = ""
        # A location is usually printed immediately after the mission title.
        for candidate in lines[mission_index + 1:min(end, mission_index + 5)]:
            if not any(re.search(re.escape(z), candidate, re.I) for z in ZONES):
                if (
                    len(candidate) < 80
                    and not re.search(
                        r"V[- ]?Bucks|Power|Founders|reward|mission|Category",
                        candidate,
                        re.I,
                    )
                ):
                    location = candidate
                    break

        power_level = _power_level(
            lines,
            start,
            end,
            mission_index,
            has_power_column,
        )

        item = {
            "mission": mission,
            "zone": zone,
            "location": location,
            "vbucks": reward,
            "source": source,
        }
        if power_level is not None:
            item["powerLevel"] = power_level

        key = (mission.lower(), zone.lower(), reward)
        if key not in seen:
            found.append(item)
            seen.add(key)

    return found


def clean_power_levels(obj):
    if isinstance(obj, dict):
        if "powerLevel" in obj:
            try:
                level = int(obj["powerLevel"])
            except (TypeError, ValueError):
                level = 0
            if level < 2 or level > 160:
                obj.pop("powerLevel", None)
        for value in obj.values():
            clean_power_levels(value)
    elif isinstance(obj, list):
        for value in obj:
            clean_power_levels(value)
    return obj


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def main():
    now = (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    today = date.today().isoformat()

    old = clean_power_levels(
        load_json(MISSIONS_FILE, {"today": [], "confirmed": False, "sources": []})
    )
    history = clean_power_levels(load_json(HISTORY_FILE, {"days": []}))

    source_results = []
    all_missions = []

    for name, url in SOURCES:
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
            page = fetch(url)
            summary = find_summary(page)
            missions = extract_missions(page, name)
            entry.update({
                "ok": True,
                "summary": summary,
                "missionCount": len(missions),
                "powerLevelCount": sum(m.get("powerLevel") is not None for m in missions),
                "status": "Fetched public page",
            })
            all_missions.extend(missions)
        except Exception as error:
            entry["status"] = "Fetch failed: " + str(error)[:180]

        source_results.append(entry)
        time.sleep(0.5)

    # Merge duplicate missions while preserving a Power Level from whichever
    # source supplied it. No value is fabricated when every source omits it.
    dedup = {}
    for mission in all_missions:
        key = (
            mission["mission"].lower(),
            mission["zone"].lower(),
            mission["vbucks"],
        )
        if key not in dedup:
            dedup[key] = dict(mission, sources=[mission["source"]])
        else:
            existing = dedup[key]
            if existing.get("powerLevel") is None and mission.get("powerLevel") is not None:
                existing["powerLevel"] = mission["powerLevel"]
            if not existing.get("location") and mission.get("location"):
                existing["location"] = mission["location"]
            if mission["source"] not in existing["sources"]:
                existing["sources"].append(mission["source"])

    today_missions = list(dedup.values())
    confirmed = bool(today_missions) and any(s["ok"] for s in source_results)

    # If every source temporarily fails to expose rows, retain the last saved
    # rows but mark them unconfirmed. Never replace them with a fake zero list.
    if not today_missions and old.get("confirmed") and old.get("today"):
        today_missions = old["today"]
        confirmed = False

    record = {
        "date": today,
        "checkedAt": now,
        "confirmed": confirmed,
        "missions": today_missions,
        "sourceSummaries": [
            {
                "name": source["name"],
                "url": source["url"],
                "ok": source["ok"],
                "summary": source["summary"],
                "status": source.get("status", "No status"),
            }
            for source in source_results
        ],
    }

    days = history.get("days", [])
    existing_index = next(
        (index for index, item in enumerate(days) if item.get("date") == today),
        None,
    )

    if existing_index is None:
        days.append(record)
    else:
        previous = days[existing_index]
        if confirmed or not previous.get("confirmed"):
            days[existing_index] = record
        else:
            previous["checkedAt"] = now
            previous["sourceSummaries"] = record["sourceSummaries"]

    days = sorted(days, key=lambda item: item.get("date", ""))[-400:]
    history_output = {"updatedAt": now, "days": days}

    output = {
        "updatedAt": now,
        "confirmed": confirmed,
        "status": (
            "confirmed"
            if confirmed
            else "partial"
            if any(source["ok"] for source in source_results)
            else "unavailable"
        ),
        "today": today_missions,
        "yesterday": old.get("yesterday", []),
        "sources": source_results,
        "historyDays": len(days),
        "historyAvailable": bool(days),
    }

    DATA.mkdir(parents=True, exist_ok=True)
    MISSIONS_FILE.write_text(
        json.dumps(output, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    HISTORY_FILE.write_text(
        json.dumps(history_output, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    power_count = sum(mission.get("powerLevel") is not None for mission in today_missions)
    print(
        f"Checked {len(SOURCES)} sources; "
        f"{sum(source['ok'] for source in source_results)} reachable; "
        f"{len(today_missions)} mission rows; "
        f"{power_count} rows with source-labelled Power Levels; "
        f"{len(days)} archived days."
    )

    if not any(source["ok"] for source in source_results):
        sys.exit(
            "All public mission sources failed; saved source statuses "
            "without inventing mission rows or Power Levels."
        )


if __name__ == "__main__":
    main()
