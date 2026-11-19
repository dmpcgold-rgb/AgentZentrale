#!/usr/bin/env python3
"""Read-only, unauthenticated analysis of publicly served WESTbahn JS assets.

No browser profile, cookies, account access, POST, purchase, or checkout
navigation. Reports bounded static source excerpts for endpoint semantics.
"""
import html
from html.parser import HTMLParser
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
    if not (parsed.scheme == "https" and parsed.hostname in HOSTS
            and parsed.port in (None, 443) and not parsed.username
            and not parsed.password and not parsed.fragment):
        return False
    if not parsed.query:
        return True
    # Public script assets commonly carry a cache-busting version.
    # Never follow unrecognized, sensitive, or free-form URL parameters.
    if not parsed.path.lower().endswith((".js", ".mjs")) or len(parsed.query)>110:
        return False
    try:
        pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True,
                                      strict_parsing=True, max_num_fields=2)
    except ValueError:
        return False
    names=[key.lower() for key,value in pairs]
    allowed=(names in (["v"],["ver"],["version"],
                       ["group","version"],["disable-minify","version"]))
    if not allowed or len(set(names))!=len(names):
        return False
    for key,value in pairs:
        # disable-minify is occasionally a flag without a value.
        if not re.fullmatch(r"[A-Za-z0-9._-]{0,80}",value):
            return False
        if not value and key.lower()!="disable-minify":
            return False
    return True

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

class AssetInventory(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.sources = []
        self.script_tags = 0
        self.inline_script_tags = 0
        self.external_hosts = set()
        self.tag_count = 0

    def handle_starttag(self, tag, attrs):
        self.tag_count += 1
        a = dict(attrs)
        if tag == "script":
            self.script_tags += 1
            src = a.get("src")
            if src:
                self.sources.append(src)
            else:
                self.inline_script_tags += 1
        if tag == "link" and a.get("href"):
            rel = a.get("rel", "").lower()
            if "preload" in rel or "modulepreload" in rel or "script" in a.get("as",""):
                self.sources.append(a["href"])

def discover_assets(markup):
    parsed = AssetInventory()
    parsed.feed(markup)
    candidate_urls = []
    rejection_counts = {"externalHost": 0, "queryOrFragment": 0,
                        "nonJavaScript": 0, "invalidScheme": 0}
    retained_query_count = 0
    for source in parsed.sources:
        target = urllib.parse.urljoin(HOME, html.unescape(source))
        parts = urllib.parse.urlsplit(target)
        if parts.scheme != "https" or parts.username or parts.password:
            rejection_counts["invalidScheme"] += 1
        elif parts.hostname not in HOSTS:
            rejection_counts["externalHost"] += 1
            if parts.hostname:
                parsed.external_hosts.add(parts.hostname.lower())
        elif not parts.path.lower().endswith((".js", ".mjs")):
            rejection_counts["nonJavaScript"] += 1
        elif parts.fragment:
            rejection_counts["queryOrFragment"] += 1
        elif not safe_url(target):
            rejection_counts["queryOrFragment"] += 1
        elif target not in candidate_urls:
            # The original HTML supplied this same-origin, allowlisted
            # versioned script URL. Removing its query returned HTTP errors.
            candidate_urls.append(target)
            if parts.query:
                retained_query_count += 1
    # Report aggregate counts and hostnames only, never page text,
    # query parameters, cookies, tokens or private URL paths.
    return candidate_urls[:MAX_ASSETS], {
        "htmlLengthBand": ("large" if len(markup)>500000
                           else "medium" if len(markup)>50000 else "small"),
        "parsedTagCount": parsed.tag_count,
        "scriptTagCount": parsed.script_tags,
        "inlineScriptTagCount": parsed.inline_script_tags,
        "sourceAttributeCount": len(parsed.sources),
        "queryRetainedForPublicAssets": retained_query_count,
        "externalScriptHosts": sorted(parsed.external_hosts)[:12],
        "rejectedSources": rejection_counts
    }

def script_urls(markup):
    return discover_assets(markup)[0]

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
        urls, discovery = discover_assets(markup)
        result["discovery"]=discovery
        result["scriptCandidates"]=len(urls)
        result["htmlEndpointReferences"]=[t for t in TARGETS if t in markup.lower()]
        for url in urls:
            try:
                js=get_public(url)
                result["checkedScripts"]+=1
                findings=find_context(js)
                if findings:
                    result["matches"].append({"scriptPath":urllib.parse.urlsplit(url).path,
                                               "findings":findings})
            except (ValueError,urllib.error.URLError,TimeoutError,OSError) as exc:
                record={"scriptPath":urllib.parse.urlsplit(url).path,
                        "errorClass":type(exc).__name__}
                if isinstance(exc,urllib.error.HTTPError):
                    record["httpStatus"]=exc.code
                result["errors"].append(record)
    except (ValueError,urllib.error.URLError,TimeoutError,OSError) as exc:
        result["status"]="public_page_fetch_failed"
        result["errors"].append({"errorClass":type(exc).__name__})
    print(json.dumps(result,ensure_ascii=False))

if __name__ == "__main__":
    main()
