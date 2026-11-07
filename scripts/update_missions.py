#!/usr/bin/env python3
"""Automatic Save the World V-Bucks mission updater.

Reads PennyDB's structured mission data and HawkBucks' embedded React Query
state. HawkBucks mission objects use:
  area       = larger region (Canny Valley, Twine Peaks, etc.)
  zone       = actual in-game zone/tile label (Desert, Grasslands, etc.)
The public JSON keeps the existing frontend contract: zone=area and
location=the mission's actual in-game zone label.
"""

import json
import re
import sys
from datetime import datetime, timezone, timedelta
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
    "stonewood": "Stonewood", "plankerton": "Plankerton",
    "canny valley": "Canny Valley", "twine peaks": "Twine Peaks",
    "ventures": "Ventures",
}
MISSION_NAMES = (
    "Fight Category 4 Storm", "Fight Category 3 Storm",
    "Fight Category 2 Storm", "Fight Category 1 Storm",
    "Fight the Storm", "Deliver the Bomb", "Ride the Lightning",
    "Retrieve the Data", "Repair the Shelter", "Evacuate the Shelter",
    "Rescue the Survivors", "Build the Radar Grid", "Build the Radar",
    "Destroy the Encampments", "Eliminate and Collect", "Resupply",
)
REWARD_RE = re.compile(
    r"V[- ]?Bucks\s*(?:(?:x|×)\s*)?(\d{1,4})"
    r"|\b(?:x|×)\s*(\d{1,4})\s*V[- ]?Bucks"
    r"|\b(\d{1,4})\s*V[- ]?Bucks", re.I)
POWER_RE = re.compile(
    r"\bPL\s*[:#-]?\s*(\d{1,3})\b"
    r"|\bPower\s*Level\s*[:#-]?\s*(\d{1,3})\b"
    r"|\b(\d{1,3})\s*PL\b", re.I)


def now_utc():
    return datetime.now(timezone.utc).replace(microsecond=0)


def timestamp():
    return now_utc().isoformat().replace("+00:00", "Z")


def fetch(url, accept):
    req = Request(url, headers={
        "User-Agent": "Mozilla/5.0 JadBakerX-STW-Tracker",
        "Accept": accept,
    })
    with urlopen(req, timeout=30) as response:
        return response.read().decode("utf-8", "replace")


def get_json(url):
    return json.loads(fetch(url, "application/json"))


def zone_name(value):
    return ZONES.get(str(value or "").replace("_", " ").strip().casefold())


def valid_pl(value):
    try:
        n = int(value)
        return n if 1 <= n <= 160 else None
    except (TypeError, ValueError):
        return None


def is_vbucks_reward(reward):
    if not isinstance(reward, dict):
        return False
    kind = str(reward.get("itemType") or reward.get("templateId") or "").casefold()
    name = re.sub(r"[\s_-]+", "", str(reward.get("name") or "").casefold())
    return "currency_mtxswap" in kind or "mtxswap" in kind or "vbucks" in name or "vbuck" in name


def pennydb_missions(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("missions"), dict):
        raise ValueError("PennyDB missions object missing")
    result = []
    for raw_area, entries in payload["missions"].items():
        area = zone_name(raw_area)
        if not area or not isinstance(entries, list):
            continue
        for mission in entries:
            if not isinstance(mission, dict):
                continue
            amount = None
            for reward in mission.get("alertRewards") or mission.get("rewards") or []:
                if is_vbucks_reward(reward):
                    try:
                        candidate = int(reward.get("quantity"))
                        if 0 < candidate <= 5000:
                            amount = candidate
                            break
                    except (TypeError, ValueError):
                        pass
            if amount is None:
                continue
            raw_name = mission.get("missionType") or ""
            name = raw_name.get("name") or raw_name.get("displayName") or raw_name.get("type") if isinstance(raw_name, dict) else str(raw_name)
            if not name:
                continue
            item = {"mission": str(name), "zone": area, "location": "", "vbucks": amount,
                    "source": "PennyDB", "sources": ["PennyDB"]}
            pl = valid_pl(mission.get("pl"))
            if pl:
                item["powerLevel"] = pl
            result.append(item)
    return result


def decode_query_state(html):
    """Decode the queryState JSON string embedded in HawkBucks page HTML."""
    patterns = (
        r'queryState\s*:\s*("(?:\\.|[^"\\])*")',
        r'["\']queryState["\']\s*:\s*("(?:\\.|[^"\\])*")',
    )
    for pattern in patterns:
        match = re.search(pattern, html)
        if match:
            raw = json.loads(match.group(1))
            if isinstance(raw, str):
                return json.loads(raw)
            if isinstance(raw, dict):
                return raw
    # Some builds serialize the state directly as an object rather than a string.
    match = re.search(r'["\']queryState["\']\s*:\s*(\{.*?\})\s*[,}]', html, re.S)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    return None


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def mission_rows_from_query_state(query_state):
    """Read mission objects from React Query's dehydrated [\"missions\"] query."""
    if not isinstance(query_state, dict):
        return []
    queries = query_state.get("queries", [])
    if not isinstance(queries, list):
        return []

    mission_objects = []
    for query in queries:
        if not isinstance(query, dict):
            continue
        key = query.get("queryKey") or []
        if not (isinstance(key, list) and key and str(key[0]).casefold() == "missions"):
            continue
        state = query.get("state") or {}
        data = state.get("data") if isinstance(state, dict) else None
        for obj in walk(data):
            if all(k in obj for k in ("name", "area", "zone", "vbucks")):
                mission_objects.append(obj)

    result = []
    seen = set()
    for obj in mission_objects:
        try:
            amount = int(obj.get("vbucks"))
        except (TypeError, ValueError):
            continue
        if not 0 < amount <= 5000:
            continue
        name = str(obj.get("name") or "").strip()
        area_raw = str(obj.get("area") or "").strip()
        actual_zone = str(obj.get("zone") or "").strip()
        area = zone_name(area_raw)
        if not name or not area or not actual_zone:
            continue
        # Deduplicate the same mission if the query state nests it more than once.
        ident = (str(obj.get("id") or ""), name.casefold(), area.casefold(), actual_zone.casefold(), amount)
        if ident in seen:
            continue
        seen.add(ident)
        item = {
            "mission": name,
            "zone": area,
            "location": actual_zone,
            "vbucks": amount,
            "source": "HawkBucks",
            "sources": ["HawkBucks"],
        }
        pl = valid_pl(obj.get("powerLevel") or obj.get("pl"))
        if pl:
            item["powerLevel"] = pl
        result.append(item)
    return result


class TextParser(HTMLParser):
    BLOCKS = {"div", "section", "article", "p", "li", "tr", "td", "th", "h1", "h2", "h3", "h4", "br"}
    SKIP = {"script", "style", "noscript", "svg"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        elif not self.skip and tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        elif not self.skip and tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def hawkbucks_fallback_html(html):
    """Legacy visible-text parser; queryState extraction is preferred."""
    parser = TextParser()
    parser.feed(html)
    lines = [re.sub(r"\s+", " ", x).strip(" -|•") for x in "\n".join(parser.parts).splitlines() if x.strip()]
    out = []
    for i, line in enumerate(lines):
        reward = REWARD_RE.search(line)
        if not reward:
            continue
        amount = next((g for g in reward.groups() if g), None)
        if not amount:
            continue
        start, end = max(0, i - 30), min(len(lines), i + 4)
        block = lines[start:end]
        name = next((n for n in MISSION_NAMES if any(re.search(re.escape(n), x, re.I) for x in block)), None)
        area = next((z for x in block for raw, z in ZONES.items() if re.search(re.escape(raw), x, re.I)), None)
        if not name or not area:
            continue
        pl = None
        for x in block:
            m = POWER_RE.search(x)
            if m:
                pl = valid_pl(next((g for g in m.groups() if g), None))
                if pl:
                    break
        out.append({"mission": name, "zone": area, "location": "", "vbucks": int(amount),
                    "source": "HawkBucks", "sources": ["HawkBucks"], **({"powerLevel": pl} if pl else {})})
    return out


def hawkbucks_missions(html):
    state = decode_query_state(html)
    if state is not None:
        rows = mission_rows_from_query_state(state)
        if rows:
            return rows, "Parsed mission rows from embedded queryState"
    rows = hawkbucks_fallback_html(html)
    return rows, ("Parsed legacy mission cards" if rows else
                  "Page fetched, but no mission rows were found in queryState or visible page text")


def merge_missions(penny, hawk):
    merged = {}
    for item in penny + hawk:
        key = (re.sub(r"\s+", " ", item["mission"]).casefold(), item["zone"].casefold(), int(item["vbucks"]))
        if key not in merged:
            merged[key] = dict(item)
            merged[key]["sources"] = list(item.get("sources", []))
            continue
        current = merged[key]
        if not current.get("powerLevel") and item.get("powerLevel"):
            current["powerLevel"] = item["powerLevel"]
        # HawkBucks' `zone` is the actual map tile label; preserve it as location.
        if item.get("location") and not current.get("location"):
            current["location"] = item["location"]
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
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def find_history_day(days, target):
    return next((entry for entry in days if entry.get("date") == target), None)


def main():
    checked_at = timestamp()
    today = now_utc().date().isoformat()
    yesterday = (now_utc().date() - timedelta(days=1)).isoformat()
    old = load_json(MISSIONS_FILE, {"today": [], "yesterday": [], "sources": []})
    history = load_json(HISTORY_FILE, {"days": []})
    days = history.get("days", []) if isinstance(history.get("days", []), list) else []
    penny, hawk, sources = [], [], []

    pstatus = {"name": "PennyDB", "url": PENNYDB_API, "ok": False, "missionCount": 0,
              "powerLevelCount": 0, "locationCount": 0, "checkedAt": checked_at}
    try:
        penny = pennydb_missions(get_json(PENNYDB_API))
        pstatus.update(ok=True, missionCount=len(penny),
                       powerLevelCount=sum(bool(x.get("powerLevel")) for x in penny),
                       locationCount=sum(bool(x.get("location")) for x in penny),
                       status="Fetched structured mission data")
    except Exception as exc:
        pstatus["status"] = f"Fetch failed: {str(exc)[:180]}"
    sources.append(pstatus)

    hstatus = {"name": "HawkBucks", "url": HAWKBUCKS_URL, "ok": False, "missionCount": 0,
              "powerLevelCount": 0, "locationCount": 0, "checkedAt": checked_at}
    try:
        hawk, message = hawkbucks_missions(fetch(HAWKBUCKS_URL, "text/html,application/xhtml+xml"))
        hstatus.update(ok=True, missionCount=len(hawk),
                       powerLevelCount=sum(bool(x.get("powerLevel")) for x in hawk),
                       locationCount=sum(bool(x.get("location")) for x in hawk), status=message)
    except Exception as exc:
        hstatus["status"] = f"Fetch failed: {str(exc)[:180]}"
    sources.append(hstatus)

    missions = merge_missions(penny, hawk)
    confirmed = bool(missions)
    status = "confirmed" if confirmed else ("partial" if any(s["ok"] for s in sources) else "unavailable")
    saved_yesterday = find_history_day(days, yesterday)
    yesterday_missions = saved_yesterday.get("missions", []) if saved_yesterday else old.get("yesterday", [])

    record = {"date": today, "checkedAt": checked_at, "confirmed": confirmed,
              "missions": missions, "sourceSummaries": sources}
    existing = find_history_day(days, today)
    if existing:
        days[days.index(existing)] = record
    else:
        days.append(record)
    days.sort(key=lambda x: x.get("date", ""))
    days = days[-400:]

    output = {"updatedAt": checked_at, "confirmed": confirmed, "status": status,
              "today": missions, "yesterday": yesterday_missions, "sources": sources,
              "historyDays": len(days), "historyAvailable": bool(days)}
    save_json(MISSIONS_FILE, output)
    save_json(HISTORY_FILE, {"updatedAt": checked_at, "days": days})

    print(f"Date: {today}\nMission rows: {len(missions)}")
    for item in missions:
        print(f"{item['mission']} | {item['zone']} | {item.get('location') or 'Zone unavailable'} | "
              f"{item['vbucks']} V-Bucks | PL {item.get('powerLevel', 'Unknown')}")
    for source in sources:
        print(f"{source['name']}: {source.get('status', 'No status')} | "
              f"Locations: {source.get('locationCount', 0)}")
    if not any(s.get("ok") for s in sources):
        sys.exit("Both mission sources failed. Today's board was cleared; history was preserved.")


if __name__ == "__main__":
    main()
