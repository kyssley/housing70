"""Python 3 stdlib only. Refresh official NBS releases and rebuild offline index.html.
Run: python update_data.py ; existing raw pages are cached; --refresh re-downloads.
"""
import concurrent.futures,csv,datetime,hashlib,html,json,re,sys,urllib.request
from pathlib import Path
from urllib.parse import urljoin
ROOT=Path(__file__).resolve().parent
RAW=ROOT/'raw'; RAW.mkdir(exist_ok=True)
def get(url):
 req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
 return urllib.request.urlopen(req,timeout=45).read().decode('utf-8-sig')
def clean(s): return re.sub(r'\s+','',html.unescape(re.sub('<[^>]+>','',s)))
def discover():
 sources={}
 for i in range(100):
  url='https://www.stats.gov.cn/sj/zxfb/'+('' if i==0 else f'index_{i}.html')
  try: t=get(url)
  except urllib.error.HTTPError as e:
   if e.code==404: break
   raise
  for href,body in re.findall(r'<a\b[^>]*href=[\"\x27]([^\"\x27]+)[\"\x27][^>]*>(.*?)</a>',t,re.S):
   title=clean(body)
   if re.fullmatch(r'\d{4}年\d+月份70个大中城市商品住宅销售价格变动情况',title):
    sources[title]={'title':title,'url':urljoin(url,href)}
 return list(sources.values())
def parse(source):
 y,m=map(int,re.search(r'(\d{4})年(\d+)月',source['title']).groups())
 month=f'{y:04}-{m:02}'; path=RAW/(month+'.html')
 if not path.exists() or '--refresh' in sys.argv: path.write_text(get(source['url']),encoding='utf-8')
 t=path.read_text(encoding='utf-8')
 title=clean(re.search(r'<title>(.*?)</title>',t,re.S).group(1))
 assert source['title'] in title,(month,title)
 tables=re.findall(r'<table\b.*?</table>',t,re.S|re.I)
 records=[]
 for k,table in zip(['new','resale'],tables[:2]):
  found={}
  for row in re.findall(r'<tr\b.*?</tr>',table,re.S|re.I):
   cells=[clean(s) for s in re.findall(r'<t[dh]\b[^>]*>(.*?)</t[dh]>',row,re.S|re.I)]
   for j in range(len(cells)-2):
    if re.fullmatch(r'[\u4e00-\u9fff]{2,5}',cells[j]) and re.fullmatch(r'\d+\.\d+',cells[j+1]) and re.fullmatch(r'\d+\.\d+',cells[j+2]):
     city=cells[j]; mom=float(cells[j+1]); yoy=float(cells[j+2])
     assert 70<mom<130 and 50<yoy<160,(month,city,mom,yoy)
     assert city not in found,(month,city)
     found[city]={'month':month,'city':city,'type':k,'mom':mom,'yoy':yoy}
  assert len(found)==70,(month,k,len(found))
  records.extend(found.values())
 pub=re.search(r'name="PubDate" content="([^"]+)"',t)
 return records,dict(source,month=month,published=pub.group(1) if pub else None,sha256=hashlib.sha256(t.encode()).hexdigest())
def main():
 seed=ROOT/'sources.json'
 sources=json.loads(seed.read_text(encoding='utf-8')) if '--cached-sources' in sys.argv else discover()
 results=list(concurrent.futures.ThreadPoolExecutor(max_workers=4).map(parse,sources))
 rows=[r for rs,_ in results for r in rs]; rows.sort(key=lambda r:(r['month'],r['city'],r['type']))
 src=sorted([s for _,s in results],key=lambda s:s['month'])
 months=[s['month'] for s in src]
 assert len(set(months))==len(months)
 nums=[int(m[:4])*12+int(m[5:]) for m in months]
 assert all(b-a==1 for a,b in zip(nums,nums[1:])), 'Missing months'
 cities=set(r['city'] for r in rows)
 assert len(cities)==70 and len(rows)==len(months)*140
 data={'checkedAt':datetime.date.today().isoformat(),'source':'国家统计局','sources':src,'records':rows}
 seed.write_text(json.dumps(src,ensure_ascii=False,indent=2),encoding='utf-8')
 encoded=json.dumps(data,ensure_ascii=False,separators=(',',':'))
 (ROOT/'data.json').write_text(encoded,encoding='utf-8')
 with (ROOT/'housing70.csv').open('w',encoding='utf-8-sig',newline='') as f:
  writer=csv.DictWriter(f,fieldnames=['month','city','type','mom','yoy']);writer.writeheader();writer.writerows(rows)
 template=(ROOT/'app.template.html').read_text(encoding='utf-8')
 (ROOT/'index.html').write_text(template.replace('__DATA__',encoded.replace('</','<\\/')),encoding='utf-8')
 print(json.dumps({'months':len(months),'range':[months[0],months[-1]],'cities':len(cities),'rows':len(rows),'status':'validated'},ensure_ascii=False))
if __name__=='__main__': main()
