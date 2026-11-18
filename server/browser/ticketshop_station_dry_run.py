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
                    # Open the explicitly named date editor for structural
                    # inspection only; never choose a date or submit a search.
                    editor=page.get_by_role("button",name="Hinfahrt Datum bearbeiten",exact=True)
                    if editor.count()!=1 or not editor.is_visible():
                        result["datePicker"]={"status":"editor_missing_or_ambiguous",
                                              "count":editor.count()}
                    else:
                        editor.click(timeout=4000)
                        page.wait_for_timeout(400)
                        result["datePicker"]=page.evaluate(r"""() => {
                            const norm=s=>(s||"").replace(/\s+/g," ").trim().slice(0,75);
                            const visible=e=>!!e.getClientRects().length &&
                                getComputedStyle(e).visibility!=="hidden" &&
                                getComputedStyle(e).display!=="none";
                            const dialogs=[...document.querySelectorAll(
                                '[role=dialog],[role=grid],[role=application]'
                            )].filter(visible);
                            const labelled=[...document.querySelectorAll(
                                '[role=gridcell],button,[role=button],[role=option],select,input'
                            )].filter(visible).slice(0,200).map(e=>({
                                tag:e.tagName.toLowerCase(),
                                role:(e.getAttribute('role')||'').slice(0,18),
                                type:(e.getAttribute('type')||'').slice(0,18),
                                label:norm(e.getAttribute('aria-label')||e.innerText||
                                    e.getAttribute('placeholder')||e.getAttribute('title')),
                                disabled:e.matches(':disabled,[aria-disabled=true]')
                            })).filter(x=>x.label && (
                                /^(?:\d{1,2}|Mo|Di|Mi|Do|Fr|Sa|So|Jan|Feb|Mär|Apr|Mai|Jun|Jul|Aug|Sep|Okt|Nov|Dez)/i.test(x.label)||
                                /Kalender|Monat|Datum|Weiter|Zurück|Heute|November|Dezember/i.test(x.label)
                            )).slice(0,35);
                            return {status:"calendar_inspected_no_date_selected",
                                    visibleDialogs:dialogs.length,
                                    candidateControls:labelled};
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
