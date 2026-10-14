import argparse, json, os, re, time
from collections import Counter
from datetime import datetime, timezone
from urllib.parse import urlparse
import requests
from playwright.sync_api import sync_playwright

def finding(cat, sev, title, evidence, context="", impact="", confidence="high", source="rules"):
    return {"id":"","category":cat,"severity":sev,"title":title,"evidence":evidence,"context":context,"impact":impact,"confidence":confidence,"source":source}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--url",default=os.getenv("AUDIT_URL",""))
    ap.add_argument("--output",default="results.json")
    a=ap.parse_args()
    u=a.url.strip()
    p=urlparse(u)
    if p.scheme not in ("http","https") or not p.netloc: raise SystemExit("Enter a valid public HTTP(S) URL.")
    start=time.time(); fs=[]
    d={"requested_url":u,"final_url":u,"status":None,"title":"","meta_description":"","canonical":"","h1":[],"headings":[],"links":[],"images":[],"resources":[],"text_excerpt":"","load_ms":None,"request_count":0}
    with sync_playwright() as pw:
        browser=pw.chromium.launch()
        page=browser.new_page(viewport={"width":1440,"height":1000})
        response=None
        try: response=page.goto(u,wait_until="networkidle",timeout=60000)
        except Exception as e:
            fs.append(finding("Technical","high","Page did not finish loading",str(e)[:400],"Browser navigation","Some checks may be incomplete.","medium"))
            try: page.goto(u,wait_until="domcontentloaded",timeout=25000)
            except Exception: pass
        d["final_url"]=page.url; d["status"]=response.status if response else None
        try: d["title"]=(page.title() or "").strip()
        except Exception: pass
        try:
            extracted=page.evaluate("""() => {
              const txt=e=>(e?.innerText||e?.textContent||'').trim();
              const meta=document.querySelector('meta[name="description"]'), can=document.querySelector('link[rel="canonical"]');
              return {
                meta_description:meta?.content?.trim()||'', canonical:can?.href||'',
                h1:[...document.querySelectorAll('h1')].map(txt),
                headings:[...document.querySelectorAll('h1,h2,h3,h4,h5,h6')].map(e=>({level:e.tagName,text:txt(e).slice(0,250)})),
                links:[...document.querySelectorAll('a[href]')].map(a=>({text:txt(a).slice(0,200),href:a.href,area:a.closest('header')?'Header':a.closest('nav')?'Navigation':a.closest('footer')?'Footer':'Main content',element:a.querySelector('img')?'image link':'text link',imageAlt:a.querySelector('img')?.getAttribute('alt')??null})),
                images:[...document.images].map(i=>({src:i.currentSrc||i.src,alt:i.getAttribute('alt'),width:i.naturalWidth||i.width,height:i.naturalHeight||i.height,visible:!!(i.getClientRects().length&&getComputedStyle(i).display!=='none'&&getComputedStyle(i).visibility!=='hidden'),area:i.closest('header')?'Header':i.closest('footer')?'Footer':'Main content'})),
                resources:performance.getEntriesByType('resource').map(r=>({name:r.name,type:r.initiatorType,duration:Math.round(r.duration),transferSize:r.transferSize||0})),
                text_excerpt:txt(document.body).slice(0,16000)
              };
            }""")
            d.update(extracted)
        except Exception as e: fs.append(finding("Technical","medium","Could not extract page structure",str(e)[:300],"DOM extraction","Some checks may be incomplete.","medium"))
        browser.close()
    d["load_ms"]=round((time.time()-start)*1000); d["request_count"]=len(d["resources"])
    if d["status"] and d["status"]>=400: fs.append(finding("Technical","critical","Page returned an HTTP error",f"HTTP status: {d['status']}",d["final_url"],"The page may not be accessible to visitors or crawlers."))
    if not d["title"]: fs.append(finding("SEO","high","Missing page title","No non-empty document title was detected.","HTML <title>","Search results and browser tabs may lack a useful title."))
    if not d["meta_description"]: fs.append(finding("SEO","medium","Missing meta description","No non-empty meta description was detected.","HTML head","Search engines may generate their own snippet."))
    if not d["h1"]: fs.append(finding("SEO","high","No H1 heading detected","The page contains zero H1 elements.","Heading structure","The page lacks a primary heading in its HTML structure."))
    elif len(d["h1"])>1: fs.append(finding("SEO","medium","Multiple H1 headings detected",json.dumps(d["h1"],ensure_ascii=False),"Heading structure","Multiple H1s may be intentional; review in context.","medium"))
    if not d["canonical"]: fs.append(finding("SEO","low","Canonical link not detected","No link[rel=canonical] was detected.","HTML head","This may be intentional.","low"))
    else:
        ch=urlparse(d["canonical"]).netloc.lower(); fh=urlparse(d["final_url"]).netloc.lower()
        if ch and fh and ch!=fh: fs.append(finding("SEO","medium","Canonical points to a different host",d["canonical"],"HTML link[rel=canonical]","Confirm whether this is intentional.","medium"))
    for im in d["images"]:
        if im["visible"] and im["alt"] is None: fs.append(finding("Accessibility","medium","Image has no alt attribute",im["src"],im["area"],"Assistive technologies may lack a text alternative."))
        elif im["visible"] and im["alt"]=="": fs.append(finding("Accessibility","low","Image has empty alt text",im["src"],im["area"],"Empty alt can be correct for decorative images; verify purpose.","low"))
    for pattern,label in [(r"submitted by .{0,100} on .{0,80}","Possible editorial metadata in page text"),(r"components library","Possible internal component-library text"),(r"node background color","Possible CMS/design configuration text"),(r"lorem ipsum","Placeholder text detected"),(r"todo:|fixme:","Possible internal note detected")]:
        m=re.search(pattern,d["text_excerpt"],re.I)
        if m: fs.append(finding("Content","medium",label,m.group(0),"Extracted page text","May be intentional; verify whether public visitors should see it.","medium"))
    seen=set(); links=[]
    for x in d["links"]:
        href=x.get("href","")
        if urlparse(href).scheme in ("http","https") and href not in seen: seen.add(href); links.append(x)
        if len(links)>=60: break
    s=requests.Session(); s.headers["User-Agent"]="PageAudit/0.1"
    for x in links:
        try:
            r=s.head(x["href"],allow_redirects=True,timeout=8)
            if r.status_code in (403,405): r=s.get(x["href"],allow_redirects=True,timeout=8,stream=True)
            label=x["text"] or x["imageAlt"] or "(unlabelled)"
            ctx=f'{x["area"]} · {x["element"]} · {label}'
            if r.status_code in (404,410): fs.append(finding("Links","high","Link points to a missing page",f'{x["href"]} returned HTTP {r.status_code}.',ctx,"Visitors may reach a missing destination."))
            elif r.status_code in (401,403,429) or r.status_code>=500: fs.append(finding("Links","medium","Link could not be reliably verified",f'{x["href"]} returned HTTP {r.status_code}.',ctx,"Access controls, rate limits or server issues may affect the result.","medium"))
            elif r.status_code>=400: fs.append(finding("Links","medium","Link returned an HTTP error",f'{x["href"]} returned HTTP {r.status_code}.',ctx,"Confirm whether the response is expected.","medium"))
        except Exception as e: fs.append(finding("Links","low","Link check failed",f'{x["href"]} — {str(e)[:150]}',x["area"],"Network behavior prevented verification.","low"))
    order={"critical":0,"high":1,"medium":2,"low":3}; fs.sort(key=lambda x:(order.get(x["severity"],9),x["category"],x["title"]))
    for i,x in enumerate(fs,1): x["id"]=f"PA-{i:03d}"
    report={"schema_version":1,"generated_at":datetime.now(timezone.utc).isoformat(),"page":d,"summary":{"total_findings":len(fs),"by_severity":dict(Counter(x["severity"] for x in fs)),"by_category":dict(Counter(x["category"] for x in fs))},"findings":fs,"ai_analysis":{"enabled":False,"status":"not configured"},"notes":["Findings require human review, especially contextual findings.","Checks up to 60 unique link destinations.","AI analysis is not enabled in this prototype."]}
    with open(a.output,"w",encoding="utf-8") as f: json.dump(report,f,ensure_ascii=False,indent=2)
    print(f"Saved {len(fs)} findings to {a.output}")
if __name__=="__main__": main()
