import urllib.request
import re
import os
from html import unescape
from datetime import datetime, timedelta, UTC
from urllib.parse import urljoin
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

BASE_URL = "https://www.conservatoriocagliari.it"
FEED_URL = f"{BASE_URL}/comunicazioni/comunicazioni-agli-studenti"
MAX_PAGES = 4
AUTHOR_NAME = "Conservatorio di Cagliari"
FEED_FILE = "feed_cons.xml"

NAMESPACE = {'atom': 'http://www.w3.org/2005/Atom'}
ET.register_namespace('', 'http://www.w3.org/2005/Atom')


ITALIAN_MONTHS = {
    "gennaio": 1,
    "febbraio": 2,
    "marzo": 3,
    "aprile": 4,
    "maggio": 5,
    "giugno": 6,
    "luglio": 7,
    "agosto": 8,
    "settembre": 9,
    "ottobre": 10,
    "novembre": 11,
    "dicembre": 12
}

def fetch_page(url):
    req = urllib.request.Request(
        url, 
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
        }
    )
    with urllib.request.urlopen(req) as response:
        return response.read().decode("utf-8")


def extract_news_items(html):
    items = []
    entries = re.split(r'<div class="news-list-element[^"]*">', html)[1:]

    for entry in entries:
        title_match = re.search(r'<h4 class="news-title">(.+?)</h4>', entry, re.DOTALL)
        title = unescape(title_match.group(1).strip()) if title_match else "Senza titolo"

        link_match = re.search(r'<a href="([^"]+)"', entry)
        link = urljoin(BASE_URL, link_match.group(1)) if link_match else BASE_URL

        date_match = re.search(r'<div class="news-date">[^<]*News del ([^<]+)</div>', entry)
        if date_match:
            raw_date = date_match.group(1).strip()

            date_regex = re.match(r'(\d{1,2}) (\w+) (\d{4})', raw_date.lower())
            if date_regex:
                day = int(date_regex.group(1))
                month_name = date_regex.group(2)
                year = int(date_regex.group(3))

                month = ITALIAN_MONTHS.get(month_name)
                if month:
                    pub_date = datetime(year, month, day, tzinfo=UTC)
                else:
                    pub_date = datetime.now(UTC)
            else:
                pub_date = datetime.now(UTC)
        else:
            pub_date = datetime.now(UTC)

        iso_date = pub_date.strftime("%Y-%m-%dT%H:%M:%S+00:00")

        items.append({
            "title": title,
            "link": link,
            "date": iso_date,
            "dt_obj": pub_date
        })

    return items


def scrape_news():
    all_items = []

    for page in range(1, MAX_PAGES + 1):
        print(f"Scraping page {page}")
        url = f"{FEED_URL}?year=_&page={page}&lang=it"
        html = fetch_page(url)
        page_items = extract_news_items(html)
        all_items.extend(page_items)

    return all_items


def load_existing_entries(filepath):
    if not os.path.exists(filepath):
        return []

    tree = ET.parse(filepath)
    root = tree.getroot()
    entries = []

    for entry in root.findall("atom:entry", NAMESPACE):
        title = entry.find("atom:title", NAMESPACE).text
        link = entry.find("atom:link", NAMESPACE).attrib.get("href")
        published = entry.find("atom:published", NAMESPACE).text
        dt = datetime.strptime(published, "%Y-%m-%dT%H:%M:%S+00:00")
        dt = dt.replace(tzinfo=UTC)
        entries.append({
            "title": title,
            "link": link,
            "date": published,
            "dt_obj": dt
        })

    return entries


def deduplicate_and_filter(items):
    now = datetime.now(UTC)
    six_months_ago = now - timedelta(days=180)

    seen_links = set()
    deduped = []

    for item in sorted(items, key=lambda x: x["dt_obj"], reverse=True):
        if item["link"] in seen_links:
            continue
        if item["dt_obj"] < six_months_ago:
            continue
        seen_links.add(item["link"])
        deduped.append(item)

    return deduped


def generate_atom_feed(items, output_path=FEED_FILE):
    updated = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    feed_id = f"{BASE_URL}/feed.xml"

    feed = ET.Element("feed", xmlns="http://www.w3.org/2005/Atom")

    ET.SubElement(feed, "generator", attrib={
        "uri": "",
        "version": "1.0"
    }).text = "Python Script"

    ET.SubElement(feed, "link", href=feed_id, rel="self", type="application/atom+xml")
    ET.SubElement(feed, "link", href=BASE_URL, rel="alternate", type="text/html")
    ET.SubElement(feed, "updated").text = updated
    ET.SubElement(feed, "id").text = feed_id
    ET.SubElement(feed, "title", type="html").text = "Comunicazione agli studenti - Conservatorio Cagliari"
    ET.SubElement(feed, "subtitle").text = "Ultime comunicazioni agli studenti"

    for item in items:
        entry = ET.SubElement(feed, "entry")
        ET.SubElement(entry, "title", type="html").text = item["title"]
        ET.SubElement(entry, "link", href=item["link"], rel="alternate", type="text/html", title=item["title"])
        ET.SubElement(entry, "id").text = item["link"]
        ET.SubElement(entry, "published").text = item["date"]
        ET.SubElement(entry, "updated").text = item["date"]
        ET.SubElement(entry, "content", type="html").text = f"<p><a href={item["link"]}>{item["link"]}</a></p>" 
        author = ET.SubElement(entry, "author")
        ET.SubElement(author, "name").text = AUTHOR_NAME
        ET.SubElement(entry, "summary", type="html").text = item["title"]

    tree = ET.ElementTree(feed)
    tree.write(output_path, encoding="utf-8", xml_declaration=True)
    print(f"Atom feed written to {output_path}")


if __name__ == "__main__":
    print("▶ Scraping new items...")
    scraped_items = scrape_news()

    print("📁 Loading existing feed entries...")
    existing_items = load_existing_entries(FEED_FILE)

    print("📌 Merging & filtering entries...")
    all_items = scraped_items + existing_items
    filtered_items = deduplicate_and_filter(all_items)

    print("📝 Generating Atom feed...")
    generate_atom_feed(filtered_items)
