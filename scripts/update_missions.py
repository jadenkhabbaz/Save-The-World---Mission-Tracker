#!/usr/bin/env python3
"""Fetch public Save the World mission data and maintain a daily archive.
Power Levels are only accepted when explicitly labelled by a source.
"""
import json, re, sys, time
from datetime import datetime, timezone, date
from urllib.request import Request, urlopen
from html.parser import HTMLParser
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
DATA=ROOT/"public"/"data"
MISSIONS_FILE=DATA/"missions.json"
HISTORY_FILE=DATA/"history.json"
SOURCES=[
 ("HawkBucks","https://hawkbucks.com/en"),
 ("V-Bucks Daily","https://vbucksdaily.com/"),
 ("SaveTheWorldDB","https://savetheworlddb.com/"),
 ("FortniteDB","https://v2.fortnitedb.com/"),
]

class TextExtractor(HTMLParser):
 BLOCKS={"p","div","section","article","tr","li","h1","h2","h3","h4","br","td","th"}
 def __init__(self):
  super().__init__(convert_charrefs=True); self.parts=[]; self.skip=0
 def handle_starttag(self,tag,attrs):
  attrs=dict(attrs)
  if tag in ("script","style","noscript","svg"): self.skip+=1
  if self.skip: return
  if tag in self.BLOCKS: self.parts.append("\n")
  if tag in ("img","input"):
   label=attrs.get("alt") or attrs.get("aria-label") or attrs.get("title") or attrs.get("value")
   if label: self.parts.append(" "+label+" ")
  for key in ("aria-label","title"):
   if attrs.get(key) and tag not in ("img","input"): self.parts.append(" "+attrs[key]+" ")
 def handle_endtag(self,tag):
  if tag in ("script","style","noscript","svg") and self.skip: self.skip-=1
  if not self.skip and tag in self.BLOCKS: self.parts.append("\n")
 def handle_data(self,data):
  if not self.skip: self.parts.append(data)

def fetch(url):
 req=Request(url,headers={"User-Agent":"Mozilla/5.0 (compatible; SaveTheWorldMissionTracker/2.0; public fan project)","Accept":"text/html,application/xhtml+xml"})
 with urlopen(req,timeout=25) as response:
  if response.status!=200: raise RuntimeError(f"HTTP {response.status}")
  raw=response.read(4_000_000)
 parser=TextExtractor(); parser.feed(raw.decode("utf-8","replace"))
 value=re.sub(r"[ \t\xa0]+"," ","".join(parser.parts))
 return re.sub(r"\n\s*\n+","\n",value)

def find_summary(text):
 labels=[("today",r"(?:Today|Today’s|Today\s+V-Bucks|V-Bucks Today)"),("yesterday",r"Yesterday"),("last7Days",r"(?:This Week|Last 7 Days)"),("last30Days",r"(?:This Month|Last 30 Days)"),("thisYear",r"This Year")]
 result={}
 for key,label in labels:
  for match in re.finditer(label,text,re.I):
   amount=re.search(r"(?<![\w])([\d,]+)\s*(?:V-Bucks)?",text[match.end():match.end()+180],re.I)
   if amount:
    value=int(amount.group(1).replace(",",""))
    if value<=1_000_000: result[key]=value; break
 return result

def extract_missions(text,source):
 found=[]
 lines=[re.sub(r"\s+"," ",x).strip(" -|•·") for x in text.splitlines()]
 lines=[x for x in lines if x]
 zones=("Stonewood","Plankerton","Canny Valley","Twine Peaks","Ventures")
 words=("Fight Category 4 Storm","Fight Category 3 Storm","Fight Category 2 Storm","Fight the Storm","Deliver the Bomb","Ride the Lightning","Retrieve the Data","Repair the Shelter","Evacuate the Shelter","Rescue the Survivors","Build the Radar","Destroy the Encampments","Fight Category")
 for i,line in enumerate(lines):
  if not re.search(r"V[- ]?Bucks",line,re.I): continue
  reward_match=re.search(r"V[- ]?Bucks\s*(?:(?:x|×)\s*)?(\d{1,4})\b|\b(?:x|×)\s*(\d{1,4})\s*V[- ]?Bucks|\b(\d{1,4})\s*V[- ]?Bucks",line,re.I)
  if not reward_match: continue
  reward=int(next(g for g in reward_match.groups() if g))
  if not 0<reward<=5000: continue
  window_lines=lines[max(0,i-6):min(len(lines),i+3)]
  window=" ".join(window_lines)
  mission=next((w for w in words if re.search(re.escape(w),window,re.I)),None)
  zone=next((z for z in zones if re.search(re.escape(z),window,re.I)),None)
  if not mission or not zone: continue
  location=""
  for candidate in window_lines:
   if zone.lower() in candidate.lower():
    remainder=re.sub(re.escape(zone),"",candidate,flags=re.I).strip(" -|•·,")
    remainder=re.sub(r"\b(?:PL\s*)?\d{1,3}\b","",remainder,flags=re.I).strip(" -|•·,")
    if remainder and len(remainder)<80 and not re.search(r"V[- ]?Bucks|Founders|reward|mission",remainder,re.I): location=remainder
    break
  # Do not interpret arbitrary nearby numbers as Power Level.
  power_level=None
  for candidate in window_lines:
   match=re.search(r"\bPL\s*[:#-]?\s*(\d{1,3})\b|\bPower\s*Level\s*[:#-]?\s*(\d{1,3})\b|\b(\d{1,3})\s*PL\b",candidate,re.I)
   if match:
    value=next((g for g in match.groups() if g is not None),None)
    if value and 2<=int(value)<=160: power_level=int(value); break
  item={"mission":mission,"zone":zone,"location":location,"vbucks":reward,"source":source}
  if power_level is not None: item["powerLevel"]=power_level
  key=(mission.lower(),zone.lower(),reward)
  if not any((x["mission"].lower(),x["zone"].lower(),x["vbucks"])==key for x in found): found.append(item)
 return found

def clean_power_levels(obj):
 if isinstance(obj,dict):
  if "powerLevel" in obj:
   try: level=int(obj["powerLevel"])
   except (TypeError,ValueError): level=0
   if level<2 or level>160: obj.pop("powerLevel",None)
  for value in obj.values(): clean_power_levels(value)
 elif isinstance(obj,list):
  for value in obj: clean_power_levels(value)
 return obj

def load_json(path,default):
 try: return json.loads(path.read_text(encoding="utf-8"))
 except (OSError,ValueError): return default

def main():
 now=datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")
 today=date.today().isoformat()
 old=clean_power_levels(load_json(MISSIONS_FILE,{"today":[],"confirmed":False,"sources":[]}))
 history=clean_power_levels(load_json(HISTORY_FILE,{"days":[]}))
 source_results=[]; all_missions=[]
 for name,url in SOURCES:
  entry={"name":name,"url":url,"ok":False,"summary":{},"missionCount":0,"checkedAt":now}
  try:
   page=fetch(url); summary=find_summary(page); missions=extract_missions(page,name)
   entry.update({"ok":True,"summary":summary,"missionCount":len(missions),"status":"Fetched public page"})
   all_missions.extend(missions)
  except Exception as error: entry["status"]="Fetch failed: "+str(error)[:180]
  source_results.append(entry); time.sleep(.5)
 dedup={}
 for mission in all_missions:
  key=(mission["mission"].lower(),mission["zone"].lower(),mission["vbucks"])
  if key not in dedup: dedup[key]=dict(mission,sources=[mission["source"]])
  elif mission["source"] not in dedup[key]["sources"]: dedup[key]["sources"].append(mission["source"])
 today_missions=list(dedup.values())
 confirmed=bool(today_missions) and any(s["ok"] for s in source_results)
 if not today_missions and old.get("confirmed") and old.get("today"):
  today_missions=old["today"]; confirmed=False
 record={"date":today,"checkedAt":now,"confirmed":confirmed,"missions":today_missions,"sourceSummaries":[{"name":s["name"],"url":s["url"],"ok":s["ok"],"summary":s["summary"],"status":s["status"]} for s in source_results]}
 days=history.get("days",[])
 existing=next((i for i,d in enumerate(days) if d.get("date")==today),None)
 if existing is None: days.append(record)
 else:
  previous=days[existing]
  if confirmed or not previous.get("confirmed"): days[existing]=record
  else: previous["checkedAt"]=now; previous["sourceSummaries"]=record["sourceSummaries"]
 days=sorted(days,key=lambda d:d.get("date",""))[-400:]
 history={"updatedAt":now,"days":days}
 output={"updatedAt":now,"confirmed":confirmed,"status":"confirmed" if confirmed else "partial" if any(s["ok"] for s in source_results) else "unavailable","today":today_missions,"yesterday":old.get("yesterday",[]),"sources":source_results,"historyDays":len(days),"historyAvailable":bool(days)}
 DATA.mkdir(parents=True,exist_ok=True)
 MISSIONS_FILE.write_text(json.dumps(output,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
 HISTORY_FILE.write_text(json.dumps(history,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
 print(f"Checked {len(SOURCES)} sources; {sum(s['ok'] for s in source_results)} reachable; {len(today_missions)} explicit mission rows; {len(days)} archived days.")
 if not any(s["ok"] for s in source_results): sys.exit("All public mission sources failed; saved source statuses without inventing zero missions.")

if __name__=="__main__": main()
