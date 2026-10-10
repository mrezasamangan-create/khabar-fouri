#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""رصد | جمع‌آوری خودکار اخبار + ترجمه Google"""
import json, re, sys, time, urllib.parse
from datetime import datetime, timezone, timedelta
from pathlib import Path
import urllib.request
from xml.etree import ElementTree as ET

FEEDS = [
    {"url": "https://moxie.foxnews.com/google-publisher/world.xml", "source": "Fox News", "lang": "en"},
    {"url": "https://moxie.foxnews.com/google-publisher/politics.xml", "source": "Fox News", "lang": "en"},
    {"url": "https://feeds.bbci.co.uk/persian/rss.xml", "source": "BBC Persian", "lang": "fa"},
    {"url": "https://www.aljazeera.com/xml/rss/all.xml", "source": "Al Jazeera", "lang": "en"},
    {"url": "https://news.google.com/rss/search?q=Israel+Iran&hl=en-US&gl=US&ceid=US:en", "source": "Google News", "lang": "en"},
    {"url": "https://news.google.com/rss/search?q=Iran+Middle+East&hl=en-US&gl=US&ceid=US:en", "source": "Google News", "lang": "en"},
    {"url": "https://news.google.com/rss/search?q=Trump+Netanyahu&hl=en-US&gl=US&ceid=US:en", "source": "Google News", "lang": "en"},
    {"url": "https://www.iranintl.com/feed", "source": "Iran International", "lang": "fa"},
]

CATEGORY_KEYWORDS = {
    "military": ["حمله","موشک","پهپاد","جنگنده","ارتش","نظامی","سپاه","بمب","پدافند","اف-۳۵","اف-۲۲","f-35","f-22","b-2","b-1","ناو","پرواز","رادار","attack","missile","drone","jet","military","strike","navy"],
    "politics": ["ترامپ","نتانیاهو","مذاکره","توافق","دولت","وزیر","رئیس‌جمهور","پارلمان","تحریم","سیاست","دیپلمات","trump","netanyahu","deal","talks","sanction"],
    "economy": ["تورم","دلار","یورو","قیمت","بانک","بورس","اقتصاد","نفت","طلا","ارز","inflation","dollar","economy","oil","bank"],
    "social": ["مردم","اعتراض","تجمع","کارگر","معلمان","بازنشسته","protest","people","worker"],
    "analysis": ["تحلیل","بررسی","چرا","گزارش ویژه","کارشناس","analysis","explainer","opinion"],
}

TAG_KEYWORDS = {
    "ترامپ": ["ترامپ","trump"], "نتانیاهو": ["نتانیاهو","netanyahu"],
    "مذاکره": ["مذاکره","توافق","talks","deal","negotiat"],
    "فلایت رادار": ["پرواز","جنگنده","رادار","فلایت","flight"],
    "F-35": ["f-35","اف-۳۵","اف ۳۵"], "F-22": ["f-22","اف-۲۲","اف ۲۲"],
    "ناو آمریکا": ["ناو","ناوگان","aircraft carrier","carrier"],
    "تصاویر ماهواره‌ای": ["ماهواره","satellite","imagery"],
    "NetBlocks": ["netblocks","اینترنت","قطع اینترنت","internet"],
    "تحلیلگران": ["تحلیل","کارشناس","analyst"],
    "گزارش مردمی": ["گزارش مردمی","شاهد","ویدیو","witness"],
}

CACHE = {}

def translate_google(text):
    if not text or len(text.strip()) < 2: return text
    if re.search(r'[\u0600-\u06FF]', text): return text
    key = text[:400]
    if key in CACHE: return CACHE[key]
    try:
        params = urllib.parse.urlencode({'client':'gtx','sl':'en','tl':'fa','dt':'t','q':text[:1800]})
        url = f"https://translate.googleapis.com/translate_a/single?{params}"
        req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode('utf-8'))
        parts = data[0] if data and data[0] else []
        translated = "".join(p[0] for p in parts if p and p[0])
        if translated:
            CACHE[key] = translated
            time.sleep(0.2)
            return translated
    except Exception as e:
        print(f"    ترجمه ناموفق: {e}", file=sys.stderr)
    return text

def fetch_url(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0 (RasadBot/1.0)"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r: return r.read()
    except Exception as e:
        print(f"  خطا: {e}", file=sys.stderr); return None

def strip_html(t):
    if not t: return ""
    t = re.sub(r"<[^>]+>", " ", t)
    t = re.sub(r"&[a-z]+;", " ", t)
    return re.sub(r"\s+", " ", t).strip()

def parse_feed(raw, src, lang):
    items = []
    try: root = ET.fromstring(raw)
    except: return items
    ci = root.findall(".//item")
    if not ci:
        ns = {"a":"http://www.w3.org/2005/Atom"}
        ci = root.findall(".//a:entry", ns)
    for it in ci:
        try:
            title = it.findtext("title") or ""
            if not title:
                ns = {"a":"http://www.w3.org/2005/Atom"}
                t = it.find("a:title", ns); title = t.text if t is not None else ""
            link = it.findtext("link") or ""
            if not link:
                ns = {"a":"http://www.w3.org/2005/Atom"}
                l = it.find("a:link", ns)
                if l is not None: link = l.get("href","")
            desc = ""
            for tag in ["description","{http://purl.org/rss/1.0/modules/content/}encoded"]:
                d = it.findtext(tag)
                if d and len(d) > len(desc): desc = d
            pub = it.findtext("pubDate") or ""
            title = strip_html(title); desc = strip_html(desc)
            if not title: continue
            items.append({"title":title,"link":link.strip(),"summary":desc,"published_raw":pub,"source":src,"lang":lang})
        except: continue
    return items

def parse_date(raw):
    if not raw: return datetime.now(timezone.utc)
    for f in ["%a, %d %b %Y %H:%M:%S %z","%a, %d %b %Y %H:%M:%S GMT","%Y-%m-%dT%H:%M:%S%z","%Y-%m-%dT%H:%M:%SZ"]:
        try:
            dt = datetime.strptime(raw, f)
            if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except: continue
    return datetime.now(timezone.utc)

def to_tehran(dt): return dt.astimezone(timezone(timedelta(hours=3, minutes=30)))

def fa_dt(dt):
    try:
        import jdatetime
        return jdatetime.datetime.fromgregorian(datetime=to_tehran(dt)).strftime("%Y/%m/%d - %H:%M")
    except: return to_tehran(dt).strftime("%Y/%m/%d - %H:%M")

def detect_cat(text):
    tl = text.lower()
    for cat, ws in CATEGORY_KEYWORDS.items():
        for w in ws:
            if w.lower() in tl: return cat
    return "other"

def detect_tags(text):
    tl = text.lower(); tags = []
    for tag, ws in TAG_KEYWORDS.items():
        for w in ws:
            if w.lower() in tl: tags.append(tag); break
    return tags

def is_urgent(t, tags):
    uw = ["f-35","اف-۳۵","f-22","اف-۲۲","b-2","b-1","ناو","موشک","حمله"]
    tl = t.lower()
    return any(w in tl for w in uw) or any(x in ["F-35","F-22","ناو آمریکا"] for x in tags)

def main():
    print("شروع جمع‌آوری اخبار")
    all_items = []
    for f in FEEDS:
        print(f"-> {f['source']}")
        raw = fetch_url(f["url"])
        if not raw: continue
        items = parse_feed(raw, f["source"], f["lang"])
        print(f"   {len(items)} خبر")
        all_items.extend(items)
    seen = set(); unique = []
    for it in all_items:
        k = it["title"][:60].strip()
        if k in seen: continue
        seen.add(k); unique.append(it)
    print(f"\nمجموع: {len(unique)}")
    out = []
    for idx, it in enumerate(unique):
        dt = parse_date(it["published_raw"])
        is_en = it["lang"] == "en"
        if is_en:
            title_fa = translate_google(it["title"])
            sum_src = it["summary"][:800] if it["summary"] else ""
            sum_fa = translate_google(sum_src) if sum_src else title_fa
        else:
            title_fa = it["title"]; sum_fa = it["summary"]
        if idx % 20 == 0: print(f"   {idx}/{len(unique)}...")
        full = f"{title_fa} {sum_fa}"
        tags = detect_tags(full + " " + it["title"])
        cat = detect_cat(full + " " + it["title"])
        out.append({
            "title": title_fa, "title_original": it["title"] if is_en else "",
            "link": it["link"], "summary": sum_fa[:1500],
            "summary_original": it["summary"][:1500] if is_en else "",
            "source": it["source"], "category": cat, "tags": tags,
            "urgent": is_urgent(title_fa + " " + it["title"], tags),
            "published": to_tehran(dt).isoformat(),
            "published_fa": fa_dt(dt), "translated": is_en, "verified_source": True,
        })
    out.sort(key=lambda x: x["published"], reverse=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_at_fa": fa_dt(datetime.now(timezone.utc)),
        "count": len(out), "items": out,
    }
    Path("news.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{len(out)} خبر ذخیره شد")

if __name__ == "__main__":
    main()
