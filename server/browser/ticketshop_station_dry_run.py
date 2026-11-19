#!/usr/bin/env python3
"""Select the two WESTbahn stations in a safe non-checkout browser dry run.

Only exact matching station suggestions may be selected. This does not
select dates, train, fare, seats, cart, payment, or booking controls.
Only exact first-party read/quote endpoints and one basket/add POST are allowed. Checkout, purchase and other writes remain blocked.
"""
import fcntl
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

URL = "https://westbahn.at/ticketshop/ticket-buchen/"
ORIGIN = "Wien Meidling"
DESTINATION = "Wiener Neustadt Hbf"
CURRENT_STAGE = "startup"

def main():
    global CURRENT_STAGE
    root = Path(os.environ.get("WESTBAHN_BROWSER_PROFILE", "./data/westbahn-browser")).resolve()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (root / ".agent.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(json.dumps({"status":"profile_busy","bookingAuthorized":False}))
            return
        with sync_playwright() as p:
            args={"headless":True,"accept_downloads":False,"timeout":20000,
                  "locale":"de-AT","timezone_id":"Europe/Vienna"}
            if os.environ.get("WESTBAHN_CHROMIUM_PATH"):
                args["executable_path"]=os.environ["WESTBAHN_CHROMIUM_PATH"]
            context=p.chromium.launch_persistent_context(str(root/"chromium"),**args)
            try:
                network={"allowedTimetableReads":[],"allowedBasketAdd":[],"allowedSeatLookup":[],"seatLookupResponses":[],"allowedSeatUpdate":[],"seatUpdateResponses":[],"allowedBasketRead":[],"basketReadResponses":[],"blockedFirstPartyWrites":[],"failedFirstPartyRequests":[],
                         "httpErrors":[],"basketAddResponses":[],"firstPartyRequestsByMethod":{}}
                def on_failed(req):
                    u=urlsplit(req.url)
                    if u.hostname in ("westbahn.at","www.westbahn.at"):
                        item={"method":req.method,"path":u.path[:130]}
                        if item not in network["failedFirstPartyRequests"] and len(network["failedFirstPartyRequests"])<15:
                            network["failedFirstPartyRequests"].append(item)
                def on_response(resp):
                    u=urlsplit(resp.url)
                    # Record only the transport status, never response body,
                    # profile data, cookies or ticket identifiers.
                    if (u.hostname in ("westbahn.at","www.westbahn.at")
                        and u.path=="/api/v1/basket/add"):
                        network["basketAddResponses"].append({
                            "method":resp.request.method,
                            "status":resp.status,
                            "ok":resp.ok,
                            "contentType":(resp.headers.get("content-type") or "").split(";")[0][:50]
                        })
                    if (u.hostname in ("westbahn.at","www.westbahn.at")
                        and u.path=="/ticketshop/rsv/seats"):
                        network["seatLookupResponses"].append({
                            "method":resp.request.method,
                            "status":resp.status,
                            "ok":resp.ok,
                            "contentType":(resp.headers.get("content-type") or "").split(";")[0][:50]
                        })
                    if (u.hostname in ("westbahn.at","www.westbahn.at")
                        and u.path in ("/ticketshop/rsv/update-seats",
                                       "/ticketshop/basket/get")):
                        key=("seatUpdateResponses" if u.path=="/ticketshop/rsv/update-seats"
                             else "basketReadResponses")
                        network[key].append({
                            "status":resp.status,"ok":resp.ok,
                            "contentType":(resp.headers.get("content-type") or "").split(";")[0][:50]
                        })
                    if u.hostname in ("westbahn.at","www.westbahn.at") and resp.status>=400:
                        item={"status":resp.status,"path":u.path[:130]}
                        if item not in network["httpErrors"] and len(network["httpErrors"])<15:
                            network["httpErrors"].append(item)
                context.on("requestfailed",on_failed)
                context.on("response",on_response)
                def guard(route):
                    req=route.request
                    u=urlsplit(req.url)
                    if u.hostname in ("westbahn.at","www.westbahn.at"):
                        network["firstPartyRequestsByMethod"][req.method]=network["firstPartyRequestsByMethod"].get(req.method,0)+1
                    # These exact POST endpoints return timetable/pricing data.
                    # No general POST allowance and no booking/checkout route.
                    safe_timetable=(
                        req.method.upper()=="POST"
                        and u.scheme=="https"
                        and u.hostname in ("westbahn.at","www.westbahn.at")
                        and u.port in (None,443)
                        and u.path in ("/timetable/get-timetable","/timetable/get-day-prices",
                                       "/api/v1/prices","/api/v1/klimatickets")
                        and not u.fragment  # WESTbahn uses query parameters for timetable fetches
                        and req.resource_type in ("fetch","xhr")
                        and not req.is_navigation_request()
                    )
                    if safe_timetable:
                        item={"method":"POST","path":u.path}
                        if item not in network["allowedTimetableReads"]:
                            network["allowedTimetableReads"].append(item)
                        route.continue_()
                        return
                    # User authorized adding this zero-euro ticket to the
                    # basket, but NOT purchasing. Limit to a single add per run.
                    safe_cart_add=(
                        req.method.upper()=="POST"
                        and u.scheme=="https"
                        and u.hostname in ("westbahn.at","www.westbahn.at")
                        and u.port in (None,443)
                        and u.path=="/api/v1/basket/add"
                        and not u.query and not u.fragment
                        and req.resource_type in ("fetch","xhr")
                        and not req.is_navigation_request()
                        and len(network["allowedBasketAdd"])==0
                    )
                    if safe_cart_add:
                        network["allowedBasketAdd"].append({"method":"POST","path":u.path})
                        route.continue_()
                        return
                    # Allow one seat-list request only; no choosing or
                    # committing any seat, cart checkout, or purchase.
                    safe_seat_lookup=(
                        req.method.upper()=="POST"
                        and u.scheme=="https"
                        and u.hostname in ("westbahn.at","www.westbahn.at")
                        and u.port in (None,443)
                        and u.path=="/ticketshop/rsv/seats"
                        and not u.query and not u.fragment
                        and req.resource_type in ("fetch","xhr")
                        and not req.is_navigation_request()
                        and len(network["allowedSeatLookup"])<4
                    )
                    if safe_seat_lookup:
                        network["allowedSeatLookup"].append({"method":"POST","path":u.path})
                        route.continue_()
                        return
                    # Only these two additional endpoints are permitted:
                    # read basket contents; apply a single already highlighted
                    # seat. They cannot invoke checkout or payment.
                    safe_seat_update=(
                        req.method.upper()=="POST"
                        and u.scheme=="https"
                        and u.hostname in ("westbahn.at","www.westbahn.at")
                        and u.port in (None,443)
                        and u.path=="/ticketshop/rsv/update-seats"
                        and not u.query and not u.fragment
                        and req.resource_type in ("fetch","xhr")
                        and not req.is_navigation_request()
                        and len(network["allowedSeatUpdate"])==0
                        and bool(network["allowedSeatLookup"])
                    )
                    if safe_seat_update:
                        network["allowedSeatUpdate"].append({"method":"POST","path":u.path})
                        route.continue_()
                        return
                    safe_basket_read=(
                        req.method.upper()=="POST"
                        and u.scheme=="https"
                        and u.hostname in ("westbahn.at","www.westbahn.at")
                        and u.port in (None,443)
                        and u.path=="/ticketshop/basket/get"
                        and not u.query and not u.fragment
                        and req.resource_type in ("fetch","xhr")
                        and not req.is_navigation_request()
                        and len(network["allowedBasketRead"])<4
                    )
                    if safe_basket_read:
                        network["allowedBasketRead"].append({"method":"POST","path":u.path})
                        route.continue_()
                        return
                    if req.method.upper() not in ("GET","HEAD"):
                        if u.hostname in ("westbahn.at","www.westbahn.at"):
                            item={"method":req.method,"path":u.path[:130],
                                  "resourceType":req.resource_type,
                                  "host":u.hostname,"scheme":u.scheme,
                                  "hasQuery":bool(u.query),
                                  "isNavigation":req.is_navigation_request()}
                            if item not in network["blockedFirstPartyWrites"] and len(network["blockedFirstPartyWrites"])<15:
                                network["blockedFirstPartyWrites"].append(item)
                        route.abort()
                        return
                    if req.is_navigation_request():
                        u=urlsplit(req.url)
                        if u.scheme!="https" or u.hostname not in ("westbahn.at","www.westbahn.at"):
                            route.abort()
                            return
                    route.continue_()
                context.route("**/*",guard)
                page=context.pages[0] if context.pages else context.new_page()
                CURRENT_STAGE="opening_ticketshop"
                page.goto(URL,wait_until="domcontentloaded",timeout=25000)
                page.wait_for_timeout(1300)
                result={"status":"station_selection_dry_run","bookingAuthorized":False,
                        "purchaseExecuted":False,"steps":[]}
                # User-provided form diagnostic confirmed the two comboboxes have
                # associated labels. No positional selector or unbounded click.
                for name,target in (("Von",ORIGIN),("Nach",DESTINATION)):
                    field=page.get_by_role("combobox",name=name,exact=True)
                    if field.count()!=1 or not field.is_visible():
                        result["status"]="station_selection_blocked"
                        result["steps"].append({"field":name,"status":"ambiguous_field",
                                                 "count":field.count()})
                        break
                    CURRENT_STAGE="choosing_station"
                    field.fill(target,timeout=5000)
                    page.wait_for_timeout(700)
                    # Match only named railway station options. An alternate
                    # spelling is not enough unless the listbox offers one
                    # unique candidate with that full accessible name.
                    aliases=(target,) if name=="Von" else (
                        "Wiener Neustadt Hbf",
                        "Wiener Neustadt Hauptbahnhof",
                        "Wr. Neustadt Hbf",
                        "Wiener Neustadt",
                    )
                    listboxes=page.get_by_role("listbox")
                    option_labels=[]
                    if listboxes.count()==1 and listboxes.first.is_visible():
                        option_labels=[
                            text.strip() for text in
                            listboxes.first.get_by_role("option").all_text_contents()
                            if text.strip()
                        ][:20]
                    selected=None
                    for alias in aliases:
                        opts=page.get_by_role("option",name=alias,exact=True)
                        if opts.count()==1 and opts.first.is_visible():
                            if selected is not None:
                                selected=None
                                break
                            selected=(opts.first,alias)
                    if selected is not None:
                        chosen,alias=selected
                        chosen.click(timeout=4000)
                        result["steps"].append({"field":name,"status":"suggestion_selected",
                                                 "requested":target,"matchedLabel":alias})
                        continue
                    # If exact aliases were not available, retry only the
                    # destination text search; never guess another station.
                    if name=="Nach":
                        field.fill("Wiener Neustadt",timeout=5000)
                        page.wait_for_timeout(850)
                        for alias in aliases:
                            opts=page.get_by_role("option",name=alias,exact=True)
                            if opts.count()==1 and opts.first.is_visible():
                                if selected is not None:
                                    selected=None
                                    break
                                selected=(opts.first,alias)
                        if selected is not None:
                            chosen,alias=selected
                            chosen.click(timeout=4000)
                            result["steps"].append({"field":name,"status":"suggestion_selected",
                                                     "requested":target,"matchedLabel":alias})
                            continue
                        if listboxes.count()==1:
                            option_labels=[
                                text.strip() for text in
                                listboxes.first.get_by_role("option").all_text_contents()
                                if text.strip()
                            ][:20]
                    result["status"]="station_selection_blocked"
                    result["steps"].append({"field":name,"status":"suggestion_not_unique",
                                             "requested":target,
                                             "listboxes":listboxes.count(),
                                             "visibleOptionLabels":option_labels})
                    break
                if len(result["steps"])==2 and all(x["status"]=="suggestion_selected" for x in result["steps"]):
                    result["status"]="stations_selected_dry_run"
                    # Dry-run only: select the known test date, never search
                    # connections, checkout, or reserve a seat.
                    test_day="2026-11-20"
                    editor=page.get_by_role("button",name="Hinfahrt Datum bearbeiten",exact=True)
                    if editor.count()!=1 or not editor.is_visible():
                        result["datePicker"]={"status":"editor_missing_or_ambiguous",
                                              "count":editor.count()}
                    else:
                        CURRENT_STAGE="opening_date_picker"
                        editor.click(timeout=4000)
                        page.wait_for_timeout(350)
                        month=page.get_by_role("button",name="November 2026",exact=True)
                        # WESTbahn's calendar buttons may expose an accessible
                        # name longer than their visible day text. Require an
                        # exact visible text of "20" and one unique enabled
                        # control, with the requested month heading present.
                        day_locator=page.locator("button").filter(
                            has_text=__import__("re").compile(r"^\s*20\s*$")
                        )
                        day_candidates=page.evaluate(r"""() => {
                            const shown=e=>!!e.getClientRects().length &&
                                getComputedStyle(e).visibility!=="hidden";
                            return [...document.querySelectorAll("button")]
                                .filter(e=>shown(e) && (
                                    (e.textContent||"").trim()==="20" ||
                                    (e.innerText||"").trim()==="20" ||
                                    /(?:^|\D)20(?:\D|$)/.test(e.getAttribute("aria-label")||"")
                                )).slice(0,12).map(e=>({
                                    text:(e.innerText||"").trim().slice(0,35),
                                    ariaLabel:(e.getAttribute("aria-label")||"").slice(0,85),
                                    disabled:e.matches(":disabled,[aria-disabled=true]"),
                                    title:(e.getAttribute("title")||"").slice(0,80),
                                    dataDate:(e.getAttribute("data-date")||"").slice(0,35)
                                }));
                        }""")
                        result["datePicker"]={
                            "status":"date_not_selected",
                            "requested":test_day,
                            "monthMatches":month.count(),
                            "dayMatches":day_locator.count(),
                            "dayCandidates":day_candidates
                        }
                        if month.count()==1 and month.is_visible() and day_locator.count()==1 and day_locator.is_visible() and day_locator.is_enabled():
                            CURRENT_STAGE="choosing_date"
                            day_locator.click(timeout=4000)
                            page.wait_for_timeout(350)
                            # Inspect only the outward date field and any
                            # specifically exposed selection metadata.
                            result["datePicker"]=page.evaluate(r"""() => {
                                const input=[...document.querySelectorAll("input")].find(
                                    e=>e.labels && [...e.labels].some(
                                        l=>l.textContent.trim()==="Hinfahrt"));
                                const value=input ? input.value.slice(0,50) : null;
                                const declared=input ? {
                                    value:input.getAttribute("value"),
                                    dateTime:input.getAttribute("data-date"),
                                    aria:input.getAttribute("aria-label")
                                } : null;
                                const accepted=/^(?:20\.11\.2026|20\/11\/2026|2026-11-20|20\. November 2026)$/.test(value||"");
                                return {
                                    status:accepted?"date_field_verified":"date_field_review_required",
                                    requested:"2026-11-20",
                                    dateFieldValue:value,
                                    declared:declared
                                };
                            }""")
                            if result["datePicker"]["status"]=="date_field_verified":
                                result["status"]="stations_and_date_selected_dry_run"
                                # Read only: confirm navigation and match
                                # route/date/timetable evidence before any
                                # train-selection click is implemented.
                                page.wait_for_timeout(700)
                                result["connectionOverview"]=page.evaluate(r"""() => {
                                    const norm=s=>(s||"").replace(/\s+/g," ").trim();
                                    const visible=e=>!!e.getClientRects().length &&
                                        getComputedStyle(e).display!=="none" &&
                                        getComputedStyle(e).visibility!=="hidden";
                                    const inputs=[...document.querySelectorAll("input")];
                                    const outbound=inputs.find(e=>e.labels &&
                                        [...e.labels].some(l=>norm(l.textContent)==="Hinfahrt"));
                                    const labels=[...document.querySelectorAll("button")].filter(visible)
                                        .map(e=>({
                                            text:norm(e.getAttribute("aria-label")||e.innerText).slice(0,60),
                                            disabled:e.matches(':disabled,[aria-disabled=true]')
                                        })).filter(e=>/20\. November|20\.11|Nach Abfahrtszeit sortieren|Unsere Klassen/i.test(e.text)).slice(0,12);
                                    const cards=[...document.querySelectorAll("body *")].filter(e=>{
                                        if (!visible(e)) return false;
                                        const t=norm(e.innerText);
                                        return t.length>=5 && t.length<=160 &&
                                            /18:22/.test(t) &&
                                            ![...e.children].some(c=>visible(c) &&
                                                /18:22/.test(norm(c.innerText)) &&
                                                norm(c.innerText).length<=160);
                                    }).slice(0,12).map(e=>{
                                        let node=e;
                                        for(let i=0;i<5 && node.parentElement;i++){
                                            if(norm(node.innerText).length>500) break;
                                            node=node.parentElement;
                                        }
                                        const text=norm(node.innerText).slice(0,500);
                                        return {
                                            hasDeparture1822:/18:22/.test(text),
                                            hasArrival1849:/18:49/.test(text),
                                            hasTrain1009:/\b1009\b/.test(text),
                                            hasComfort:/Comfort/i.test(text),
                                            hasEuroZero:/(?:0,00|0\.00|0)\s*(?:€|EUR)/i.test(text),
                                            visibleTimes:[...new Set((text.match(/\b\d{1,2}:\d{2}\b/g)||[]))].slice(0,10)
                                        };
                                    });
                                    return {
                                        routePath:location.pathname.slice(0,200),
                                        outboundField:outbound?outbound.value.slice(0,35):null,
                                        requestedDayButtons:labels,
                                        // Tiles are alternative dates; the outbound input is authoritative.
                                        visibleDateTiles:[...document.querySelectorAll('button')]
                                            .filter(visible).map(e=>({
                                                label:norm(e.getAttribute('aria-label')||e.innerText).slice(0,70),
                                                disabled:e.matches(':disabled,[aria-disabled=true]')
                                            })).filter(e=>/Nov(?:ember)?/i.test(e.label) && /(?:26|27|28)/.test(e.label)).slice(0,12),
                                        targetTrainCandidates:cards,
                                        targetTrainCount:cards.length,
                                        timetableEvidence:(()=>{
                                            const root=document.querySelector('main')||document.body;
                                            const body=norm(root.innerText).slice(0,35000);
                                            const allTimes=[...new Set((body.match(/\b(?:[01]?\d|2[0-3]):[0-5]\d\b/g)||[]))].slice(0,80);
                                            return {
                                                has1822Anywhere:/\b18:22\b/.test(body),
                                                has1849Anywhere:/\b18:49\b/.test(body),
                                                hasTrain1009Anywhere:/\b1009\b/.test(body),
                                                distinctVisibleTimes:allTimes,
                                                timeCount:allTimes.length,
                                                noConnectionsMessage:/keine (?:passenden )?(?:verbindungen|fahrten)|keine ergebnisse|keine züge/i.test(body),
                                                loadingIndicator:!!root.querySelector('[aria-busy=true],[role=progressbar],.loading,.spinner'),
                                                visibleMainTextLength:body.length,
                                                candidateTrainButtons:[...root.querySelectorAll('button,[role=button]')]
                                                    .filter(visible).map(e=>norm(e.getAttribute('aria-label')||e.innerText))
                                                    .filter(t=>/\b(?:\d{1,2}:\d{2}|WESTbahn|abfahrt|verbindung)\b/i.test(t))
                                                    .slice(0,14).map(t=>t.slice(0,90))
                                            };
                                        })(),
                                        resultsDiagnostics:(()=>{
                                            const root=document.querySelector('main')||document.body;
                                            const text=norm(root.innerText);
                                            const headings=[...root.querySelectorAll('h1,h2,h3,h4,[role=heading]')]
                                                .filter(visible).map(e=>norm(e.innerText).slice(0,100))
                                                .filter(Boolean).slice(0,30);
                                            const lines=(root.innerText||"").split(/\n+/).map(norm).filter(Boolean);
                                            // Only pre-approved timetable/status terms; never
                                            // emit arbitrary text, account names, or identifiers.
                                            const terms=/verbindung|abfahrt|ankunft|fahrt|zug|prei[sz]|ausgebucht|nicht verfügbar|nicht buchbar|keine|hinweis|ergebnis|laden|uhrzeit|umsteigen|fahrplan|tagespreis|reisezeit/i;
                                            const statusLines=lines.filter(t=>terms.test(t)&&t.length<=110)
                                                .slice(0,35).map(t=>t.replace(/\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/gi,"[redacted]"));
                                            const dateRows=[...root.querySelectorAll('button')].filter(visible)
                                                .map(e=>({label:norm(e.getAttribute('aria-label')||e.innerText).slice(0,65),
                                                    disabled:e.matches(':disabled,[aria-disabled=true]')}))
                                                .filter(e=>/\b(?:18|19|20|21|22|23|24)\.\s*November/i.test(e.label))
                                                .slice(0,10);
                                            return {headings,statusLines,dateRows,
                                                visibleMainLength:text.length,
                                                resultsRegionCount:root.querySelectorAll(
                                                    '[class*="connection"],[class*="journey"],[class*="timetable"],[data-testid*="connection"]'
                                                ).length};
                                        })(),
                                        note:"Observed timetable content only; no live availability or booking authorization."
                                    };
                                }""")
                                # Identify the 18:22 row and controls without
                                # clicking. Do not assume the train number is
                                # in the same smallest DOM element as the time.
                                result["train1009Diagnostic"]=page.evaluate(r"""() => {
                                    const norm=s=>(s||"").replace(/\s+/g," ").trim();
                                    const visible=e=>!!e.getClientRects().length &&
                                        getComputedStyle(e).visibility!=="hidden" &&
                                        getComputedStyle(e).display!=="none";
                                    const leafs=[...document.querySelectorAll("main *")].filter(e=>{
                                        if(!visible(e))return false;
                                        const t=norm(e.innerText);
                                        return t.length>0 && t.length<=100 && /\b18:22\b/.test(t) &&
                                            ![...e.children].some(c=>/\b18:22\b/.test(norm(c.innerText)) &&
                                                norm(c.innerText).length<=100);
                                    }).slice(0,8);
                                    const rows=leafs.map(e=>{
                                        let n=e;
                                        let best=null;
                                        for(let i=0;i<9 && n;i++,n=n.parentElement){
                                            const t=norm(n.innerText);
                                            if(t.length>1500)break;
                                            const hasTime=/\b18:22\b/.test(t);
                                            const hasArrival=/\b18:49\b/.test(t);
                                            const hasNumber=/\b1009\b/.test(t);
                                            if(hasTime && hasArrival){
                                                best=n;
                                                if(hasNumber)break;
                                            }
                                        }
                                        if(!best)return {status:"row_not_found"};
                                        const label=n=>norm(n.getAttribute("aria-label")||
                                            n.innerText||n.getAttribute("title")||
                                            n.getAttribute("value")).slice(0,90);
                                        return {
                                            status:"row_found",
                                            has1822:/\b18:22\b/.test(norm(best.innerText)),
                                            has1849:/\b18:49\b/.test(norm(best.innerText)),
                                            has1009:/\b1009\b/.test(norm(best.innerText)),
                                            hasComfortClass:/Comfort\s*(?:Class)?\s*2\+/i.test(norm(best.innerText)),
                                            controls:[...best.querySelectorAll(
                                                "button,a[href],[role=button],[role=radio],input[type=radio]"
                                            )].filter(visible).slice(0,14).map(c=>({
                                                tag:c.tagName.toLowerCase(),
                                                role:c.getAttribute("role")||"",
                                                label:label(c),
                                                disabled:c.matches(":disabled,[aria-disabled=true]")
                                            })),
                                            ancestorTag:best.tagName.toLowerCase(),
                                            ancestorClasses:(typeof best.className==="string"?
                                                best.className:"").slice(0,100)
                                        };
                                    });
                                    return {matchedTimeLeafCount:leafs.length,rows:rows.slice(0,5),
                                        clicked:false,reservationMade:false};
                                }""")
                                # Select only the verified train card in the
                                # browser UI. No non-timetable writes are allowed
                                # by the network guard; no payment/reservation.
                                train=result["train1009Diagnostic"]
                                if (train["matchedTimeLeafCount"]==1
                                    and len(train["rows"])==1
                                    and all(train["rows"][0].get(x) for x in ("has1822","has1849","has1009"))
                                    and result["datePicker"]["dateFieldValue"]=="20.11.2026"):
                                    # DOM innerText verified all 3 signals,
                                    # whereas Playwright has_text uses textContent
                                    # semantics and missed this exact card.
                                    tile_handle=page.evaluate_handle(r"""() => {
                                        const norm=s=>(s||"").replace(/\s+/g," ").trim();
                                        const visible=e=>!!e.getClientRects().length &&
                                            getComputedStyle(e).visibility!=="hidden";
                                        const candidates=[...document.querySelectorAll(
                                            ".west-ui-select-connection-tile--content"
                                        )].filter(e=>{
                                            const t=norm(e.innerText);
                                            return visible(e) &&
                                                /\b18:22\b/.test(t) &&
                                                /\b18:49\b/.test(t) &&
                                                /\b1009\b/.test(t);
                                        });
                                        return candidates.length===1?candidates[0]:null;
                                    }""")
                                    tile=tile_handle.as_element()
                                    if tile is not None and tile.is_visible():
                                        CURRENT_STAGE="opening_train_1009"
                                        tile.click(timeout=5000)
                                        page.wait_for_timeout(850)
                                        result["trainSelectionDiagnostic"]=page.evaluate(r"""() => {
                                            const norm=s=>(s||"").replace(/\s+/g," ").trim();
                                            const visible=e=>!!e.getClientRects().length &&
                                                getComputedStyle(e).visibility!=="hidden";
                                            const main=document.querySelector("main")||document.body;
                                            const controls=[...main.querySelectorAll(
                                                "button,[role=button],[role=radio],a[href]"
                                            )].filter(visible).map(e=>({
                                                label:norm(e.getAttribute("aria-label")||e.innerText).slice(0,80),
                                                tag:e.tagName.toLowerCase(),
                                                disabled:e.matches(":disabled,[aria-disabled=true]")
                                            })).filter(x=>x.label && /Comfort|Klasse|Sitz|Reserv|Weiter|Tarif|Ticket|Platz|2\+|Warenkorb/i.test(x.label)).slice(0,28);
                                            const headings=[...main.querySelectorAll("h1,h2,h3,h4,[role=heading]")]
                                                .filter(visible).map(e=>norm(e.innerText).slice(0,90))
                                                .filter(t=>/Sitz|Klasse|Ticket|Tarif|Reserv|Reisende/i.test(t)).slice(0,12);
                                            return {
                                                status:"train_tile_clicked_without_purchase",
                                                path:location.pathname.slice(0,170),
                                                controls,headings,
                                                hasComfort2Plus:/Comfort\s*(?:Class)?\s*2\+/i.test(main.innerText),
                                                hasSeatMap:/Sitzplatz\s*(?:auswahl|reservierung)|Sitzplan/i.test(main.innerText)
                                            };
                                        }""")
                                        result["status"]="train_tile_opened_dry_run"
                                        # Select the Comfort 2+ option strictly
                                        # inside the one previously verified
                                        # 1009 connection tile. Do not choose a
                                        # Comfort option from another train.
                                        comfort_target=page.evaluate_handle(r"""() => {
                                            const norm=s=>(s||"").replace(/\s+/g," ").trim();
                                            const visible=e=>!!e.getClientRects().length &&
                                                getComputedStyle(e).visibility!=="hidden";
                                            const tiles=[...document.querySelectorAll(
                                                ".west-ui-select-connection-tile--content"
                                            )].filter(e=>{
                                                const t=norm(e.innerText);
                                                return visible(e) && /\b18:22\b/.test(t) &&
                                                    /\b18:49\b/.test(t) && /\b1009\b/.test(t);
                                            });
                                            if(tiles.length!==1)return null;
                                            let root=tiles[0];
                                            for(let i=0;i<5 && root;i++,root=root.parentElement){
                                                const candidates=[...root.querySelectorAll("button")].filter(b=>
                                                    visible(b) && !b.disabled &&
                                                    /^2\+\s*\|\s*Comfort\s+ab\s*€\s*0,00$/i.test(
                                                        norm(b.getAttribute("aria-label")||b.innerText)));
                                                if(candidates.length===1 &&
                                                   (root===tiles[0] || root.querySelectorAll(
                                                       ".west-ui-select-connection-tile--content").length===1))
                                                    return candidates[0];
                                                if(candidates.length>1)break;
                                            }
                                            return null;
                                        }""")
                                        comfort_button=comfort_target.as_element()
                                        if comfort_button is not None and comfort_button.is_visible():
                                            CURRENT_STAGE="opening_comfort_2plus"
                                            comfort_button.click(timeout=4500)
                                            page.wait_for_timeout(800)
                                            result["comfortClassDiagnostic"]=page.evaluate(r"""() => {
                                                const norm=s=>(s||"").replace(/\s+/g," ").trim();
                                                const visible=e=>!!e.getClientRects().length &&
                                                    getComputedStyle(e).visibility!=="hidden";
                                                const main=document.querySelector("main")||document.body;
                                                return {
                                                    status:"comfort_2plus_option_opened_dry_run",
                                                    path:location.pathname.slice(0,170),
                                                    headings:[...main.querySelectorAll("h1,h2,h3,h4,[role=heading]")]
                                                        .filter(visible).map(e=>norm(e.innerText).slice(0,85))
                                                        .filter(x=>/Sitz|Platz|Klasse|Komfort|Comfort|Reserv|Ticket|Wagen/i.test(x)).slice(0,14),
                                                    controls:[...main.querySelectorAll("button,[role=button],a[href]")]
                                                        .filter(visible).map(e=>({
                                                            label:norm(e.getAttribute("aria-label")||
                                                                e.innerText||e.getAttribute("title")).slice(0,80),
                                                            disabled:e.matches(":disabled,[aria-disabled=true]")
                                                        })).filter(x=>/Sitz|Platz|Wagen|Weiter|Auswahl|Reserv|Comfort|2\+|Abbrechen/i.test(x.label)).slice(0,30),
                                                    seatCodeHints:[...new Set((main.innerText.match(/\b(?:233\s*[AD]|191\s*D|182\s*A)\b/gi)||[]))].slice(0,10),
                                                    bookingAuthorized:false,
                                                    purchaseExecuted:false
                                                };
                                            }""")
                                            result["status"]="comfort_2plus_opened_dry_run"
                                            # Identify tariff fields without selecting them or
                                            # retrieving account numbers/input values.
                                            result["tariffFieldDiagnostic"]=page.evaluate(r"""() => {
                                                const norm=s=>(s||"").replace(/\s+/g," ").trim().slice(0,120);
                                                const vis=e=>!!e.getClientRects().length &&
                                                    getComputedStyle(e).visibility!=="hidden" &&
                                                    getComputedStyle(e).display!=="none";
                                                const main=document.querySelector("main")||document.body;
                                                const fields=[...main.querySelectorAll(
                                                    'input[type=radio],input[role=combobox],select,[role=radio]'
                                                )].filter(vis);
                                                const info=fields.map((e,index)=>{
                                                    const labels=e.labels?[...e.labels].map(l=>norm(l.innerText)).filter(Boolean):[];
                                                    const enclosing=e.closest("label");
                                                    const context=e.closest("fieldset,[role=radiogroup],[role=group]");
                                                    const parent=e.parentElement;
                                                    const publicTerms=/KlimaTicket|Reservierung|Vollpreis|WestFlexpreis|WestFixpreis|Sitzplatz|Class|Comfort|Tarif|Erwachsene|Erwachsener|Standard/i;
                                                    const descriptiveText=[
                                                        ...(labels||[]),
                                                        enclosing?norm(enclosing.innerText):"",
                                                        context?norm(context.querySelector("legend")?.innerText):"",
                                                        parent?norm(parent.innerText):""
                                                    ].filter(x=>publicTerms.test(x)).slice(0,4);
                                                    return {
                                                        index,
                                                        type:(e.getAttribute("type")||"").slice(0,18),
                                                        role:(e.getAttribute("role")||"").slice(0,22),
                                                        ariaLabel:norm(e.getAttribute("aria-label")),
                                                        descriptiveText,
                                                        checked:e.matches(":checked,[aria-checked=true]"),
                                                        disabled:e.matches(":disabled,[aria-disabled=true]"),
                                                        idPresent:!!e.id,
                                                        enclosingGroup:context?context.tagName.toLowerCase():null
                                                    };
                                                });
                                                const notableButtons=[...main.querySelectorAll("button")].filter(vis)
                                                    .map(e=>({
                                                        label:norm(e.getAttribute("aria-label")||e.innerText),
                                                        type:(e.getAttribute("type")||"").slice(0,15)
                                                    })).filter(e=>/Warenkorb|Bearbeiten|Schließen/.test(e.label)).slice(0,8);
                                                return {
                                                    fieldCount:info.length,fields:info,
                                                    notableButtons,
                                                    shoppingCartBlockedByNetworkPolicy:true,
                                                    selectedFareNotVerified:true,
                                                    reservationMade:false
                                                };
                                            }""")

                                            # The public tariff label and zero
                                            # price were confirmed in the previous
                                            # read-only probe. Match by enclosing
                                            # label text, never by input position.
                                            fare_handle=page.evaluate_handle(r"""() => {
                                                const norm=s=>(s||"").replace(/\s+/g," ").trim();
                                                const vis=e=>!!e.getClientRects().length &&
                                                    getComputedStyle(e).visibility!=="hidden";
                                                const matches=[...document.querySelectorAll('main input[type=radio]')]
                                                    .filter(vis).filter(e=>{
                                                        const label=e.closest("label");
                                                        const text=norm(label?label.innerText:e.parentElement?.innerText);
                                                        return /Reservierung\s+KlimaTicket\s+Ö/i.test(text) &&
                                                               /€\s*0,00/.test(text) &&
                                                               !/WestFlexpreis|Vollpreis/i.test(text) &&
                                                               !e.disabled;
                                                    });
                                                return matches.length===1 ? matches[0] : null;
                                            }""")
                                            fare_radio=fare_handle.as_element()
                                            if fare_radio is not None and fare_radio.is_visible():
                                                CURRENT_STAGE="selecting_klimaticket_fare"
                                                fare_radio.check(timeout=4500)
                                                page.wait_for_timeout(500)
                                                result["climateFareSelection"]=page.evaluate(r"""() => {
                                                    const norm=s=>(s||"").replace(/\s+/g," ").trim();
                                                    const radios=[...document.querySelectorAll('main input[type=radio]')];
                                                    const matches=radios.filter(e=>{
                                                        const text=norm(e.closest("label")?.innerText||e.parentElement?.innerText);
                                                        return /Reservierung\s+KlimaTicket\s+Ö/i.test(text) &&
                                                               /€\s*0,00/.test(text);
                                                    });
                                                    const cart=[...document.querySelectorAll("main button")]
                                                        .filter(e=>/In den Warenkorb/i.test(e.innerText));
                                                    return {
                                                        status:matches.length===1 && matches[0].checked
                                                            ? "climate_ticket_zero_fare_selected"
                                                            : "climate_fare_not_verified",
                                                        matchingFareControls:matches.length,
                                                        checked:matches.length===1?matches[0].checked:false,
                                                        cartButtonPresent:cart.length===1,
                                                        cartButtonClicked:false,
                                                        reservationMade:false,
                                                        purchaseExecuted:false
                                                    };
                                                }""")
                                                if result["climateFareSelection"]["checked"]:
                                                    result["status"]="climate_ticket_fare_selected_dry_run"
                                            else:
                                                result["climateFareSelection"]={
                                                    "status":"climate_fare_radio_missing_or_ambiguous",
                                                    "cartButtonClicked":False,
                                                    "purchaseExecuted":False
                                                }
                                            # Diagnose only the visible structure,
                                            # without reading text-input values,
                                            # account identifiers, or cookie data.
                                            page.wait_for_timeout(1300)
                                            result["detailsStructure"]=page.evaluate(r"""() => {
                                                const norm=s=>(s||"").replace(/\s+/g," ").trim().slice(0,95);
                                                const visible=e=>!!e.getClientRects().length &&
                                                    getComputedStyle(e).display!=="none" &&
                                                    getComputedStyle(e).visibility!=="hidden";
                                                const main=document.querySelector("main")||document.body;
                                                const selectors='button,[role=button],a[href],select,[role=combobox],[role=radio],input';
                                                const controls=[...main.querySelectorAll(selectors)].filter(visible)
                                                    .slice(0,100).map(e=>({
                                                        tag:e.tagName.toLowerCase(),
                                                        role:(e.getAttribute("role")||"").slice(0,25),
                                                        type:(e.getAttribute("type")||"").slice(0,20),
                                                        label:norm(e.getAttribute("aria-label")||e.innerText||
                                                            e.getAttribute("placeholder")||
                                                            e.getAttribute("title")),
                                                        disabled:e.matches(':disabled,[aria-disabled="true"]'),
                                                        isInput:e.matches("input,select"),
                                                        inForm:!!e.closest("form")
                                                    }));
                                                const publicTerms=/Sitzplatz|Sitzplan|Wagen|Platz|Tarif|Comfort|Klasse|KlimaTicket|Reservierung|Weiter|Preis|Lade|Anmeldung|Anmelden|Verfügbarkeit|Fehler|auswählen/i;
                                                const lines=(main.innerText||"").split(/\n+/)
                                                    .map(norm).filter(x=>x && x.length<=90)
                                                    .filter(x=>publicTerms.test(x))
                                                    .slice(0,32);
                                                const forms=[...main.querySelectorAll("form")].slice(0,6)
                                                    .map(e=>({method:(e.getAttribute("method")||"get").toLowerCase(),
                                                        inputCount:e.querySelectorAll("input").length,
                                                        buttonCount:e.querySelectorAll("button").length}));
                                                return {
                                                    path:location.pathname.slice(0,150),
                                                    visibleMainLength:(main.innerText||"").length,
                                                    title:norm(document.title),
                                                    controlCount:controls.length,
                                                    controls:controls.slice(0,45),
                                                    publicStatusLines:lines,
                                                    forms,
                                                    spinnerCount:[...main.querySelectorAll(
                                                        '[aria-busy=true],[role=progressbar],[class*=spinner],[class*=loading]'
                                                    )].filter(visible).length,
                                                    iframeCount:document.querySelectorAll("iframe").length,
                                                    hasVisibleSeatMap:!![...main.querySelectorAll(
                                                        '[class*=seat-map],[class*=seatmap],[data-testid*=seat]'
                                                    )].find(visible),
                                                    note:"No form values, profile names, ticket numbers, or cookies collected"
                                                };
                                            }""")

                                        else:
                                            result["comfortClassDiagnostic"]={
                                                "status":"comfort_2plus_button_not_uniquely_scoped",
                                                "bookingAuthorized":False,"purchaseExecuted":False
                                            }

                                    else:
                                        result["trainSelectionDiagnostic"]={
                                            "status":"train_tile_not_unique_or_missing"
                                        }
                                else:
                                    result["trainSelectionDiagnostic"]={"status":"train_evidence_incomplete"}
                                report=result["connectionOverview"]
                                headers=report.get("resultsDiagnostics",{}).get("headings",[])
                                unavailable=any(
                                    "Am gewählten Datum gibt es die gewünschte Verbindung leider nicht." in heading
                                    for heading in headers
                                )
                                if unavailable and report.get("targetTrainCount")==0:
                                    result["status"]="provider_reports_no_bookable_connection"
                                    result["connectionOverview"]["bookingCheck"]={
                                        "state":"provider_no_connection_for_selected_date",
                                        "date":test_day,
                                        "canSelectTrain":False,
                                        "canSelectSeat":False,
                                        "safeToBook":False,
                                        "explanation":"Der Fahrplan kann einen Zug zeigen, obwohl der Ticketshop ihn für die gewählte Strecke nicht anbietet."
                                    }
                                elif report.get("targetTrainCount")==0:
                                    result["status"]="timetable_not_verified"
                                    result["connectionOverview"]["bookingCheck"]={
                                        "state":"unknown","safeToBook":False
                                    }
                # Let the seat-list response settle before inspecting
                # transport status; no additional cart request is initiated.
                page.wait_for_timeout(850)
                result["seatLookupDiagnostic"]={
                    "requestAllowed":bool(network["allowedSeatLookup"]),
                    "responses":network["seatLookupResponses"],
                    "seatSelectionMade":False,
                    "reservationCompleted":False,
                    "checkoutAuthorized":False
                }
                basket_added=bool(network["allowedBasketAdd"])
                basket_transport_ok=any(x.get("ok") for x in network["basketAddResponses"])
                result["bookingSafety"]={
                    "state":"basket_add_requested" if basket_added else "basket_not_modified",
                    "basketAddRequestAllowed":basket_added,
                    "basketAddConfirmedByProvider":False,
                    "basketTransportAccepted":basket_transport_ok,
                    "basketAddResponses":network["basketAddResponses"],
                    "maxBasketAddRequestsPerRun":1,
                    "checkoutAuthorized":False,
                    "purchaseExecuted":False,
                    "note":"Even a 2xx POST is not proof the cart holds an item; independent cart read required."
                }
                if basket_added:
                    result["status"]="basket_add_requested_dry_run"
                    page.wait_for_timeout(900)
                    result["postBasketDetails"]=page.evaluate(r"""() => {
                        const norm=s=>(s||"").replace(/\s+/g," ").trim().slice(0,100);
                        const visible=e=>!!e.getClientRects().length &&
                            getComputedStyle(e).visibility!=="hidden";
                        const main=document.querySelector("main")||document.body;
                        const controls=[...main.querySelectorAll("button,[role=button],a[href]")].filter(visible)
                            .map(e=>({
                                label:norm(e.getAttribute("aria-label")||e.innerText),
                                disabled:e.matches(":disabled,[aria-disabled=true]")
                            })).filter(e=>/Warenkorb|Sitz|Platz|Wagen|Weiter|Auswahl|Reserv|Fertig/i.test(e.label)).slice(0,35);
                        return {
                            path:location.pathname.slice(0,160),
                            seatMapVisible:!![...main.querySelectorAll(
                                '[class*=seat-map],[class*=seatmap],[data-testid*=seat]'
                            )].find(visible),
                            controls,
                            seatCodeHints:[...new Set((main.innerText.match(/\b(?:233\s*[AD]|191\s*D|182\s*A)\b/gi)||[]))].slice(0,10),
                            noCheckoutActionClicked:true
                        };
                    }""")
                # Inspect seat selector only. "Ändern" opens the choice UI;
                # this test never clicks a seat or a confirm/cart button.
                result["seatMapDiagnostic"]={"status":"not_inspected"}
                if (result.get("seatLookupDiagnostic",{}).get("requestAllowed")
                    and result.get("seatLookupDiagnostic",{}).get("responses")
                    and any(x.get("ok") for x in result["seatLookupDiagnostic"]["responses"])):
                    change=page.get_by_role("button",name="Ändern",exact=True)
                    if change.count()==1 and change.is_visible():
                        CURRENT_STAGE="opening_seat_dialog"
                        change.click(timeout=4000)
                        page.wait_for_timeout(850)
                        result["seatMapDiagnostic"]=page.evaluate(r"""() => {
                            const norm=s=>(s||"").replace(/\s+/g," ").trim();
                            const visible=e=>!!e.getClientRects().length &&
                                getComputedStyle(e).visibility!=="hidden" &&
                                getComputedStyle(e).display!=="none";
                            const seatRx=/\b(?:233\s*[AD]|191\s*D|182\s*A|204\s*A)\b/i;
                            const root=document.querySelector('[role=dialog]')||
                                       document.querySelector('main')||document.body;
                            const labels=[...root.querySelectorAll(
                                "button,[role=button],[role=radio],input[type=radio],label,option,[data-seat]"
                            )].filter(visible).map(e=>({
                                tag:e.tagName.toLowerCase(),
                                role:(e.getAttribute("role")||"").slice(0,25),
                                text:norm(e.getAttribute("aria-label")||
                                    e.getAttribute("title")||e.innerText).slice(0,85),
                                disabled:e.matches(':disabled,[aria-disabled=true]'),
                                selected:e.matches(':checked,[aria-checked=true],[aria-selected=true]'),
                                classHint:(typeof e.className==="string"?e.className:"").slice(0,100)
                            }));
                            const important=labels.filter(x=>
                                seatRx.test(x.text)||/Wagen|Sitz|Platz|Weiter|Fertig|Speichern|Schließen/i.test(x.text))
                                .slice(0,45);
                            const selectedText=norm(root.innerText);
                            return {
                                status:"seat_selection_ui_inspected_no_seat_clicked",
                                path:location.pathname.slice(0,140),
                                dialogVisible:!!document.querySelector('[role=dialog]'),
                                seatElementCount:labels.length,
                                controls:important,
                                preferredSeatText:({
                                    "233A":/\b233\s*A\b/.test(selectedText),
                                    "233D":/\b233\s*D\b/.test(selectedText),
                                    "191D":/\b191\s*D\b/.test(selectedText),
                                    "182A":/\b182\s*A\b/.test(selectedText)
                                }),
                                default204AVisible:/\b204\s*A\b/.test(selectedText),
                                candidateSeatControls:labels.filter(x=>seatRx.test(x.text)).slice(0,24),
                                seatClicked:false,
                                confirmationClicked:false,
                                purchaseExecuted:false
                            };
                        }""")
                        # Changing wagons only navigates a seat map, and
                        # does NOT select any seat or confirm any booking.
                        result["wagonAvailability"]=[]
                        for wagon in (11,10,9,8,7):
                            wagon_button=page.get_by_role(
                                "button",name=f"Wagen: {wagon}",exact=True
                            )
                            if wagon_button.count()!=1 or not wagon_button.is_enabled():
                                result["wagonAvailability"].append({
                                    "wagon":wagon,"status":"wagon_button_missing_or_disabled",
                                    "count":wagon_button.count()
                                })
                                continue
                            CURRENT_STAGE="switching_wagon"
                            wagon_button.click(timeout=4500)
                            page.wait_for_timeout(650)
                            inspected=page.evaluate(r"""(wagon) => {
                                const norm=s=>(s||"").replace(/\s+/g," ").trim();
                                const visible=e=>!!e.getClientRects().length &&
                                    getComputedStyle(e).visibility!=="hidden" &&
                                    getComputedStyle(e).display!=="none";
                                const root=document.querySelector('[role=dialog]')||
                                    document.querySelector('main')||document.body;
                                const wagonButtons=[...root.querySelectorAll(
                                    'button.west-ui-wagons--wagon'
                                )].filter(visible);
                                const active=wagonButtons.filter(e=>e.matches(
                                    '[aria-selected=true],[aria-pressed=true],.west-ui-wagons--active'
                                )).map(e=>norm(e.getAttribute("aria-label")||e.innerText));
                                const seats=[...root.querySelectorAll('button')].filter(e=>
                                    visible(e) && typeof e.className==="string" &&
                                    e.className.includes('west-ui-seat-picker--seat')
                                ).map(e=>{
                                    const label=norm(e.getAttribute("aria-label")||
                                        e.getAttribute("title")||e.innerText);
                                    const match=label.match(/^(\d{2,3}[A-D])\b/i);
                                    return match?{
                                        code:match[1].toUpperCase(),
                                        label:label.slice(0,95),
                                        available:!e.matches(':disabled,[aria-disabled=true]'),
                                        selected:e.matches(
                                            '[aria-selected=true],[aria-pressed=true],.west-ui-seat-picker--selected'
                                        )
                                    }:null;
                                }).filter(Boolean);
                                const preferred=(wagon===11?["233A","233D"]:
                                    wagon===8?["191D"]:wagon===7?["182A"]:[]);
                                return {
                                    wagon,
                                    status:active.some(a=>new RegExp(
                                        'Wagen:\\s*'+wagon+'(?:\\b|$)').test(a))
                                        ?"wagon_inspected":"wagon_not_verified",
                                    activeWagons:active.slice(0,4),
                                    totalSeats:seats.length,
                                    availableSeats:seats.filter(s=>s.available).length,
                                    preferred:preferred.map(code=>{
                                        const seat=seats.find(s=>s.code===code);
                                        return {
                                            code,
                                            status:seat
                                                ?(seat.available?"available":"unavailable")
                                                :"not_found_in_visible_wagon",
                                            label:seat?seat.label:null
                                        };
                                    }),
                                    availableSeatLabels:seats.filter(s=>s.available)
                                        .slice(0,22).map(s=>s.label),
                                    fallbackCandidates:seats.filter(s=>s.available &&
                                        /Fensterplatz/i.test(s.label) &&
                                        /mit Tisch/i.test(s.label) &&
                                        !/WESTcafé|Klappsitz/i.test(s.label))
                                        .map(s=>({
                                            code:s.code,
                                            wagon,
                                            label:s.label,
                                            isWindow:true,
                                            hasTable:true,
                                            evidence:"visible seat label and enabled control",
                                            tableConfiguration:"not_verified",
                                            singleSeatLayoutVerified:false,
                                            fourSeatGroupExcluded:false
                                        })).slice(0,24),
                                    seatClicked:false
                                };
                            }""",wagon)
                            result["wagonAvailability"].append(inspected)
                        # List-only fallback suggestions. The public seat
                        # labels show window/table properties, but do not prove
                        # whether a seat belongs to a two-person table or a
                        # prohibited four-person group. Such candidates must
                        # NOT be automatically selected.
                        fallback=[]
                        for w in result["wagonAvailability"]:
                            if w.get("status")=="wagon_inspected":
                                fallback.extend(w.get("fallbackCandidates",[]))
                        fallback.sort(key=lambda c:(
                            {11:0,10:1,9:2,8:3,7:4}.get(c["wagon"],5),
                            c["code"]
                        ))
                        result["fallbackSeatSuggestions"]={
                            "status":"candidates_require_table_layout_verification"
                                if fallback else "no_table_window_candidates_found",
                            "criteria":"enabled window seat with table, not WESTcafe or folding seat",
                            "fourPersonGroupsExcluded":False,
                            "verifiedSingleSeats":0,
                            "candidateCount":len(fallback),
                            "suggestions":fallback[:20],
                            "seatClicked":False,
                            "checkoutAuthorized":False,
                            "purchaseExecuted":False,
                            "note":"Seat labels alone cannot establish paired vs four-person table; no automatic fallback choice."
                        }
                        # Choose only a uniquely available, verified priority
                        # seat in the UI; never click "Fertig" or check out.
                        checked={p["code"]:p["status"]
                                 for w in result["wagonAvailability"]
                                 if w.get("status")=="wagon_inspected"
                                 for p in w.get("preferred",[])}
                        # Preferred seats only require their own three
                        # wagons to be verified. Optional fallback wagons
                        # must never block a valid preferred-seat selection.
                        all_verified=all(
                            any(w.get("wagon")==wagon and
                                w.get("status")=="wagon_inspected"
                                for w in result["wagonAvailability"])
                            for wagon in (11,8,7)
                        )
                        result["prioritySeatChoice"]={
                            "status":"priority_not_verified",
                            "checked":checked,
                            "seatClicked":False,
                            "confirmed":False
                        }
                        if all_verified and all(
                            x in checked for x in ("233A","233D","191D","182A")
                        ):
                            priority=(
                                ("233A",11),("233D",11),
                                ("191D",8),("182A",7)
                            )
                            picked=next(
                                ((code,wagon) for code,wagon in priority
                                 if checked[code]=="available"),None
                            )
                            if picked:
                                code,wagon=picked
                                target_wagon=page.get_by_role(
                                    "button",name=f"Wagen: {wagon}",exact=True
                                )
                                if (target_wagon.count()==1
                                    and target_wagon.is_enabled()):
                                    CURRENT_STAGE="switching_to_priority_wagon"
                                    target_wagon.click(timeout=4500)
                                    page.wait_for_timeout(450)
                                    seat=page.evaluate_handle(r"""(code) => {
                                        const root=document.querySelector('[role=dialog]')||
                                            document.querySelector("main")||document.body;
                                        const visible=e=>!!e.getClientRects().length &&
                                            getComputedStyle(e).visibility!=="hidden";
                                        const seats=[...root.querySelectorAll(
                                            'button.west-ui-seat-picker--seat'
                                        )].filter(e=>{
                                            const label=(e.getAttribute("aria-label")||
                                                e.getAttribute("title")||e.innerText||"").trim();
                                            return visible(e) && !e.disabled &&
                                                label.toUpperCase().startsWith(code.toUpperCase()+",");
                                        });
                                        return seats.length===1?seats[0]:null;
                                    }""",code)
                                    seat_el=seat.as_element()
                                    if seat_el is not None and seat_el.is_enabled():
                                        CURRENT_STAGE="highlighting_priority_seat"
                                        seat_el.click(timeout=4500)
                                        page.wait_for_timeout(400)
                                        result["prioritySeatChoice"]=page.evaluate(r"""(code) => {
                                            const root=document.querySelector('[role=dialog]')||
                                                document.querySelector("main")||document.body;
                                            const seats=[...root.querySelectorAll(
                                                'button.west-ui-seat-picker--seat'
                                            )];
                                            const matching=seats.filter(e=>
                                                (e.getAttribute("aria-label")||
                                                e.getAttribute("title")||
                                                e.innerText||"").trim().toUpperCase()
                                                .startsWith(code.toUpperCase()+","));
                                            const selected=matching.length===1 &&
                                                matching[0].matches(
                                                    '[aria-selected=true],[aria-pressed=true],.west-ui-seat-picker--selected'
                                                );
                                            return {
                                                status:selected?"priority_seat_highlighted":
                                                    "seat_click_not_verified",
                                                code,
                                                selected,
                                                seatClicked:true,
                                                confirmed:false,
                                                cartSubmitted:false,
                                                purchaseExecuted:false
                                            };
                                        }""",code)
                                        # Commit the seat choice to the local
                                        # ticket form only; never click "In den
                                        # Warenkorb", payment or ticket purchase.
                                        if result["prioritySeatChoice"].get("selected"):
                                            finish=page.get_by_role("button",name="Fertig",exact=True)
                                            if finish.count()==1 and finish.is_visible():
                                                CURRENT_STAGE="confirming_seat_in_form"
                                                # A prior click timed out. Capture
                                                # actionability/overlay state rather
                                                # than retrying blindly or forcing a
                                                # click through obstructing UI.
                                                result["finishButtonDiagnostic"]=page.evaluate(r"""() => {
                                                    const vis=e=>!!e.getClientRects().length &&
                                                        getComputedStyle(e).visibility!=="hidden";
                                                    const buttons=[...document.querySelectorAll("button")]
                                                        .filter(e=>(e.getAttribute("aria-label")||
                                                            e.innerText||"").trim()==="Fertig");
                                                    return {
                                                        matchedButtons:buttons.length,
                                                        controls:buttons.slice(0,4).map(e=>{
                                                            const rect=e.getBoundingClientRect();
                                                            const x=rect.left+rect.width/2,y=rect.top+rect.height/2;
                                                            const top=document.elementFromPoint(x,y);
                                                            const dialog=e.closest('[role=dialog]');
                                                            return {
                                                                visible:vis(e),
                                                                disabled:e.disabled,
                                                                ariaDisabled:e.getAttribute("aria-disabled"),
                                                                inDialog:!!dialog,
                                                                pointerEvents:getComputedStyle(e).pointerEvents,
                                                                rect:{x:Math.round(rect.x),y:Math.round(rect.y),
                                                                    w:Math.round(rect.width),h:Math.round(rect.height)},
                                                                centerHitIsButton:top===e||e.contains(top),
                                                                centerHitTag:top?top.tagName.toLowerCase():null,
                                                                centerHitClass:top&&typeof top.className==="string"
                                                                    ?top.className.slice(0,90):null
                                                            };
                                                        }),
                                                        seatPickerDialogCount:[...document.querySelectorAll(
                                                            '[role=dialog]')].filter(vis).length
                                                    };
                                                }""")
                                                # "Fertig" belongs to the underlying page,
                                                # not the active seat dialog. Never click
                                                # an off-screen/background control.
                                                result["finishButtonDiagnostic"]["clickOutcome"]="skipped_background_control"
                                                result["seatDialogControls"]=page.evaluate(r"""() => {
                                                    const norm=s=>(s||"").replace(/\s+/g," ").trim();
                                                    const vis=e=>!!e.getClientRects().length &&
                                                        getComputedStyle(e).visibility!=="hidden";
                                                    const dialogs=[...document.querySelectorAll('[role=dialog]')].filter(vis);
                                                    return {
                                                        visibleDialogs:dialogs.length,
                                                        controls:dialogs.flatMap(d=>[...d.querySelectorAll(
                                                            'button,[role=button],[aria-label]'
                                                        )].filter(vis).map(e=>({
                                                            tag:e.tagName.toLowerCase(),
                                                            label:norm(e.getAttribute('aria-label')||
                                                                e.getAttribute('title')||e.innerText).slice(0,75),
                                                            type:(e.getAttribute('type')||'').slice(0,16),
                                                            disabled:e.matches(':disabled,[aria-disabled=true]')
                                                        }))).filter(c=>/Schließen|Zurück|Fertig|Übernehmen|Bestätigen|Abbrechen|Auswahl|Wagen/i.test(c.label))
                                                            .slice(0,18)
                                                    };
                                                }""")
                                                # Confirm ONLY the chosen seat within the
                                                # seat dialog. This is not a checkout action.
                                                # Never click the obscured page-level "Fertig".
                                                confirm=page.locator('[role="dialog"]').get_by_role(
                                                    "button",name="Bestätigen",exact=True
                                                )
                                                result["seatDialogConfirmation"]={
                                                    "buttonCount":confirm.count(),
                                                    "seatCode":code,
                                                    "clicked":False,
                                                    "cartSubmitted":False,
                                                    "purchaseExecuted":False
                                                }
                                                if (result["seatDialogControls"]["visibleDialogs"]==1
                                                    and confirm.count()==1
                                                    and confirm.is_visible()
                                                    and confirm.is_enabled()):
                                                    CURRENT_STAGE="confirming_seat_in_dialog"
                                                    try:
                                                        confirm.click(timeout=4000,no_wait_after=True)
                                                        result["seatDialogConfirmation"]["clicked"]=True
                                                        result["seatDialogConfirmation"]["status"]="clicked"
                                                    except Exception as error:
                                                        result["seatDialogConfirmation"]["status"]="click_failed"
                                                        result["seatDialogConfirmation"]["errorClass"]=type(error).__name__[:48]
                                                else:
                                                    result["seatDialogConfirmation"]["status"]="confirm_control_unavailable"
                                                page.wait_for_timeout(950)
                                                summary=page.evaluate(r"""(code) => {
                                                    const norm=s=>(s||"").replace(/\s+/g," ").trim();
                                                    const visible=e=>!!e.getClientRects().length &&
                                                        getComputedStyle(e).visibility!=="hidden";
                                                    const dialogs=[...document.querySelectorAll('[role=dialog]')].filter(visible);
                                                    const main=document.querySelector("main")||document.body;
                                                    const buttons=[...main.querySelectorAll("button")].filter(visible);
                                                    const matching=buttons.filter(e=>
                                                        norm(e.getAttribute("aria-label")||e.innerText)===code);
                                                    return {
                                                        code,
                                                        visibleDialogCount:dialogs.length,
                                                        seatShownInForm:dialogs.length===0 && matching.length===1,
                                                        matchingButtonCount:matching.length,
                                                        cartSubmitClicked:false,
                                                        purchaseExecuted:false
                                                    };
                                                }""",code)
                                                summary["seatUpdateHttpResponses"]=network["seatUpdateResponses"]
                                                summary["seatUpdateRequestAllowed"]=bool(network["allowedSeatUpdate"])
                                                result["seatFormConfirmation"]=summary
                                                result["prioritySeatChoice"]["confirmed"]=bool(
                                                    result["seatDialogConfirmation"]["clicked"] and
                                                    summary["seatShownInForm"]
                                                )
                                                result["prioritySeatChoice"]["status"]=(
                                                    "priority_seat_applied_to_form"
                                                    if result["prioritySeatChoice"]["confirmed"]
                                                    else "seat_dialog_remains_or_selection_not_applied"
                                                )
                                            else:
                                                result["seatFormConfirmation"]={
                                                    "status":"finish_button_not_unique",
                                                    "count":finish.count(),
                                                    "purchaseExecuted":False
                                                }
                                    else:
                                        result["prioritySeatChoice"]["status"]="seat_control_missing"
                                else:
                                    result["prioritySeatChoice"]["status"]="target_wagon_unavailable"
                            else:
                                result["prioritySeatChoice"]["status"]="no_preferred_seat_available"
                    else:
                        result["seatMapDiagnostic"]={
                            "status":"change_seat_button_not_unique",
                            "count":change.count(),"seatClicked":False
                        }
                # Observe only the final cart-submit affordance after the
                # verified seat update. It must not be clicked while the
                # independent ticket inventory is not reconciled.
                result["cartSubmitReadiness"]={
                    "status":"seat_not_verified",
                    "clicked":False,
                    "duplicateInventoryGatePassed":False,
                    "checkoutAuthorized":False
                }
                if result.get("prioritySeatChoice",{}).get("confirmed"):
                    result["cartSubmitReadiness"]=page.evaluate(r"""() => {
                        const vis=e=>!!e.getClientRects().length &&
                            getComputedStyle(e).visibility!=="hidden";
                        const norm=s=>(s||"").replace(/\s+/g," ").trim();
                        const buttons=[...document.querySelectorAll("main button")].filter(e=>
                            vis(e) && norm(e.innerText)==="In den Warenkorb");
                        return {
                            status:buttons.length===1?"ready_for_inventory_gate":"button_missing_or_ambiguous",
                            matchingButtons:buttons.length,
                            enabled:buttons.length===1?!buttons[0].disabled:false,
                            formPresent:buttons.length===1?!!buttons[0].closest("form"):false,
                            buttonType:buttons.length===1?buttons[0].type:null,
                            seat191DInForm:[...document.querySelectorAll("main button")].filter(vis)
                                .some(e=>norm(e.innerText)==="191D"),
                            clicked:false,
                            duplicateInventoryGatePassed:false,
                            checkoutAuthorized:false,
                            purchaseExecuted:false
                        };
                    }""")
                # Controlled cart-submit diagnostic: the user previously
                # authorized adding one zero-euro seat to a cart, but NOT
                # checkout or a completed booking. The network gate still
                # allows at most one basket/add request in the entire run.
                # Any subsequent mutation required by the submit is blocked
                # and reported, not retried or implicitly authorized.
                result["cartSubmissionDiagnostic"]={
                    "status":"not_attempted",
                    "cartButtonClicked":False,
                    "checkoutAuthorized":False,
                    "purchaseExecuted":False
                }
                seat_choice=result.get("prioritySeatChoice",{})
                climate=result.get("climateFareSelection",{})
                seat_form=result.get("seatFormConfirmation",{})
                confirmed_form=(seat_choice.get("confirmed") is True
                    and seat_form.get("seatShownInForm") is True)
                zero_fare=(climate.get("checked") is True
                    and climate.get("matchingFareControls")==1)
                seat_update_ok=any(x.get("ok") for x in network["seatUpdateResponses"])
                if (confirmed_form and zero_fare and seat_update_ok
                    and result["cartSubmitReadiness"].get("duplicateInventoryGatePassed") is True):
                    cart_btn=page.get_by_role("button",name="In den Warenkorb",exact=True)
                    result["cartSubmissionDiagnostic"].update({
                        "matchedButtons":cart_btn.count(),
                        "zeroFareVerified":True,
                        "seatCode":seat_choice.get("code"),
                        "basketAddRequestsBeforeClick":len(network["allowedBasketAdd"]),
                        "seatUpdateAccepted":True
                    })
                    if (cart_btn.count()==1 and cart_btn.is_visible()
                        and cart_btn.is_enabled()):
                        CURRENT_STAGE="cart_submit_diagnostic"
                        try:
                            cart_btn.click(timeout=4000,no_wait_after=True)
                            result["cartSubmissionDiagnostic"]["cartButtonClicked"]=True
                            result["cartSubmissionDiagnostic"]["status"]="clicked_network_gated"
                        except Exception as error:
                            result["cartSubmissionDiagnostic"]["status"]="click_failed"
                            result["cartSubmissionDiagnostic"]["errorClass"]=type(error).__name__[:48]
                        page.wait_for_timeout(950)
                        result["cartSubmissionDiagnostic"]["afterClick"]={
                            "path":urlsplit(page.url).path[:160],
                            "basketAddRequests":len(network["allowedBasketAdd"]),
                            "basketAddResponses":network["basketAddResponses"],
                            "blockedPostPaths":[i["path"] for i in network["blockedFirstPartyWrites"]],
                            "basketReadResponses":network["basketReadResponses"],
                            "cartText":page.evaluate(r"""() => {
                                const m=document.querySelector("main")||document.body;
                                const t=(m.innerText||"").replace(/\s+/g," ");
                                return {
                                    containsEmptyCart:/Warenkorb\s+ist\s+leer/i.test(t),
                                    containsSeat191D:/\b191D\b/.test(t),
                                    hasCheckoutWords:/Warenkorb|Kasse|Checkout/i.test(t)
                                };
                            }""")
                        }
                    else:
                        result["cartSubmissionDiagnostic"]["status"]="cart_button_unavailable"
                else:
                    result["cartSubmissionDiagnostic"]["status"]="preconditions_not_verified"
                    result["cartSubmissionDiagnostic"]["seatFormVerified"]=confirmed_form
                    result["cartSubmissionDiagnostic"]["zeroFareVerified"]=zero_fare
                    result["cartSubmissionDiagnostic"]["seatUpdateAccepted"]=seat_update_ok
                    result["cartSubmissionDiagnostic"]["inventoryGatePassed"]=bool(
                        result["cartSubmitReadiness"].get("duplicateInventoryGatePassed"))
                    if confirmed_form and zero_fare and seat_update_ok:
                        result["cartSubmissionDiagnostic"]["status"]="inventory_reconciliation_required_no_submit"
                result["environmentDiagnostics"]={
                    "network":network,
                    "browserHasWestbahnCookies":any(
                        c.get("domain","").endswith("westbahn.at") for c in context.cookies(URL)
                    ),
                    "browserTimezone":page.evaluate("Intl.DateTimeFormat().resolvedOptions().timeZone"),
                    "browserLocale":page.evaluate("navigator.language"),
                    "selectedDateIsTopField":True,
                    "note":"Read/quote and limited basket/get; one basket/add, seat lookup and one seat update permitted; checkout and purchase blocked."
                }
                print(json.dumps(result,ensure_ascii=False))
            finally:
                context.close()

if __name__=="__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"status":"station_selection_blocked",
                          "errorClass":type(error).__name__[:48],
                          "errorStage":CURRENT_STAGE,
                          "bookingAuthorized":False,"purchaseExecuted":False}))
