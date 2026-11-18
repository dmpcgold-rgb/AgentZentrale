#!/usr/bin/env python3
"""Read-only, redacted WESTbahn ticketshop entry diagnostics.

No control is clicked. No checkout. Non-GET/HEAD network requests are blocked.
Uses the existing private browser profile and the same interprocess lock as worker.py.
"""
import fcntl
import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright

TARGET = "https://westbahn.at/ticketshop/ticket-buchen/ticketshop/"
WORDS = re.compile(
    r"^(?:"
    r".{0,45}(?:KlimaTicket|Comfort|2\+|Sitzplatz|Wagen|Platz|Reservierung|"
    r"Von|Nach|Abfahrt|Datum|Verbindung|Ticket|Suchen|Weiter|"
    r"Fahrt|Ändern|Bearbeiten).{0,45}"
    r")$", re.IGNORECASE
)

def main():
    root = Path(os.environ.get("WESTBAHN_BROWSER_PROFILE", "./data/westbahn-browser")).resolve()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (root / ".agent.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(json.dumps({"status":"profile_busy","bookingAuthorized":False}))
            return

        with sync_playwright() as p:
            kwargs = {
                "headless":True, "timeout":20000, "accept_downloads":False
            }
            if os.environ.get("WESTBAHN_CHROMIUM_PATH"):
                kwargs["executable_path"]=os.environ["WESTBAHN_CHROMIUM_PATH"]
            context = p.chromium.launch_persistent_context(str(root/"chromium"), **kwargs)
            try:
                def guard(route):
                    req = route.request
                    if req.method.upper() not in ("GET", "HEAD"):
                        route.abort()
                        return
                    if req.is_navigation_request():
                        parsed = urlsplit(req.url)
                        if parsed.scheme != "https" or parsed.hostname not in ("westbahn.at", "www.westbahn.at"):
                            route.abort()
                            return
                    route.continue_()
                context.route("**/*", guard)
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(TARGET, wait_until="domcontentloaded", timeout=25000)
                page.wait_for_timeout(1600)
                observed = page.evaluate(r"""() => {
                    const norm = value => (value || "").replace(/\s+/g," ").trim();
                    const visible = e => !!e.getClientRects().length &&
                        getComputedStyle(e).visibility!=="hidden" &&
                        getComputedStyle(e).display!=="none";
                    const relevant = /KlimaTicket|Comfort|2\+|Sitzplatz|Wagen|Platz|Reservierung|Von|Nach|Abfahrt|Datum|Verbindung|Ticket|Suchen|Weiter|Fahrt|Ändern|Bearbeiten/i;
                    const controls = [...document.querySelectorAll(
                        "button, select, input, a, [role=button], [role=combobox]"
                    )].filter(visible).slice(0,450);
                    const rows = controls.map(e => {
                        const text = norm(e.getAttribute("aria-label") ||
                            e.getAttribute("placeholder") ||
                            e.innerText || e.getAttribute("title"));
                        if(!relevant.test(text) || text.length>90) return null;
                        return {kind:e.tagName.toLowerCase(), label:text.slice(0,90),
                            disabled:e.matches(":disabled,[aria-disabled=true]")};
                    }).filter(Boolean).slice(0,36);
                    return {
                        pageKind:location.pathname.startsWith("/ticketshop") ?
                            "ticketshop" : "other",
                        visibleRelevantControls:rows,
                        matchingHeadings:[...document.querySelectorAll("h1,h2,h3,h4")]
                            .filter(visible).map(e=>norm(e.innerText))
                            .filter(t=>t.length<75 && relevant.test(t)).slice(0,12)
                    };
                }""")
                # Resolve only navigation targets, not private account or form values.
                navigation = page.evaluate(r"""() => {
                    const norm = s => (s || "").replace(/\s+/g," ").trim();
                    const links=[...document.querySelectorAll('a[href]')];
                    return links.filter(e => /Zur Ticketbuchung|Ticket buchen/i.test(norm(e.innerText)))
                        .slice(0,8).map(e=>{
                            let u;
                            try {u=new URL(e.getAttribute('href'),location.href);} catch {return {valid:false};}
                            return {
                                label:norm(e.innerText).slice(0,45),
                                protocol:u.protocol,
                                host:u.hostname,
                                path:u.pathname.slice(0,140),
                                queryKeys:[...u.searchParams.keys()].filter(k=>
                                    /^(?:lang|locale|language|step|action)$/i.test(k)).slice(0,6)
                            };
                        });
                }""")
                # The booking UI may be embedded in a frame; disclose only
                # public host/path and aggregate control counts, never values.
                frame_summary = []
                for frame in page.frames[:12]:
                    u = urlsplit(frame.url)
                    if u.scheme != "https":
                        continue
                    try:
                        facts = frame.evaluate(r"""() => {
                            const vis=e=>!!e.getClientRects().length;
                            const inputs=[...document.querySelectorAll('input,select,textarea')].filter(vis);
                            return {
                                inputs:inputs.length,
                                buttons:[...document.querySelectorAll('button,[role=button]')].filter(vis).length,
                                inputTypes:[...new Set(inputs.map(e=>e.tagName.toLowerCase()==='input'
                                    ? (e.getAttribute('type')||'text').toLowerCase()
                                    :e.tagName.toLowerCase()))].slice(0,12)
                            };
                        }""")
                    except Exception:
                        facts = {"status":"frame_unavailable"}
                    frame_summary.append({
                        "host":u.hostname if u.hostname in ("westbahn.at","www.westbahn.at") else "other_https",
                        "path":u.path[:100] if u.hostname in ("westbahn.at","www.westbahn.at") else "redacted",
                        "controls":facts
                    })
                print(json.dumps({
                    "status":"ticketshop_read_only_inspected",
                    "result":observed,
                    "ticketshopNavigation":navigation,
                    "frames":frame_summary,
                    "bookingAuthorized":False,
                    "purchaseExecuted":False,
                    "notes":"No clicks; all non-GET/HEAD requests blocked; page data redacted."
                }, ensure_ascii=False))
            finally:
                context.close()

if __name__=="__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({
            "status":"ticketshop_inspection_blocked",
            "errorClass":type(exc).__name__[:48],
            "bookingAuthorized":False,"purchaseExecuted":False
        }))
