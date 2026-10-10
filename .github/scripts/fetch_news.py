#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
رصد | جمع‌آوری خودکار اخبار + ترجمه خودکار به فارسی
"""
import json
import re
import sys
import time
import urllib.parse
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
    "military": ["حمله", "موشک", "پهپاد", "جنگنده", "ارتش", "نظامی", "سپاه", "بمب", "پدافند",
                 "اف-۳۵", "اف-۲۲", "f-35", "f-22", "b-2", "b-1", "ناو", "پرواز", "رادار",
                 "attack", "missile", "drone", "jet", "military", "strike", "navy"],
    "politics": ["ترامپ", "نتانیاهو", "مذاکره", "توافق", "دولت", "وزیر", "رئیس‌جمهور", "پارلمان",
                 "تحریم", "سیاست", "دیپلمات", "trump", "netanyahu", "deal", "talks", "sanction"],
    "economy": ["تورم", "دلار", "یورو", "قیمت", "بانک", "بورس", "اقتصاد", "نفت", "طلا", "ارز",
                "inflation", "dollar", "economy", "oil", "bank"],
    "social": ["مردم", "اعتراض", "تجمع", "کارگر", "معلمان", "بازنشسته", "گزارش مردمی",
               "protest", "people", "worker"],
    "analysis": ["تحلیل", "بررسی", "چرا", "گزارش ویژه", "کارشناس", "analysis", "explainer", "opinion"],
}

TAG_KEYWORDS = {
    "ترامپ": ["ترامپ", "trump"],
    "نتانیاهو": ["نتانیاهو", "netanyahu"],
    "مذاکره": ["مذاکره", "توافق", "talks", "deal", "negotiat"],
    "فلایت رادار": ["پرواز", "جنگنده", "رادار", "فلایت", "flight"],
    "F-35": ["f-35", "اف-۳۵", "اف ۳۵"],
    "F-22": ["f-22", "اف-۲۲", "اف ۲۲"],
    "ناو آمریکا": ["ناو", "ناوگان", "aircraft carrier", "carrier"],
    "تصاویر ماهواره‌ای": ["ماهواره", "satellite", "imagery"],
    "NetBlocks": ["netblocks", "اینترنت", "قطع اینترنت", "internet"],
    "تحلیلگران": ["تحلیل", "کارشناس", "analyst"],
    "گزارش مردمی": ["گزارش مردمی", "شاهد", "ویدیو", "witness"],
}

# ---------------- ترجمه ----------------
TRANSLATE_CACHE = {}

def translate_to_fa(text):
    """ترجمه متن انگلیسی به فارسی با MyMemory (رایگان)"""
    if not text or len(text.strip()) < 3:
        return text
    # اگه متن از قبل فارسی بود، ترجمه نکن
    if re.search(r'[\u0600-\u06FF]', text):
        return text
    key = text[:500]
    if key in TRANSLATE_CACHE:
        return TRANSLATE_CACHE[key]
    try:
        # MyMemory محدودیت 500 کاراکتر داره
        chunk = text[:500]
        url = "https://api.mymemory.translated.net/get?q=" + urllib.parse.quote(chunk) + "&langpair=en|fa"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode('utf-8'))
        translated = data.get("responseData", {}).get("translatedText", "")
        if translated and not translated.startswith("MYMEMORY"):
            TRANSLATE_CACHE[key] = translated
            time.sleep(0.5)  # محدودیت نرخ
            return translated
    except Exception as e:
        print(f"    ترجمه ناموفق: {e}", file=sys.stderr)
    return text

# ---------------- ابزار ----------------
def fetch_url(url, timeout=20):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (RasadBot/1.0)",
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except Exception as e:
        print(f"  خطا در دریافت {url}: {e}", file=sys.stderr)
        return None

def strip_html(text):
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&[a-z]+;", " ", text)
    return re.sub(r"\s+", " ", text).strip()

def parse_feed(raw, source_name, default_lang):
    items = []
    try:
        root = ET.fromstring(raw)
    except Exception as e:
        print(f"  خطای XML در {source_name}: {e}", file=sys.stderr)
        return items

    channel_items = root.findall(".//item")
    if not channel_items:
        ns = {"a": "http://www.w3.org/2005/Atom"}
        channel_items = root.findall(".//a:entry", ns)

    for it in channel_items:
        try:
            title = it.findtext("title") or ""
            if not title:
                ns = {"a": "http://www.w3.org/2005/Atom"}
                t = it.find("a:title", ns)
                title = t.text if t is not None else ""

            link = it.findtext("link") or ""
            if not link:
                ns = {"a": "http://www.w3.org/2005/Atom"}
                l = it.find("a:link", ns)
                if l is not None:
                    link = l.get("href", "")

            # تلاش برای گرفتن محتوای کامل
            desc = ""
            for tag in ["description", "{http://purl.org/rss/1.0/modules/content/}encoded", "content:encoded"]:
                d = it.findtext(tag)
                if d and len(d) > len(desc):
                    desc = d
            if not desc:
                ns = {"a": "http://www.w3.org/2005/Atom"}
                d = it.find("a:summary", ns)
                desc = d.text if d is not None else ""
            if not desc:
                ns = {"a": "http://www.w3.org/2005/Atom"}
                d = it.find("a:content", ns)
                desc = d.text if d is not None else ""

            pub = (it.findtext("pubDate") or it.findtext("{http://purl.org/dc/elements/1.1/}date")
                   or it.findtext("{http://www.w3.org/2005/Atom}updated") or "")

            title = strip_html(title)
            desc = strip_html(desc)  # بدون محدودیت طول
            if not title:
                continue

            items.append({
                "title": title,
                "link": link.strip(),
                "summary": desc,
                "published_raw": pub,
                "source": source_name,
                "lang": default_lang,
            })
        except Exception:
            continue
    return items

def parse_date(raw):
    if not raw:
        return datetime.now(timezone.utc)
    formats = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S GMT",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S",
    ]
    for f in formats:
        try:
            dt = datetime.strptime(raw, f)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            continue
    return datetime.now(timezone.utc)

def to_tehran(dt):
    return dt.astimezone(timezone(timedelta(hours=3, minutes=30)))

def fa_datetime(dt):
    try:
        import jdatetime
        j = jdatetime.datetime.fromgregorian(datetime=to_tehran(dt))
        return j.strftime("%Y/%m/%d - %H:%M")
    except ImportError:
        return to_tehran(dt).strftime("%Y/%m/%d - %H:%M")

def detect_category(text):
    tl = text.lower()
    for cat, words in CATEGORY_KEYWORDS.items():
        for w in words:
            if w.lower() in tl:
                return cat
    return "other"

def detect_tags(text):
    tl = text.lower()
    tags = []
    for tag, words in TAG_KEYWORDS.items():
        for w in words:
            if w.lower() in tl:
                tags.append(tag)
                break
    return tags

def is_urgent(title, tags):
    urgent_words = ["f-35", "اف-۳۵", "f-22", "اف-۲۲", "b-2", "b-1", "ناو", "موشک", "حمله"]
    tl = title.lower()
    if any(w in tl for w in urgent_words):
        return True
    return any(t in ["F-35", "F-22", "ناو آمریکا"] for t in tags)

def main():
    print("شروع جمع‌آوری اخبار")
    all_items = []

    for feed in FEEDS:
        print(f"-> {feed['source']}: {feed['url'][:70]}...")
        raw = fetch_url(feed["url"])
        if not raw:
            continue
        items = parse_feed(raw, feed["source"], feed["lang"])
        print(f"   {len(items)} خبر")
        all_items.extend(items)

    # حذف تکراری‌ها
    seen = set()
    unique = []
    for it in all_items:
        key = it["title"][:60].strip()
        if key in seen:
            continue
        seen.add(key)
        unique.append(it)

    print(f"\nمجموع یکتا: {len(unique)}")
    print("شروع ترجمه (ممکنه چند دقیقه طول بکشه)...")

    output_items = []
    for idx, it in enumerate(unique):
        dt = parse_date(it["published_raw"])
        is_en = it["lang"] == "en"
        
        # ترجمه فقط برای خبرهای انگلیسی
        if is_en:
            title_fa = translate_to_fa(it["title"])
            summary_fa = translate_to_fa(it["summary"]) if it["summary"] else ""
        else:
            title_fa = it["title"]
            summary_fa = it["summary"]
        
        if idx % 20 == 0:
            print(f"   ترجمه {idx}/{len(unique)}...")

        full_text = f"{title_fa} {summary_fa} {it['title']} {it['summary']}"
        tags = detect_tags(full_text)
        category = detect_category(full_text)
        
        # خلاصه بلندتر: تا 1200 کاراکتر
        long_summary = summary_fa if summary_fa else title_fa
        if len(long_summary) < 100 and it["summary"]:
            long_summary = summary_fa + "\n\n" + it["summary"]
        
        output_items.append({
            "title": title_fa,
            "title_original": it["title"] if is_en else "",
            "link": it["link"],
            "summary": long_summary[:1500],
            "summary_original": it["summary"][:1500] if is_en else "",
            "source": it["source"],
            "category": category,
            "tags": tags,
            "urgent": is_urgent(title_fa + " " + it["title"], tags),
            "published": to_tehran(dt).isoformat(),
            "published_fa": fa_datetime(dt),
            "translated": is_en,
            "verified_source": True,
        })

    output_items.sort(key=lambda x: x["published"], reverse=True)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_at_fa": fa_datetime(datetime.now(timezone.utc)),
        "count": len(output_items),
        "items": output_items,
    }

    out_path = Path("news.json")
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{len(output_items)} خبر ذخیره شد در {out_path}")

if __name__ == "__main__":
    main()
