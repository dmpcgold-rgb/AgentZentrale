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
                    # Autocomplete implementations can use listbox options,
                    # or a menu of buttons. Prefer semantic listbox controls.
                    opts=page.get_by_role("option",name=target,exact=True)
                    if opts.count()==1 and opts.is_visible():
                        opts.click(timeout=4000)
                        result["steps"].append({"field":name,"status":"suggestion_selected",
                                                 "requested":target})
                        continue
                    # Never press Enter blindly: it might submit a booking form.
                    result["status"]="station_selection_blocked"
                    result["steps"].append({"field":name,"status":"suggestion_not_unique",
                                             "requested":target,"matchingOptions":opts.count(),
                                             "listboxes":page.get_by_role("listbox").count()})
                    break
                if len(result["steps"])==2 and all(x["status"]=="suggestion_selected" for x in result["steps"]):
                    result["status"]="stations_selected_dry_run"
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
