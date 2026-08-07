"""Temp helper: search arXiv for correct IDs (deleted after use)."""
import re
import urllib.parse
import urllib.request


def search(q):
    url = "http://export.arxiv.org/api/query?" + urllib.parse.urlencode(
        {"search_query": q, "max_results": 3})
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    xml = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
    for e in re.findall(r"<entry>(.*?)</entry>", xml, re.S):
        aid = re.search(r"<id>http://arxiv.org/abs/([^v<]+)", e).group(1)
        title = re.sub(r"\s+", " ", re.search(r"<title>(.*?)</title>", e, re.S).group(1)).strip()
        print(aid, "|", title[:110])
    print("---")


import json

def crossref(q, rows=5):
    url = "https://api.crossref.org/works?" + urllib.parse.urlencode(
        {"query.bibliographic": q, "rows": rows, "select": "title,author,DOI,issued,published-print"})
    req = urllib.request.Request(url, headers={"User-Agent": "research/1.0 (mailto:test@example.com)"})
    data = json.loads(urllib.request.urlopen(req, timeout=30).read().decode("utf-8"))
    for it in data.get("message", {}).get("items", []):
        title = (it.get("title") or ["?"])[0]
        doi = it.get("DOI", "?")
        year = (it.get("issued", {}).get("date-parts") or [[None]])[0][0]
        print(doi, "|", year, "|", title[:110])
    print("---")


search('ti:"Multi-Agent Systems" AND abs:"large language model" AND abs:survey')
search('ti:"Challenges and Open Problems" AND all:multi-agent')
search('ti:"multi-agent" AND abs:"challenges and open problems" AND all:LLM')
