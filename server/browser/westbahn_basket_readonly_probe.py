#!/usr/bin/env python3
"""Read-only inspection of the current WESTbahn cart; never add or buy.

Uses existing isolated browser profile. Blocks every non-GET/HEAD request.
Only emits public UI labels, booking route hints and redacted endpoint paths.
"""
import fcntl
import json
import os
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright

URL="https://westbahn.at/ticketshop/checkout"
def main():
    profile=Path(os.environ.get("WESTBAHN_BROWSER_PROFILE","./data/westbahn-browser")).resolve()
    profile.mkdir(parents=True,exist_ok=True,mode=0o700)
    with (profile/".agent.lock").open("a") as lock:
        try:
            fcntl.flock(lock,fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(json.dumps({"status":"profile_busy","cartModified":False,"purchaseExecuted":False}))
            return
        with sync_playwright() as p:
            opts={"headless":True,"accept_downloads":False,"timeout":20000,
                  "locale":"de-AT","timezone_id":"Europe/Vienna"}
            if os.environ.get("WESTBAHN_CHROMIUM_PATH"):
                opts["executable_path"]=os.environ["WESTBAHN_CHROMIUM_PATH"]
            context=p.chromium.launch_persistent_context(str(profile/"chromium"),**opts)
            blocked=[]
            failed=[]
            try:
                def guard(route):
                    req=route.request
                    u=urlsplit(req.url)
                    if req.method.upper() not in ("GET","HEAD"):
                        item={"method":req.method,"host":u.hostname if u.hostname in
                              ("westbahn.at","www.westbahn.at") else "external",
                              "path":u.path[:100] if u.hostname in
                              ("westbahn.at","www.westbahn.at") else "redacted"}
                        if item not in blocked and len(blocked)<15: blocked.append(item)
                        route.abort()
                        return
                    if req.is_navigation_request() and (
                        u.scheme!="https" or u.hostname not in ("westbahn.at","www.westbahn.at")
                    ):
                        route.abort()
                        return
                    route.continue_()
                def on_fail(req):
                    u=urlsplit(req.url)
                    if u.hostname in ("westbahn.at","www.westbahn.at"):
                        item={"method":req.method,"path":u.path[:100]}
                        if item not in failed and len(failed)<12: failed.append(item)
                context.route("**/*",guard)
                context.on("requestfailed",on_fail)
                page=context.pages[0] if context.pages else context.new_page()
                page.goto(URL,wait_until="domcontentloaded",timeout=25000)
                page.wait_for_timeout(1400)
                facts=page.evaluate(r"""() => {
                    const norm=s=>(s||"").replace(/\s+/g," ").trim();
                    const visible=e=>!!e.getClientRects().length &&
                        getComputedStyle(e).display!=="none" &&
                        getComputedStyle(e).visibility!=="hidden";
                    const main=document.querySelector("main")||document.body;
                    const text=norm(main.innerText);
                    const safeLabel=s=>norm(s).slice(0,90);
                    const controls=[...main.querySelectorAll("button,a[href],[role=button]")]
                        .filter(visible).map(e=>({
                            label:safeLabel(e.getAttribute("aria-label")||e.innerText),
                            tag:e.tagName.toLowerCase(),
                            disabled:e.matches(":disabled,[aria-disabled=true]"),
                            path:(()=>{
                                const raw=e.getAttribute("href");
                                if(!raw)return null;
                                try {
                                    const u=new URL(raw,location.href);
                                    return u.origin===location.origin?u.pathname.slice(0,100):"external";
                                }catch{return "invalid";}
                            })()
                        })).filter(x=>/Sitz|Platz|Reserv|Wagen|Warenkorb|Bearbeiten|Weiter|Bezahl|Kasse|Ticket|Zug|Entfernen/i.test(x.label))
                        .slice(0,35);
                    return {
                        path:location.pathname.slice(0,150),
                        hasWienMeidling:/Wien Meidling/i.test(text),
                        hasWienerNeustadt:/Wiener Neustadt/i.test(text),
                        hasDate20112026:/20\.11\.2026|20\.\s*November\s*2026/i.test(text),
                        hasTrain1009:/\b1009\b/.test(text),
                        has1822:/\b18:22\b/.test(text),
                        hasComfort:/Comfort/i.test(text),
                        hasClimateFare:/KlimaTicket/i.test(text),
                        containsEmptyCartMessage:/Warenkorb\s+ist\s+leer|keine\s+Artikel|keine\s+Produkte/i.test(text),
                        visibleSeatMap:!![...main.querySelectorAll(
                            '[class*=seat-map],[class*=seatmap],[data-testid*=seat]'
                        )].find(visible),
                        publicHeadings:[...main.querySelectorAll("h1,h2,h3,[role=heading]")]
                            .filter(visible).map(e=>safeLabel(e.innerText))
                            .filter(x=>/Warenkorb|Sitz|Platz|Ticket|Reserv|Reise|Checkout/i.test(x))
                            .slice(0,15),
                        controls,
                        note:"No account details, ticket IDs, form values or raw page text returned"
                    };
                }""")
                print(json.dumps({"status":"basket_read_only_inspected",
                                  "result":facts,"blockedRequests":blocked,
                                  "failedFirstPartyRequests":failed,
                                  "cartModified":False,"bookingAuthorized":False,
                                  "purchaseExecuted":False},ensure_ascii=False))
            finally:
                context.close()

if __name__=="__main__":
    try: main()
    except Exception as exc:
        print(json.dumps({"status":"basket_inspection_blocked",
                          "errorClass":type(exc).__name__[:50],
                          "cartModified":False,"bookingAuthorized":False,"purchaseExecuted":False}))
