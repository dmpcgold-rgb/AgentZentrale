#!/usr/bin/env python3
"""Read-only, unauthenticated analysis of publicly served WESTbahn JS assets.

No browser profile, cookies, account access, POST, purchase, or checkout
navigation. Reports bounded static source excerpts for endpoint semantics.
"""
import html
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

HOME = "https://westbahn.at/ticketshop/ticket-buchen/"
HOSTS = {"westbahn.at", "www.westbahn.at"}
TARGETS = ("payment-init", "basket/approve", "payment/payment-methods")
MAX_ASSETS = 35
MAX_BYTES = 8 * 1024 * 1024

def safe_url(url):
    parsed = urllib.parse.urlsplit(url)
    return (parsed.scheme == "https" and parsed.hostname in HOSTS
            and parsed.port in (None, 443) and not parsed.username
            and not parsed.password and not parsed.query and not parsed.fragment)

class SameOriginOnly(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        if not safe_url(newurl):
            raise ValueError("external_redirect_not_allowed")
        return super().redirect_request(request, fp, code, msg, headers, newurl)

opener = urllib.request.build_opener(SameOriginOnly)

def get_public(url):
    if not safe_url(url):
        raise ValueError("url_not_allowlisted")
    request = urllib.request.Request(url, method="GET",
        headers={"User-Agent": "WESTbahn-public-script-readonly-diagnostic/1.0",
                 "Accept": "text/html, application/javascript, text/javascript, */*"})
    with opener.open(request, timeout=12) as response:
        final = response.geturl()
        if not safe_url(final):
            raise ValueError("response_url_not_allowlisted")
        raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError("public_asset_too_large")
        return raw.decode("utf-8", errors="replace")

def script_urls(markup):
    sources = re.findall(
        r"<script\b[^>]*?\bsrc\s*=\s*['\\"]([^'\\"]+)['\\"]",
        markup, flags=re.IGNORECASE)
    # Some bundlers also preload scripts before inserting a script tag.
    sources += re.findall(
        r"<link\b[^>]*?\bhref\s*=\s*['\\"]([^'\\"]+\.js(?:[^'\\"]*)?)['\\"]",
        markup, flags=re.IGNORECASE)
    urls = []
    for source in sources:
        target = urllib.parse.urljoin(HOME, html.unescape(source))
        if safe_url(target) and target not in urls and target.lower().endswith((".js", ".mjs")):
            urls.append(target)
    return urls[:MAX_ASSETS]

def find_context(script):
    findings=[]
    for target in TARGETS:
        positions=[m.start() for m in re.finditer(re.escape(target),script,re.IGNORECASE)]
        for pos in positions[:6]:
            # Public JS source, limited to a tiny static, printable excerpt.
            excerpt=script[max(0,pos-160):min(len(script),pos+220)]
            excerpt=re.sub(r"[^\x20-\x7e]", " ", excerpt)
            findings.append({"endpoint":target,"offset":pos,
                             "sourceExcerpt":excerpt[:380]})
    return findings

def main():
    result={"status":"public_script_readonly","page":HOME,"checkedScripts":0,
            "matches":[],"errors":[],"postRequests":0,"authenticated":False}
    try:
        markup=get_public(HOME)
        urls=script_urls(markup)
        result["scriptCandidates"]=len(urls)
        for url in urls:
            try:
                js=get_public(url)
                result["checkedScripts"]+=1
                findings=find_context(js)
                if findings:
                    result["matches"].append({"scriptPath":urllib.parse.urlsplit(url).path,
                                               "findings":findings})
            except (ValueError,urllib.error.URLError,TimeoutError,OSError) as exc:
                result["errors"].append({"scriptPath":urllib.parse.urlsplit(url).path,
                                         "errorClass":type(exc).__name__})
    except (ValueError,urllib.error.URLError,TimeoutError,OSError) as exc:
        result["status"]="public_page_fetch_failed"
        result["errors"].append({"errorClass":type(exc).__name__})
    print(json.dumps(result,ensure_ascii=False))

if __name__ == "__main__":
    main()
