import json, os, sys
from datetime import datetime, timezone
from urllib.request import Request, urlopen
OUT=os.path.join(os.path.dirname(__file__),'..','public','data','missions.json')
def clean(items):
 out=[]
 for m in items if isinstance(items,list) else []:
  if not isinstance(m,dict): continue
  try: reward=int(m.get('vbucks',0))
  except (TypeError,ValueError): continue
  if reward<0: continue
  out.append({k:m.get(k) for k in ('mission','zone','location','powerLevel','expiresAt')}|{'vbucks':reward})
 return out
def main():
 url=os.environ.get('STW_DATA_URL','')
 if not url.startswith('https://'): sys.exit('Configure STW_DATA_URL with an authorized HTTPS JSON feed.')
 req=Request(url,headers={'User-Agent':'JadBakerX-STW-Tracker/1.0'})
 with urlopen(req,timeout=25) as r: d=json.load(r)
 out={'updatedAt':datetime.now(timezone.utc).isoformat(),'confirmed':d.get('confirmed') is True,'source':os.environ.get('STW_SOURCE_URL','https://vbucksdaily.com/'),'today':clean(d.get('today',d.get('missions',[]))),'yesterday':clean(d.get('yesterday',[]))}
 os.makedirs(os.path.dirname(OUT),exist_ok=True);tmp=OUT+'.tmp'
 with open(tmp,'w',encoding='utf-8') as f: json.dump(out,f,indent=2)
 os.replace(tmp,OUT)
if __name__=='__main__': main()
