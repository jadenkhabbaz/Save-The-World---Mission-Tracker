#!/usr/bin/env python3
"""Collect public Save the World mission summaries and maintain a daily archive.

No private APIs or credentials are used. Individual mission extraction is best-effort;
when sources do not expose details, the script records source summaries/status rather
than inventing mission rows or replacing known data with false zeroes.
"""
import json, os, re, sys, time
from datetime import datetime, timezone, date
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'public' / 'data'
MISSIONS_FILE = DATA / 'missions.json'
HISTORY_FILE = DATA / 'history.json'
SOURCES = [
    ('HawkBucks', 'https://hawkbucks.com/vbucks-missions'),
    ('V-Bucks Daily', 'https://vbucksdaily.com/'),
    ('SaveTheWorldDB', 'https://savetheworlddb.com/'),
    ('FortniteDB', 'https://v2.fortnitedb.com/'),
]

class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts=[]; self.skip=0
    def handle_starttag(self, tag, attrs):
        if tag in ('script','style','noscript','svg'): self.skip += 1
        if tag in ('p','div','section','article','tr','li','h1','h2','h3','h4','br'): self.parts.append('\n')
    def handle_endtag(self, tag):
        if tag in ('script','style','noscript','svg') and self.skip: self.skip -= 1
        if tag in ('p','div','section','article','tr','li','h1','h2','h3','h4'): self.parts.append('\n')
    def handle_data(self, data):
        if not self.skip: self.parts.append(data)

def fetch(url):
    req=Request(url, headers={'User-Agent':'Mozilla/5.0 (compatible; SaveTheWorldMissionTracker/2.0; public fan project)', 'Accept':'text/html,application/xhtml+xml'})
    with urlopen(req, timeout=25) as resp:
        if resp.status != 200: raise RuntimeError(f'HTTP {resp.status}')
        raw=resp.read(4_000_000)
    parser=TextExtractor(); parser.feed(raw.decode('utf-8','replace'))
    text=re.sub(r'[ \t\xa0]+',' ', ''.join(parser.parts))
    text=re.sub(r'\n\s*\n+', '\n', text)
    return text

def find_summary(text):
    # Read summary cards when present. These are source-reported totals, not our own guesses.
    labels = [('today', r'(?:Today|Today’s|Today\s+V-Bucks|V-Bucks Today)'),
              ('yesterday', r'Yesterday'), ('last7Days', r'(?:This Week|Last 7 Days)'),
              ('last30Days', r'(?:This Month|Last 30 Days)'), ('thisYear', r'This Year')]
    out={}
    for key, lab in labels:
        for m in re.finditer(lab, text, re.I):
            segment=text[m.end():m.end()+180]
            # Site cards often show amount then mission count; use the first amount near label.
            amt=re.search(r'(?<![\w])([\d,]+)\s*(?:V-Bucks)?', segment, re.I)
            if amt:
                value=int(amt.group(1).replace(',',''))
                if value <= 1000000:
                    out[key]=value; break
    return out

def extract_missions(text, source):
    """Conservative parser for explicit V-Bucks mission rows/cards in source text."""
    found=[]
    # Sources differ; scan lines containing a V-Bucks reward and use nearby line as mission.
    lines=[re.sub(r'\s+',' ',x).strip(' -|•') for x in text.splitlines()]
    lines=[x for x in lines if x]
    zones=('Stonewood','Plankerton','Canny Valley','Twine Peaks','Ventures')
    mission_words=('Fight the Storm','Deliver the Bomb','Ride the Lightning','Retrieve the Data',
                   'Repair the Shelter','Evacuate the Shelter','Rescue the Survivors','Build the Radar','Destroy the Encampments','Fight Category')
    for i,line in enumerate(lines):
        if not re.search(r'\bV[- ]?Bucks\b', line, re.I): continue
        reward_match=re.search(r'(?:V[- ]?Bucks\s*(?:x|×)?\s*|(?:x|×)\s*)(\d{1,4})\b|\b(\d{1,4})\s*V[- ]?Bucks\b',line,re.I)
        if not reward_match: continue
        reward=int(next(g for g in reward_match.groups() if g))
        if reward<=0 or reward>5000: continue
        window=' '.join(lines[max(0,i-5):i+2])
        mission=next((w for w in mission_words if re.search(re.escape(w),window,re.I)),None)
        zone=next((z for z in zones if re.search(re.escape(z),window,re.I)),None)
        if not mission or not zone: continue
        # avoid capturing broad page summaries as mission rows
        key=(mission.lower(),zone.lower(),reward)
        if any((x['mission'].lower(),x['zone'].lower(),x['vbucks'])==key for x in found): continue
        found.append({'mission':mission,'zone':zone,'location':'','vbucks':reward,'source':source})
    return found

def load_json(path, default):
    try: return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError): return default

def main():
    now=datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z')
    today=date.today().isoformat() # runner uses UTC
    old=load_json(MISSIONS_FILE, {'today':[],'yesterday':[],'confirmed':False,'sources':[]})
    history=load_json(HISTORY_FILE, {'days':[]})
    source_results=[]; all_missions=[]
    for name,url in SOURCES:
        entry={'name':name,'url':url,'ok':False,'summary':{},'missionCount':0,'checkedAt':now}
        try:
            text=fetch(url)
            summary=find_summary(text)
            missions=extract_missions(text,name)
            entry.update({'ok':True,'summary':summary,'missionCount':len(missions),'status':'Fetched public page'})
            all_missions.extend(missions)
        except Exception as e:
            entry['status']='Fetch failed: '+str(e)[:180]
        source_results.append(entry)
        time.sleep(0.5)
    # Deduplicate same alert discovered on several sources; keep source attribution list.
    dedup={}
    for m in all_missions:
        key=(m['mission'].lower(),m['zone'].lower(),m['vbucks'])
        if key not in dedup: dedup[key]=dict(m, sources=[m['source']])
        elif m['source'] not in dedup[key]['sources']: dedup[key]['sources'].append(m['source'])
    today_missions=list(dedup.values())
    confirmed=bool(today_missions) and any(s['ok'] for s in source_results)
    # Keep last confirmed current rows if current sources did not expose row-level details.
    if not today_missions and old.get('confirmed') and old.get('today'):
        today_missions=old['today']; confirmed=False
    record={'date':today,'checkedAt':now,'confirmed':confirmed,'missions':today_missions,
            'sourceSummaries':[{'name':s['name'],'url':s['url'],'ok':s['ok'],'summary':s['summary'],'status':s['status']} for s in source_results]}
    days=history.get('days',[])
    existing=next((i for i,d in enumerate(days) if d.get('date')==today),None)
    if existing is None: days.append(record)
    else:
        # Replace today's record only if new scrape has useful information; preserve last successful missions otherwise.
        previous=days[existing]
        if confirmed or not previous.get('confirmed'): days[existing]=record
        else:
            previous['checkedAt']=now; previous['sourceSummaries']=record['sourceSummaries']
    days=sorted(days,key=lambda d:d.get('date',''))[-400:]
    history={'updatedAt':now,'days':days}
    # Yesterday missions are only real if the archive has them. Never infer them from summary totals.
    yesterday_key=(date.today().fromordinal(date.today().toordinal()-1)).isoformat()
    yesterday_record=next((d for d in reversed(days) if d.get('date')==yesterday_key),None)
    out={'updatedAt':now,'confirmed':confirmed,'status':'confirmed' if confirmed else 'partial' if any(s['ok'] for s in source_results) else 'unavailable',
         'today':today_missions,'yesterday':(yesterday_record or {}).get('missions',[]),
         'sources':source_results,'historyDays':len(days), 'historyAvailable':bool(yesterday_record)}
    DATA.mkdir(parents=True,exist_ok=True)
    MISSIONS_FILE.write_text(json.dumps(out,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    HISTORY_FILE.write_text(json.dumps(history,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(f"Checked {len(SOURCES)} sources; {sum(s['ok'] for s in source_results)} reachable; {len(today_missions)} explicit mission rows; {len(days)} archived days.")
    if not any(s['ok'] for s in source_results): sys.exit('All public mission sources failed; stored source statuses without inventing zero missions.')

if __name__=='__main__': main()
