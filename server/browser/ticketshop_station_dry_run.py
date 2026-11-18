#!/usr/bin/env python3
"""Select the two WESTbahn stations in a safe non-checkout browser dry run.

Only exact matching station suggestions may be selected. This does not
select dates, train, fare, seats, cart, payment, or booking controls.
Network POST/PUT/PATCH/DELETE are blocked.
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
            args={"headless":True,"accept_downloads":False,"timeout":20000}
            if os.environ.get("WESTBAHN_CHROMIUM_PATH"):
                args["executable_path"]=os.environ["WESTBAHN_CHROMIUM_PATH"]
            context=p.chromium.launch_persistent_context(str(root/"chromium"),**args)
            try:
                def guard(route):
                    req=route.request
                    if req.method.upper() not in ("GET","HEAD"):
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
                                        note:"Observed timetable content only; no live availability or booking authorization."
                                    };
                                }""")
                print(json.dumps(result,ensure_ascii=False))
            finally:
                context.close()

if __name__=="__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"status":"station_selection_blocked",
                          "errorClass":type(error).__name__[:48],
                          "bookingAuthorized":False,"purchaseExecuted":False}))
