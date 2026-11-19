#!/usr/bin/env python3
"""Select the two WESTbahn stations in a safe non-checkout browser dry run.

Only exact matching station suggestions may be selected. This does not
select dates, train, fare, seats, cart, payment, or booking controls.
Only exact first-party read/quote endpoints and one basket/add POST are allowed. Checkout, purchase and other writes remain blocked.
"""
import fcntl
import json
import os
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

URL = "https://westbahn.at/ticketshop/ticket-buchen/"
ORIGIN = "Wien Meidling"
DESTINATION = "Wiener Neustadt Hbf"
CURRENT_STAGE = "startup"
# Explicit user-authorized fallback seats (order preserved); 191D remains
# in the higher-priority preferred set, so it is not tried twice.
AUTHORIZED_FALLBACK_SEATS = [["231D",11], ["222D",11], ["222A",11], ["221A",11], ["221D",11], ["230D",11], ["213D",10], ["212D",10], ["210A",10], ["210D",10], ["209A",10], ["209D",10], ["206D",9], ["205D",9], ["204D",9], ["203D",9], ["202D",9], ["195D",9], ["194D",9], ["191D",8], ["190D",8]]


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
        # Never erase or reuse the original approval marker. One separate
        # recovery attempt is permitted only with the owner's explicit
        # no-ticket attestation and a one-off recovery flag.
        prior_approval=root/"approval_attempt_20261120.flag"
        recovery_marker=root/"approval_attempt_20261120_recovery1.flag"
        final_recovery_marker=root/"approval_attempt_20261120_recovery2.flag"
        third_recovery_marker=root/"approval_attempt_20261120_recovery3.flag"
        # Explicitly one additional attempt after the original and both recoveries.
        third_recovery_requested=(
            os.environ.get("WESTBAHN_THIRD_RECOVERY_AFTER_NO_TICKET_20261120")=="1"
            and os.environ.get("WESTBAHN_USER_ATTESTED_NO_DUPLICATE_20261120")=="1"
            and os.environ.get("WESTBAHN_AUTHORIZE_ZERO_EUR_PURCHASE_20261120")=="1"
        )
        final_recovery_requested=(
            os.environ.get("WESTBAHN_FINAL_RECOVERY_AFTER_NO_TICKET_20261120")=="1"
            and os.environ.get("WESTBAHN_USER_ATTESTED_NO_DUPLICATE_20261120")=="1"
            and os.environ.get("WESTBAHN_AUTHORIZE_ZERO_EUR_PURCHASE_20261120")=="1"
        )
        recovery_requested=(
            os.environ.get("WESTBAHN_RECOVERY_AFTER_NO_TICKET_20261120")=="1"
            and os.environ.get("WESTBAHN_USER_ATTESTED_NO_DUPLICATE_20261120")=="1"
            and os.environ.get("WESTBAHN_AUTHORIZE_ZERO_EUR_PURCHASE_20261120")=="1"
        )
        if ((root/"checkout_attempt_20261120.flag").exists()
            or third_recovery_marker.exists()
            or (final_recovery_marker.exists() and not third_recovery_requested)
            or (recovery_marker.exists() and not final_recovery_requested
                and not third_recovery_requested)
            or (prior_approval.exists() and not recovery_requested
                and not final_recovery_requested and not third_recovery_requested)):
            print(json.dumps({
                "status":"previous_approval_attempt_requires_inventory_check",
                "reason":"checkout_already_attempted"
                    if (root/"checkout_attempt_20261120.flag").exists()
                    else ("third_recovery_already_attempted"
                          if third_recovery_marker.exists()
                          else "recovery_not_authorized_or_already_attempted"),
                "newSeatSelectionBlocked":True,
                "newBasketApprovalBlocked":True,
                "purchaseExecuted":False
            }))
            return
        with sync_playwright() as p:
            args={"headless":True,"accept_downloads":False,"timeout":20000,
                  "locale":"de-AT","timezone_id":"Europe/Vienna"}
            if os.environ.get("WESTBAHN_CHROMIUM_PATH"):
                args["executable_path"]=os.environ["WESTBAHN_CHROMIUM_PATH"]
            context=p.chromium.launch_persistent_context(str(root/"chromium"),**args)
            try:
                # Approval can be a binding reservation. The opt-in is one-day only.
                # A durable marker prevents a second attempt even after a crash.
                approval_marker=(
                    third_recovery_marker
                    if final_recovery_marker.exists() and third_recovery_requested
                    else final_recovery_marker
                    if recovery_marker.exists() and final_recovery_requested
                    else recovery_marker
                    if prior_approval.exists() and recovery_requested
                    else prior_approval
                )
                purchase_opt_in=(
                    os.environ.get("WESTBAHN_AUTHORIZE_ZERO_EUR_PURCHASE_20261120")=="1"
                    and os.environ.get("WESTBAHN_USER_ATTESTED_NO_DUPLICATE_20261120")=="1"
                )
                approval_state={"armed":False,"attempted":False,
                                "approvedRequestSent":False,"reason":"not_armed"}
                checkout_state={"armed":False,"attempted":False,
                                "requestSent":False,"path":None,
                                "reason":"not_armed"}
                checkout_marker=root/"checkout_attempt_20261120.flag"
                def parse_zero_total(value):
                    if isinstance(value,bool):
                        return False
                    if isinstance(value,(int,float)):
                        return Decimal(str(value))==0
                    if isinstance(value,str):
                        x=value.strip().replace("€","").replace(" ","")
                        if x in ("0","0.0","0.00","0,0","0,00"):
                            return True
                    return False
                def basket_response_shape(payload):
                    # Structural debugging only. Never return raw values or
                    # arbitrary key names from a potentially personal payload.
                    allowed=("total","price","amount","gross","net","sum",
                             "currency","basket","cart","summary","checkout",
                             "order","data","result","items","tickets",
                             "reservations","cost","fare","payment")
                    def classify(value):
                        if isinstance(value,dict):
                            return "object"
                        if isinstance(value,list):
                            return "array"
                        if isinstance(value,bool):
                            return "boolean"
                        if isinstance(value,(int,float)):
                            return "number"
                        if isinstance(value,str):
                            return "string"
                        return "null_or_other"
                    def inspect(obj,level=0):
                        if isinstance(obj,dict):
                            keys=[k for k in obj if isinstance(k,str)]
                            known=[{"key":k,"type":classify(obj[k])}
                                   for k in keys if any(x in k.lower() for x in allowed)]
                            # Diagnose unnamed wrapper values by type only.
                            # Never return unknown keys, raw HTML, numbers,
                            # booking IDs, user details or customer values.
                            unknown_types=[classify(obj[k]) for k in keys
                                           if not any(x in k.lower() for x in allowed)]
                            unknown_string_shapes=[]
                            for k in keys:
                                if any(x in k.lower() for x in allowed):
                                    continue
                                value=obj[k]
                                if isinstance(value,str):
                                    stripped=value.lstrip()
                                    unknown_string_shapes.append({
                                        "looksLikeHtml":stripped.startswith("<"),
                                        "looksLikeJson":stripped.startswith(("{","[")),
                                        "isEmpty":not stripped,
                                        "lengthBand":("empty" if not value else
                                                      "short" if len(value)<80 else
                                                      "medium" if len(value)<1000 else "long")
                                    })
                            return {"type":"object","fieldCount":len(keys),
                                    "unknownFieldTypes":unknown_types[:12],
                                    "unknownStringShapes":unknown_string_shapes[:6],
                                    "monetaryOrContainerFields":known[:20],
                                    "children":[{"via":k,"structure":inspect(obj[k],level+1)}
                                                for k in ("data","result","basket","cart",
                                                          "summary","checkout")
                                                if level<3 and k in obj
                                                and isinstance(obj[k],(dict,list))][:6],
                                    "unnamedContainerShapes":[
                                        {"type":classify(obj[k]),
                                         "structure":inspect(obj[k],level+1)}
                                        for k in keys
                                        if level<3 and not any(x in k.lower()
                                            for x in allowed)
                                        and isinstance(obj[k],(dict,list))
                                    ][:3]}
                        if isinstance(obj,list):
                            return {"type":"array","length":len(obj),
                                    "firstItem":inspect(obj[0],level+1)
                                    if obj and level<4 else None}
                        return {"type":classify(obj)}
                    return inspect(payload)
                def basket_item_evidence(payload):
                    # Return booleans and safe schema labels only, never values.
                    # A line-item price alone is not the provider's final total.
                    data=payload.get("data") if isinstance(payload,dict) else None
                    arrays=[(key,value) for key,value in data.items()
                            if isinstance(value,list)] if isinstance(data,dict) else []
                    if len(arrays)!=1:
                        return {"verified":False,"reason":"item_array_missing_or_ambiguous",
                                "arrays":len(arrays)}
                    items=arrays[0][1]
                    if len(items)!=1 or not isinstance(items[0],dict):
                        return {"verified":False,"reason":"requires_exactly_one_item",
                                "itemCount":len(items)}
                    item=items[0]
                    def collect(obj,depth=0):
                        if depth>3:
                            return []
                        if isinstance(obj,dict):
                            result=[]
                            for key,value in list(obj.items())[:80]:
                                if isinstance(value,(str,int,float)) and not isinstance(value,bool):
                                    result.append((str(key).lower(),str(value)))
                                elif isinstance(value,(dict,list)):
                                    result.extend(collect(value,depth+1))
                            return result
                        if isinstance(obj,list):
                            result=[]
                            for value in obj[:8]:
                                result.extend(collect(value,depth+1))
                            return result
                        return []
                    scalars=collect(item)
                    # Seat details may be placed inside an opaque array or a
                    # generic string field rather than a field named "seat".
                    # Match only an entire, known seat token; don't expose
                    # other data or infer a completed reservation from it.
                    import re
                    allowed_seats={"233A","233D","191D","182A","231D",
                        "222D","222A","221A","221D","230D","213D","212D",
                        "210A","210D","209A","209D","206D","205D","204D",
                        "203D","202D","195D","194D","190D"}
                    token_re=re.compile(r"(?<![A-Z0-9])(?:"
                        + "|".join(sorted(allowed_seats)) + r")(?![A-Z0-9])")
                    seat_hits=sorted(set(
                        hit.group(0) for key,value in scalars
                        for hit in token_re.finditer(value.upper())))
                    seat_key_hits=sorted(set(
                        hit.group(0) for key,value in scalars
                        if any(part in key for part in ("seat","platz","place"))
                        for hit in token_re.finditer(value.upper())))
                    opaque_arrays={
                        key:{"count":len(value),
                             "firstItemType":type(value[0]).__name__
                             if value else None}
                        for key,value in item.items()
                        if isinstance(value,list) and key.lower() in
                        ("seats","reservations","passengers","tickets",
                         "segments","connections","places","rsv")}
                    def matches(substr,keys):
                        return any(any(k in key for k in keys)
                                   and substr.lower() in value.lower()
                                   for key,value in scalars)
                    price=item.get("price")
                    return {
                        "verified":False,
                        "itemCount":1,
                        "numericPriceIsZero":(
                            isinstance(price,(int,float)) and not isinstance(price,bool)
                            and Decimal(str(price))==0),
                        "priceFieldType":type(price).__name__,
                        "matchingDepartureDate":(
                            matches("2026-11-20",("date","departure","start","travel"))
                            or matches("20.11.2026",("date","departure","start","travel"))),
                        "matchingDepartureTime":matches("18:22",("departure","time","start")),
                        "matchingTrain":matches("1009",("train","connection","service")),
                        "matchingSeat_AtResponseTime":bool(seat_key_hits),
                        "seatTokensAnywhere":seat_hits,
                        "seatTokensInNamedFields":seat_key_hits,
                        "knownNestedArrayShapes":opaque_arrays,
                        "recognizedSchemaFields":sorted({
                            key for key,value in scalars
                            if key in ("price","date","departure","departuredate",
                                       "departuretime","train","trainnumber",
                                       "seat","seatnumber","place","tariff",
                                       "currency","from","to")})[:20],
                        "reason":"line_item_not_final_total_or_booking_confirmation"
                    }
                def basket_total_evidence(payload):
                    # Accept only a single explicit total in a checkout/basket
                    # root or its immediate summary. Never trust a line-item
                    # subtotal or an arbitrary nested zero.
                    if not isinstance(payload,dict):
                        return {"verified":False,"reason":"non_object"}
                    containers=[payload]
                    for key in ("basket","cart","summary","checkout","order"):
                        node=payload.get(key)
                        if isinstance(node,dict):
                            containers.append(node)
                    fields=("grandTotal","totalPrice","totalAmount","totalGross",
                            "totalGrossPrice","finalPrice","total")
                    candidates=[]
                    for node in containers:
                        for key in fields:
                            if key in node:
                                candidates.append((key,node[key]))
                    if len(candidates)!=1:
                        return {"verified":False,"reason":"total_absent_or_ambiguous",
                                "totalFieldCount":len(candidates)}
                    key,value=candidates[0]
                    return {"verified":parse_zero_total(value),
                            "reason":"zero_total" if parse_zero_total(value)
                                   else "nonzero_or_unrecognized_total",
                            "totalFieldName":key}
                network={"allowedTimetableReads":[],"allowedBasketAdd":[],"allowedSeatLookup":[],"seatLookupResponses":[],"allowedSeatUpdate":[],"seatUpdateResponses":[],"allowedBasketRead":[],"basketReadResponses":[],"blockedFirstPartyWrites":[],"failedFirstPartyRequests":[],
                         "httpErrors":[],"basketAddResponses":[],"basketTotalEvidence":[],"basketApprovalResponses":[],"paymentMethodReads":[],"checkoutOrderResponses":[],"firstPartyRequestsByMethod":{}}
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
                    if (u.hostname in ("westbahn.at","www.westbahn.at")
                        and u.path=="/ticketshop/basket/get" and resp.ok):
                        try:
                            payload=resp.json()
                            quote=basket_total_evidence(payload)
                            quote["responseShape"]=basket_response_shape(payload)
                            quote["itemEvidence"]=basket_item_evidence(payload)
                            network["basketTotalEvidence"].append(quote)
                        except Exception:
                            network["basketTotalEvidence"].append({
                                "verified":False,"reason":"response_not_json"})
                    if (u.hostname in ("westbahn.at","www.westbahn.at")
                        and u.path=="/ticketshop/basket/approve"):
                        network["basketApprovalResponses"].append({
                            "status":resp.status,"ok":resp.ok})
                    if (u.hostname in ("westbahn.at","www.westbahn.at")
                        and checkout_state["path"]==u.path):
                        network["checkoutOrderResponses"].append({
                            "status":resp.status,"ok":resp.ok})
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
                    # WESTbahn uses this POST to fetch payment-method
                    # OPTIONS while rendering checkout. It is a read of
                    # available methods, not payment initiation.
                    safe_payment_methods_read=(
                        req.method.upper()=="POST"
                        and u.scheme=="https"
                        and u.hostname in ("westbahn.at","www.westbahn.at")
                        and u.port in (None,443)
                        and u.path=="/ticketshop/payment/payment-methods"
                        and not u.query and not u.fragment
                        and req.resource_type in ("xhr","fetch")
                        and not req.is_navigation_request()
                        and len(network["paymentMethodReads"])<2
                    )
                    if safe_payment_methods_read:
                        network["paymentMethodReads"].append({
                            "method":"POST","path":u.path})
                        route.continue_()
                        return
                    # Permit ONE terminal order request, only while a
                    # verified zero-EUR checkout confirmation is being clicked.
                    # No arbitrary payment requests, no retries.
                    final_post=(
                        req.method.upper()=="POST"
                        and u.scheme=="https"
                        and u.hostname in ("westbahn.at","www.westbahn.at")
                        and u.port in (None,443)
                        and not u.query and not u.fragment
                        and req.resource_type in ("fetch","xhr")
                        and not req.is_navigation_request()
                        and (u.path.startswith("/ticketshop/") or
                             u.path.startswith("/api/v1/"))
                        and any(term in u.path.lower() for term in
                            ("/order/","/booking/","/checkout/","/purchase/",
                             "/payment/complete","/payment/confirm"))
                        and not any(term in u.path.lower() for term in
                            ("cancel","delete","remove","refund","method",
                             "charge","capture","card","pay-with","tokenize"))
                        and checkout_state["armed"]
                        and not checkout_state["attempted"]
                        and not checkout_marker.exists()
                    )
                    if final_post:
                        try:
                            fd=os.open(str(checkout_marker),
                                os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
                            with os.fdopen(fd,"w") as marker:
                                marker.write("one_final_order_request")
                                marker.flush()
                                os.fsync(marker.fileno())
                        except FileExistsError:
                            route.abort()
                            return
                        checkout_state["attempted"]=True
                        checkout_state["requestSent"]=True
                        checkout_state["path"]=u.path
                        checkout_state["reason"]="one_verified_zero_euro_order_request"
                        route.continue_()
                        return
                    if req.method.upper() not in ("GET","HEAD"):
                        if (req.method.upper()=="POST"
                            and u.path=="/ticketshop/basket/approve"
                            and u.scheme=="https"
                            and u.hostname in ("westbahn.at","www.westbahn.at")
                            and u.port in (None,443)
                            and not u.query and not u.fragment
                            and req.resource_type in ("fetch","xhr")
                            and not req.is_navigation_request()
                            and purchase_opt_in and approval_state["armed"]
                            and not approval_state["attempted"]
                            and not approval_marker.exists()):
                            # The marker is written before the one permitted
                            # attempt, preventing retries after unknown outcomes.
                            # Exclusive, persistent attempt marker prevents
                            # any second approval even if process crashes.
                            try:
                                fd=os.open(str(approval_marker),
                                    os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
                                with os.fdopen(fd,"w") as marker:
                                    marker.write("attempted_2026-11-20\\n")
                                    marker.flush()
                                    os.fsync(marker.fileno())
                            except FileExistsError:
                                approval_state["reason"]="already_attempted"
                                route.abort()
                                return
                            approval_state["attempted"]=True
                            approval_state["approvedRequestSent"]=True
                            approval_state["reason"]="one_request_permitted"
                            route.continue_()
                            return
                        if (req.method.upper()=="POST" and u.path=="/ticketshop/basket/approve"
                            and u.scheme=="https"
                            and u.hostname in ("westbahn.at","www.westbahn.at")):
                            # Observe only structural metadata. Never log request bodies,
                            # customer data, tokens, or payment details; never send approval.
                            raw=req.post_data or ""
                            parsed=None
                            try:
                                parsed=json.loads(raw) if raw else None
                            except (ValueError,TypeError):
                                pass
                            # Multipart form-data is expected by this endpoint.
                            # Inspect names ONLY; never expose names, values, tokens,
                            # passenger data, or identifiers outside a small whitelist.
                            import re
                            field_names=re.findall(
                                r'Content-Disposition:\s*form-data;[^\r\n]*?name="([^"]{1,90})"',
                                raw,re.IGNORECASE)
                            safe_categories=("amount","total","price","sum",
                                             "fare","ticket","train","seat",
                                             "date","route","journey","tariff")
                            semantic_fields=sorted({
                                key.lower() for key in field_names
                                if key.lower() in safe_categories
                            })
                            # A multipart field may itself contain JSON. Classify
                            # nested structure without exposing any values or
                            # arbitrary names (could include private identifiers).
                            parts=re.findall(
                                r'Content-Disposition:\s*form-data;[^\r\n]*?name="[^"]+"[^\r\n]*\r\n(?:[^\r\n]*\r\n)*?\r\n(.*?)(?=\r\n--)',
                                raw,re.IGNORECASE|re.DOTALL)
                            nested_types=[]
                            nested_semantics=set()
                            def inspect_shape(obj,depth=0):
                                if depth>3:
                                    return
                                if isinstance(obj,dict):
                                    for k,v in list(obj.items())[:100]:
                                        low=str(k).lower()
                                        if low in safe_categories:
                                            nested_semantics.add(low)
                                        inspect_shape(v,depth+1)
                                elif isinstance(obj,list):
                                    for item in obj[:15]:
                                        inspect_shape(item,depth+1)
                            for part in parts[:10]:
                                try:
                                    payload=json.loads(part)
                                    nested_types.append("json_object" if isinstance(payload,dict)
                                        else "json_array" if isinstance(payload,list) else "json_scalar")
                                    inspect_shape(payload)
                                except (ValueError,TypeError):
                                    nested_types.append("non_json")
                            network["approvalRequestStructure"]={
                                "method":"POST","path":u.path,
                                "contentType":req.headers.get("content-type","").split(";")[0][:55],
                                "bodyFormat":("multipart/form-data" if "multipart/form-data" in
                                             req.headers.get("content-type","").lower()
                                             else ("json" if isinstance(parsed,(dict,list))
                                                   else ("empty" if not raw else "opaque"))),
                                "multipartFieldCount":len(field_names),
                                "multipartPayloadTypes":nested_types,
                                "safeNestedSemanticKeys":sorted(nested_semantics),
                                "safeSemanticFieldNames":semantic_fields,
                                "hasPriceField":any(k in field_names for k in
                                    ("amount","total","price","sum")),
                                "providerFinalPriceVerified":False,
                                "wasSent":False
                            }
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
                                // Geometry is diagnostic only. DOM proximity
                                // is not proof of a two-person table layout.
                                const seatNodes=[...root.querySelectorAll(
                                    'button.west-ui-seat-picker--seat'
                                )].filter(visible).map(e=>{
                                    const label=norm(e.getAttribute("aria-label")||
                                        e.getAttribute("title")||e.innerText);
                                    const m=label.match(/^(\d{2,3}[A-D])\b/i);
                                    const rect=e.getBoundingClientRect();
                                    return m?{
                                        code:m[1].toUpperCase(),label,
                                        x:rect.x+rect.width/2,
                                        y:rect.y+rect.height/2
                                    }:null;
                                }).filter(Boolean);
                                // The WESTbahn seat map renders visible
                                // fixtures separately from seat buttons.
                                // Inspect likely table/fixture DOM markers,
                                // but do not infer a verified 2-seat layout
                                // from CSS names or coordinates alone.
                                const fixtureNodes=[...root.querySelectorAll(
                                    '[class*="seat-picker"],[class*="seats-"]'
                                )].filter(e=>visible(e) && !e.matches('button') &&
                                    typeof e.className==="string" &&
                                    /table|tisch|desk/i.test(e.className+" "+
                                        (e.getAttribute("aria-label")||""))
                                ).map(e=>{
                                    const r=e.getBoundingClientRect();
                                    return {
                                        classHint:e.className.slice(0,95),
                                        x:r.x+r.width/2,y:r.y+r.height/2,
                                        width:Math.round(r.width),
                                        height:Math.round(r.height)
                                    };
                                }).filter(e=>e.width>3 && e.height>3).slice(0,60);
                                const layoutEvidence=seats.filter(s=>s.available &&
                                    /Fensterplatz/i.test(s.label) &&
                                    /mit Tisch/i.test(s.label) &&
                                    !/WESTcafé|Klappsitz/i.test(s.label)
                                ).map(candidate=>{
                                    const current=seatNodes.find(n=>n.code===candidate.code);
                                    if(!current)return {code:candidate.code,
                                        status:"geometry_not_available"};
                                    const neighbors=seatNodes.filter(n=>n.code!==candidate.code)
                                        .map(n=>({
                                            code:n.code,
                                            label:n.label.slice(0,75),
                                            dx:Math.round(n.x-current.x),
                                            dy:Math.round(n.y-current.y),
                                            distance:Math.round(Math.hypot(
                                                n.x-current.x,n.y-current.y))
                                        })).sort((a,b)=>a.distance-b.distance).slice(0,8);
                                    return {
                                        code:candidate.code,
                                        status:"geometry_collected_not_verified",
                                        nearbySeats:neighbors,
                                        nearbyTableMarkers:fixtureNodes.map(t=>({
                                            classHint:t.classHint,
                                            dx:Math.round(t.x-current.x),
                                            dy:Math.round(t.y-current.y),
                                            width:t.width,height:t.height
                                        })).filter(t=>Math.abs(t.dx)<140 &&
                                            Math.abs(t.dy)<165).slice(0,8),
                                        layoutVerification:"requires_explicit_seat_map_review",
                                        fourPersonGroupExcluded:false
                                    };
                                });
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
                                    authorizedFallback:([["231D",11],["222D",11],["222A",11],["221A",11],["221D",11],["230D",11],["213D",10],["212D",10],["210A",10],["210D",10],["209A",10],["209D",10],["206D",9],["205D",9],["204D",9],["203D",9],["202D",9],["195D",9],["194D",9],["191D",8],["190D",8]]).filter(
                                        p=>p[1]===wagon).map(p=>{
                                        const seat=seats.find(x=>x.code===p[0]);
                                        return {code:p[0],wagon,
                                            status:seat?(seat.available?"available":"unavailable"):
                                                "not_found_in_visible_wagon"};
                                    }),
                                    fallbackLayoutEvidence:layoutEvidence,
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
                        layout_evidence=[
                            {"wagon":w["wagon"],**candidate}
                            for w in result["wagonAvailability"]
                            if w.get("status")=="wagon_inspected"
                            for candidate in w.get("fallbackLayoutEvidence",[])
                        ]
                        # Conservatively flag facing 2+2 clusters seen in
                        # the DOM geometry. This is an indication, not proof
                        # of the actual table layout. Never auto-select them.
                        layout_by_code={(e["wagon"],e["code"]):e
                                        for e in layout_evidence}
                        for candidate in fallback:
                            evidence=layout_by_code.get(
                                (candidate["wagon"],candidate["code"]),{})
                            label=candidate["label"]
                            direction=("in Fahrtrichtung" if "in Fahrtrichtung" in label
                                       else "gegen Fahrtrichtung"
                                       if "gegen Fahrtrichtung" in label else None)
                            opposite=("gegen Fahrtrichtung"
                                      if direction=="in Fahrtrichtung"
                                      else "in Fahrtrichtung"
                                      if direction=="gegen Fahrtrichtung" else None)
                            neighbors=evidence.get("nearbySeats",[])
                            # Nearby opposite-facing window and aisle seats,
                            # aligned in the same transverse row.
                            opposite_window=next((n for n in neighbors
                                if opposite and opposite in n["label"]
                                and "Fensterplatz" in n["label"]
                                and 35<=abs(n["dy"])<=115
                                and abs(n["dx"])<=25),None)
                            opposite_aisle=next((n for n in neighbors
                                if opposite_window and opposite in n["label"]
                                and "Gangplatz" in n["label"]
                                and abs(n["dy"]-opposite_window["dy"])<=22
                                and 25<=abs(n["dx"])<=85),None)
                            facing_cluster=bool(opposite_window and opposite_aisle)
                            candidate["layoutClassification"]=(
                                "suspected_four_seat_table"
                                if facing_cluster else "layout_not_verified")
                            candidate["excludedFromAutomaticFallback"]=True
                            candidate["layoutEvidence"]={
                                "nearbyTableMarkers":evidence.get("nearbyTableMarkers",[]),
                                "facingWindowSeat":opposite_window["code"]
                                    if opposite_window else None,
                                "facingAisleSeat":opposite_aisle["code"]
                                    if opposite_aisle else None,
                                "classificationOnlyNotProof":True
                            }
                        suspected_four_count=sum(
                            c["layoutClassification"]=="suspected_four_seat_table"
                            for c in fallback)
                        fallback.sort(key=lambda c:(
                            {11:0,10:1,9:2,8:3,7:4}.get(c["wagon"],5),
                            c["code"]
                        ))
                        result["fallbackSeatSuggestions"]={
                            "status":"candidates_require_table_layout_verification"
                                if fallback else "no_table_window_candidates_found",
                            "criteria":"enabled window seat with table, not WESTcafe or folding seat",
                            "fourPersonGroupsExcluded":False,
                            "allFallbacksBlockedPendingLayoutVerification":True,
                            "verifiedSingleSeats":0,
                            "candidateCount":len(fallback),
                            "suspectedFourSeatGroups":suspected_four_count,
                            "unverifiedTableLayouts":len(fallback)-suspected_four_count,
                            "layoutEvidence":layout_evidence[:20],
                            "suggestions":fallback[:20],
                            "candidateSummaryByWagon":[{
                                "wagon":w["wagon"],
                                "count":len(w.get("fallbackCandidates",[]))
                            } for w in result["wagonAvailability"]
                              if w.get("status")=="wagon_inspected"],
                            "recommendedForAutomaticSelection":None,
                            "requiresVisualLayoutVerification":True,
                            "seatClicked":False,
                            "checkoutAuthorized":False,
                            "purchaseExecuted":False,
                            "note":"Seat labels alone cannot establish paired vs four-person table; no automatic fallback choice."
                        }
                        # Preferred seats take precedence. For unavailable
                        # preferences, try only the seats explicitly authorized
                        # by the user, in the supplied order. Never infer that
                        # an unverified seat is available.
                        checked={p["code"]:p["status"]
                                 for w in result["wagonAvailability"]
                                 if w.get("status")=="wagon_inspected"
                                 for p in w.get("preferred",[])}
                        all_verified=all(
                            any(w.get("wagon")==wagon and
                                w.get("status")=="wagon_inspected"
                                for w in result["wagonAvailability"])
                            for wagon in (11,8,7)
                        )
                        fallback_status={
                            (p["code"],p["wagon"]):p["status"]
                            for w in result["wagonAvailability"]
                            if w.get("status")=="wagon_inspected"
                            for p in w.get("authorizedFallback",[])
                        }
                        approved_fallback=[{"code":code,"wagon":wagon,
                            "status":fallback_status.get(
                                (code,wagon),"not_verified")}
                            for code,wagon in AUTHORIZED_FALLBACK_SEATS]
                        result["fallbackSeatSuggestions"]["authorizedByUser"]=approved_fallback
                        result["fallbackSeatSuggestions"]["authorizationScope"]=(
                            "seat-selection-in-form-only_no_cart_or_purchase")
                        result["fallbackSeatSuggestions"]["preferredAvailability"]=checked
                        result["fallbackSeatSuggestions"]["allPreferredUnavailable"]=(
                            all_verified and all(
                                checked.get(x)=="unavailable"
                                for x in ("233A","233D","191D","182A")
                            )
                        )
                        result["fallbackSeatSuggestions"]["status"]=(
                            "preferred_seat_available_fallback_only_informational"
                            if any(checked.get(x)=="available"
                                   for x in ("233A","233D","191D","182A"))
                            else result["fallbackSeatSuggestions"]["status"]
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
                            picked_source="preferred"
                            if picked is None:
                                picked=next((
                                    (code,wagon)
                                    for code,wagon in AUTHORIZED_FALLBACK_SEATS
                                    if code not in ("233A","233D","191D","182A")
                                    and fallback_status.get((code,wagon))=="available"
                                ),None)
                                picked_source="user_approved_fallback"
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
                                        result["prioritySeatChoice"]["selectionSource"]=picked_source
                                        result["prioritySeatChoice"]["explicitlyAuthorizedFallback"]=(
                                            picked_source=="user_approved_fallback")
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
                                                update_accepted=any(
                                                    x.get("ok") for x in network["seatUpdateResponses"]
                                                )
                                                summary["formState"]=(
                                                    "selected_seat_visible" if summary["seatShownInForm"]
                                                    else "selected_seat_not_verified"
                                                )
                                                summary["serverUpdateStatus"]=(
                                                    "seat_update_http_accepted" if update_accepted
                                                    else "no_seat_update_request_observed"
                                                )
                                                result["seatFormConfirmation"]=summary
                                                result["prioritySeatChoice"]["confirmed"]=bool(
                                                    result["seatDialogConfirmation"]["clicked"] and
                                                    summary["seatShownInForm"]
                                                )
                                                result["prioritySeatChoice"]["serverUpdateVerified"]=update_accepted
                                                result["prioritySeatChoice"]["status"]=(
                                                    "seat_update_accepted_and_visible_in_form"
                                                    if result["prioritySeatChoice"]["confirmed"] and update_accepted
                                                    else "seat_visible_in_form_no_update_observed"
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
                                result["prioritySeatChoice"]["status"]="no_approved_seat_available"
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
                    # Seat updates temporarily replace the submit text with
                    # "Wird geladen...". Observe readiness without clicking.
                    CURRENT_STAGE="cart_submit_readiness_wait"
                    cart_wait_completed=False
                    try:
                        page.wait_for_function(r"""() => {
                            const norm=s=>(s||"").replace(/\\s+/g," ").trim();
                            const visible=e=>!!e.getClientRects().length &&
                                getComputedStyle(e).visibility!=="hidden";
                            return [...document.querySelectorAll('button[type="submit"],input[type="submit"]')]
                                .some(e=>visible(e)&&!e.disabled&&!!e.closest("form")&&
                                    norm(e.getAttribute("aria-label")||e.innerText||e.textContent||e.value)
                                    ==="In den Warenkorb");
                        }""",timeout=10000,polling=250)
                        cart_wait_completed=True
                    except Exception as wait_error:
                        cart_wait_error=type(wait_error).__name__
                    result["cartSubmitReadiness"]=page.evaluate(r"""(selectedCode) => {
                        const vis=e=>!!e.getClientRects().length &&
                            getComputedStyle(e).visibility!=="hidden";
                        const norm=s=>(s||"").replace(/\s+/g," ").trim();
                        // The cart submit can live outside <main> and its
                        // label may be supplied by nested spans or aria-label.
                        const all=[...document.querySelectorAll('button, input[type="submit"]')];
                        const label=e=>norm(e.getAttribute("aria-label")||
                            e.innerText||e.textContent||e.value);
                        const buttons=all.filter(e=>vis(e)&&label(e)==="In den Warenkorb");
                        const valid=buttons.length===1 && !buttons[0].disabled &&
                            buttons[0].type==="submit" && !!buttons[0].closest("form");
                        return {
                            status:valid?"ready_for_inventory_gate":
                                (buttons.length===1?"submit_control_not_ready":"button_missing_or_ambiguous"),
                            matchingButtons:buttons.length,
                            enabled:buttons.length===1?!buttons[0].disabled:false,
                            formPresent:buttons.length===1?!!buttons[0].closest("form"):false,
                            buttonType:buttons.length===1?buttons[0].type:null,
                            submitControls:all.filter(e=>vis(e)&&e.type==="submit")
                                .map(e=>({label:label(e).slice(0,80),inForm:!!e.closest("form")}))
                                .slice(0,5),
                            selectedSeatCode:selectedCode,
                            selectedSeatInForm:[...document.querySelectorAll("main button")].filter(vis)
                                .some(e=>norm(e.getAttribute("aria-label")||e.innerText)===selectedCode),
                            clicked:false,
                            duplicateInventoryGatePassed:false,
                            checkoutAuthorized:false,
                            purchaseExecuted:false
                        };
                    }""",result["prioritySeatChoice"]["code"])
                    result["cartSubmitReadiness"]["waitForReadyCompleted"]=cart_wait_completed
                    if not cart_wait_completed:
                        result["cartSubmitReadiness"]["waitErrorClass"]=cart_wait_error
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
                # Explicit one-day owner attestation: the user inspected
                # "Meine Tickets" and confirmed no existing 20 Nov booking.
                # This is NOT an automated inventory reconciliation and
                # authorizes only a single cart-button diagnostic, not payment.
                user_attested_no_duplicate=(
                    os.environ.get("WESTBAHN_USER_ATTESTED_NO_DUPLICATE_20261120")=="1"
                    and result.get("datePicker",{}).get("dateFieldValue")=="20.11.2026"
                    and result.get("train1009Diagnostic",{}).get("rows",[])
                    and any(r.get("has1009") and r.get("has1822") and r.get("has1849")
                            for r in result["train1009Diagnostic"]["rows"])
                )
                result["cartSubmitReadiness"]["userAttestedNoDuplicate"]=bool(
                    user_attested_no_duplicate)
                result["cartSubmitReadiness"]["automatedInventoryReconciliationPassed"]=False
                # One-off release of the cart APPROVE transition, not an
                # authorization for payment or further checkout mutations.
                # The user specifically approved the one zero-euro reservation.
                quotes=network["basketTotalEvidence"]
                verified_quote=bool(quotes) and quotes[-1].get("verified") is True
                latest_preapprove_item=(quotes[-1].get("itemEvidence",{})
                    if quotes else {})
                selected_code=seat_choice.get("code")
                # The basket/get response is matched against the selected seat.
                # The item price is NOT a verified checkout final total.
                matching_post_submit_basket_verified=bool(
                    latest_preapprove_item.get("itemCount")==1
                    and latest_preapprove_item.get("numericPriceIsZero") is True
                    and latest_preapprove_item.get("matchingDepartureDate") is True
                    and latest_preapprove_item.get("matchingDepartureTime") is True
                    and latest_preapprove_item.get("matchingTrain") is True
                    and latest_preapprove_item.get("seatTokensAnywhere")==[selected_code]
                    and latest_preapprove_item.get("seatTokensInNamedFields")==[selected_code]
                )
                approval_state["armed"]=bool(
                    purchase_opt_in and user_attested_no_duplicate
                    and confirmed_form and zero_fare and seat_update_ok
                    and matching_post_submit_basket_verified
                    and not approval_marker.exists()
                    and result["cartSubmitReadiness"].get("status")=="ready_for_inventory_gate"
                )
                approval_state["reason"]=(
                    "armed" if approval_state["armed"]
                    else ("already_attempted" if approval_marker.exists()
                          else "provider_total_or_preconditions_not_verified")
                )
                if (confirmed_form and zero_fare and seat_update_ok
                    and result["cartSubmitReadiness"].get("status")=="ready_for_inventory_gate"
                    and user_attested_no_duplicate):
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
                        # The approve response may navigate the page during
                        # this diagnostic. Wait for navigation to settle.
                        try:
                            page.wait_for_load_state("domcontentloaded",
                                                     timeout=6000)
                        except Exception:
                            pass
                        # Timed waits themselves can throw while Chromium
                        # replaces the execution context during navigation.
                        try:
                            page.wait_for_timeout(700)
                        except Exception:
                            pass
                        try:
                            current_path=urlsplit(page.url).path[:160]
                        except Exception:
                            current_path="navigation_in_progress"
                        result["cartSubmissionDiagnostic"]["afterClick"]={
                            "path":current_path,
                            "basketAddRequests":len(network["allowedBasketAdd"]),
                            "basketAddResponses":list(network["basketAddResponses"]),
                            "blockedPostPaths":[i["path"] for i in
                                network["blockedFirstPartyWrites"]],
                            "basketReadResponses":list(network["basketReadResponses"]),
                            "cartText":None
                        }
                        try:
                            result["cartSubmissionDiagnostic"]["afterClick"]["cartText"]=page.evaluate(r"""(seatCode) => {
                                const m=document.querySelector("main")||document.body;
                                const t=(m.innerText||"").replace(/\s+/g," ");
                                return {
                                    containsEmptyCart:/Warenkorb\s+ist\s+leer/i.test(t),
                                    selectedSeatCode:seatCode,
                                    containsSelectedSeat:t.split(/[^A-Za-z0-9]+/).includes(seatCode),
                                    hasCheckoutWords:/Warenkorb|Kasse|Checkout/i.test(t)
                                };
                            }""",seat_choice.get("code"))
                        except Exception as diagnostic_error:
                            result["cartSubmissionDiagnostic"]["afterClick"][
                                "cartTextErrorClass"]=type(diagnostic_error).__name__[:48]
                        approval_blocked=any(
                            p["path"]=="/ticketshop/basket/approve"
                            for p in network["blockedFirstPartyWrites"])
                        result["cartSubmissionDiagnostic"]["approvalEndpoint"]={
                            "requestStructure":network.get("approvalRequestStructure"),
                            "path":"/ticketshop/basket/approve",
                            "attemptObserved":approval_blocked,
                            "requestBlocked":approval_blocked,
                            "requestSent":approval_state["approvedRequestSent"],
                            "responseStatuses":network["basketApprovalResponses"],
                            "semanticsVerified":False,
                            "finalPriceVerified":False,
                            "mayCompleteReservation":True,
                            "nextStep":"verify_approval_semantics_and_final_price_before_enabling"
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
                        result["cartSubmissionDiagnostic"]["status"]=(
                            "awaiting_explicit_one_day_cart_diagnostic_flag"
                            if not user_attested_no_duplicate
                            else "cart_submit_preconditions_not_met")
                # Inspect the public checkout review screen without any writes.
                # This is a READ-ONLY probe: no payment buttons or forms clicked.
                # It may legitimately be empty while basket/approve is blocked.
                result["checkoutReviewReadOnly"]={"status":"not_attempted",
                    "finalPriceVerified":False,"purchaseExecuted":False}
                try:
                    CURRENT_STAGE="checkout_review_read_only"
                    # The approve endpoint initiates asynchronous navigation.
                    # Wait for its actual checkout URL instead of triggering
                    # another navigation that can discard the volatile cart.
                    try:
                        page.wait_for_url(
                            lambda url:urlsplit(str(url)).path=="/ticketshop/checkout",
                            wait_until="domcontentloaded",timeout=12000)
                    except Exception:
                        pass
                    if urlsplit(page.url).path!="/ticketshop/checkout":
                        # Never force checkout navigation during a pending
                        # approval; fail closed rather than race page changes.
                        result["checkoutReviewReadOnly"]={
                            "status":"checkout_navigation_not_confirmed",
                            "path":urlsplit(page.url).path[:130],
                            "finalPriceVerified":False,"purchaseExecuted":False}
                    else:
                        try:
                            page.locator("main").wait_for(state="visible",
                                                          timeout=8000)
                        except Exception:
                            pass
                        try:
                            page.wait_for_timeout(400)
                        except Exception:
                            pass
                        for review_try in range(3):
                            try:
                                result["checkoutReviewReadOnly"]=page.evaluate(r"""(selected) => {
                        const visible=e=>!!e.getClientRects().length &&
                            getComputedStyle(e).visibility!=="hidden";
                        const norm=s=>(s||"").replace(/\s+/g," ").trim();
                        const main=document.querySelector("main")||document.body;
                        const text=norm(main.innerText||"");
                        // Only return booleans and explicitly labelled price
                        // snippets (never raw text, customer names or forms).
                        const prices=[];
                        for(const e of [...main.querySelectorAll("div,span,p,strong,b,td")]){
                            if(!visible(e) || e.children.length>2)continue;
                            const t=norm(e.innerText||"");
                            if(t.length>95 || t.length<3)continue;
                            if(/(?:Gesamt(?:betrag|preis|summe)?|Endpreis|Zu zahlen|Total|Summe)/i.test(t)
                              && /(?:€|EUR)/i.test(t)){
                                prices.push({
                                  labelType:/Endpreis/i.test(t)?"final":
                                    /Zu zahlen/i.test(t)?"payable":"total",
                                  containsZero:/\b0[,.]00\s*(?:€|EUR)|(?:€|EUR)\s*0[,.]00\b/.test(t),
                                  containsNonzero:/\b[1-9][0-9]*(?:[,.][0-9]{2})?\s*(?:€|EUR)/.test(t)
                                });
                            }
                        }
                        return {
                            status:"read_only_reviewed",
                            path:location.pathname,
                            emptyCart:/Warenkorb\s+ist\s+leer/i.test(text),
                            selectedSeatVisible:new RegExp("(^|[^A-Za-z0-9])"+
                                selected+"([^A-Za-z0-9]|$)").test(text),
                            targetDateVisible:/20\.11\.2026|20\. November 2026/.test(text),
                            targetTimeVisible:/18:22/.test(text),
                            targetTrainVisible:/\b1009\b/.test(text),
                            originVisible:/Wien Meidling/i.test(text),
                            destinationVisible:/Wiener Neustadt/i.test(text),
                            labelledPriceCandidates:prices.slice(0,8),
                            checkoutActions:[...main.querySelectorAll("button,input[type=submit],a[href]")]
                                .filter(visible).filter(e=>!e.disabled)
                                .map(e=>{
                                    const t=norm(e.getAttribute("aria-label")||
                                        e.innerText||e.value||"");
                                    const category=/bestellen|kaufen|zahlungspflichtig|verbindlich/i.test(t)
                                        ?"potentially_binding"
                                        :/weiter|fortfahren|fortsetzen/i.test(t)
                                        ?"continue"
                                        :/bezahlen|zahlung|zahlungsart/i.test(t)
                                        ?"payment"
                                        :/anmelden|einloggen/i.test(t)
                                        ?"login":"other";
                                    return {category,kind:e.tagName.toLowerCase(),
                                        isSubmit:e.type==="submit",
                                        inForm:!!e.closest("form")};
                                }).filter(x=>x.category!=="other").slice(0,12),
                            paymentOptionsRequestBlocked:false,
                            finalPriceVerified:false,
                            purchaseExecuted:false
                        };
                    }""",seat_choice.get("code") or "")
                                break
                            except Exception as transient:
                                # Checkout may reload repeatedly during
                                # async payment-method initialization. Never
                                # allow read-only diagnosis to abort the run.
                                if review_try==2:
                                    result["checkoutReviewReadOnly"]={
                                        "status":"navigation_unstable",
                                        "errorClass":type(transient).__name__[:48],
                                        "finalPriceVerified":False,
                                        "purchaseExecuted":False
                                    }
                                    break
                                try:
                                    page.wait_for_load_state("domcontentloaded",
                                                             timeout=5000)
                                except Exception:
                                    pass
                                try:
                                    page.wait_for_timeout(250)
                                except Exception:
                                    pass
                except Exception as review_error:
                    # This is a read-only probe. Its failure must not make
                    # an already-sent approval result disappear.
                    result["checkoutReviewReadOnly"]={
                        "status":"review_unavailable",
                        "errorClass":type(review_error).__name__[:48],
                        "finalPriceVerified":False,
                        "purchaseExecuted":False
                    }
                # Do not misreport a pre-checkout line-item price as
                # completion. Checkout must show precisely one zero-euro
                # total and the matching date, train and seat.
                review=result["checkoutReviewReadOnly"]
                total_candidates=review.get("labelledPriceCandidates",[])
                checkout_verified=bool(
                    approval_state["approvedRequestSent"]
                    and any(r.get("ok") is True for r in network["basketApprovalResponses"])
                    and review.get("status")=="read_only_reviewed"
                    and review.get("emptyCart") is False
                    and review.get("selectedSeatVisible") is True
                    and review.get("targetDateVisible") is True
                    and review.get("targetTrainVisible") is True
                    and review.get("targetTimeVisible") is True
                    and review.get("originVisible") is True
                    and review.get("destinationVisible") is True
                    and len(total_candidates)==1
                    and total_candidates[0].get("containsZero") is True
                    and total_candidates[0].get("containsNonzero") is False
                )
                review["zeroEuroTripReviewVerified"]=checkout_verified
                review["paymentOptionsReadRequests"]=len(
                    network["paymentMethodReads"])
                review["nextStep"]=(
                    "inspect_checkout_controls_before_binding_purchase"
                    if checkout_verified else "checkout_not_verified_stop"
                )
                # A checkout verification alone cannot safely authorize a
                # purchase without identifying the provider's final mutation.
                # All order/payment POST routes remain blocked.
                # Attempt a terminal checkout click only when the
                # provider checkout itself displays the expected route,
                # date, train, seat and one unambiguous zero-EUR total.
                # Never accept an unchecked mandatory terms control or
                # ambiguous/multiple purchase buttons.
                checkout_action={"status":"not_attempted",
                    "requestSent":False,"ticketConfirmed":False}
                if (checkout_verified and purchase_opt_in
                    and not checkout_marker.exists()
                    and approval_state["approvedRequestSent"]):
                    try:
                        # The owner explicitly opted into automatic acceptance
                        # of the WESTbahn AGB. Only for the already-verified
                        # one-shot zero-euro checkout, never for other pages.
                        # Do not accept unrelated checkboxes or force hidden
                        # controls. The final order guard remains unchanged.
                        checkout_action["termsAutoAcceptance"]={
                            "status":"not_enabled"}
                        if os.environ.get("WESTBAHN_AUTO_ACCEPT_AGB")=="1":
                            terms=page.evaluate(r"""() => {
                                const boxes=[...document.querySelectorAll(
                                    'input[type="checkbox"]')];
                                const matches=boxes.map((e,index)=>{
                                    const linked=e.id?[...document.querySelectorAll('label')]
                                        .filter(label=>label.htmlFor===e.id)
                                        .map(label=>label.innerText).join(" "):"";
                                    const text=(e.closest('label')?.innerText||
                                        linked||e.parentElement?.innerText||
                                        e.getAttribute('aria-label')||"")
                                        .replace(/\s+/g," ").trim();
                                    return {index,checked:e.checked,disabled:e.disabled,
                                        matched:/ich\s+akzeptiere\s+die\s+allgemeinen\s+geschäftsbedingungen/i.test(text)};
                                }).filter(e=>e.matched);
                                return {
                                    matchingCount:matches.length,
                                    index:matches.length===1?matches[0].index:null,
                                    checked:matches.length===1?matches[0].checked:false,
                                    disabled:matches.length===1?matches[0].disabled:true
                                };
                            }""")
                            checkout_action["termsAutoAcceptance"]={
                                "status":"ambiguous_or_missing",
                                "matchingCount":terms.get("matchingCount")}
                            if terms.get("matchingCount")==1:
                                if terms.get("checked") is True:
                                    checkout_action["termsAutoAcceptance"]={
                                        "status":"already_accepted"}
                                elif terms.get("disabled") is not True:
                                    try:
                                        terms_box=page.locator(
                                            'input[type="checkbox"]').nth(
                                            terms["index"])
                                        terms_box.check(timeout=5000)
                                        checkout_action["termsAutoAcceptance"]={
                                            "status":"checked" if terms_box.is_checked()
                                                else "not_verified"}
                                    except Exception as terms_err:
                                        checkout_action["termsAutoAcceptance"]={
                                            "status":"check_failed",
                                            "errorClass":type(terms_err).__name__[:48]}
                        # AGB changes can re-render the final CTA asynchronously.
                        # Wait for the DOM to settle before evaluating the
                        # real binding control. This does not submit anything.
                        if checkout_action["termsAutoAcceptance"].get("status")=="checked":
                            try:
                                page.wait_for_function(r"""() => {
                                    const norm=s=>(s||"").replace(/\\s+/g," ").trim();
                                    const controls=[...document.querySelectorAll(
                                        "button,input[type=submit]")];
                                    return controls.some(e=>!e.disabled &&
                                        /zahlungspflichtig\\s+bestellen/i.test(
                                            norm(e.getAttribute("aria-label")||
                                                e.innerText||e.value||"")));
                                }""",timeout=3500)
                                checkout_action["termsAutoAcceptance"][
                                    "finalControlEnabledAfterTerms"]=True
                            except Exception:
                                checkout_action["termsAutoAcceptance"][
                                    "finalControlEnabledAfterTerms"]=False
                        action=page.evaluate(r"""() => {
                            const visible=e=>!!e.getClientRects().length &&
                                getComputedStyle(e).visibility!=="hidden";
                            const norm=s=>(s||"").replace(/\s+/g," ").trim();
                            const controls=[...document.querySelectorAll(
                                "button,input[type=submit]")];
                            const candidates=controls.map((e,index)=>({
                                index,element:e,
                                label:norm(e.getAttribute("aria-label")||
                                    e.innerText||e.value||"")
                            })).filter(x=>visible(x.element)&&
                                !x.element.disabled &&
                                /(?:zahlungspflichtig\s+bestellen|kostenlos\s*(?:bestellen|buchen|kaufen)|(?:jetzt|verbindlich)\s*(?:bestellen|buchen|kaufen)|bestellung\s*abschlie(?:ßen|ssen)|buchung\s*abschlie(?:ßen|ssen))/i.test(x.label)
                                && !/ticket\s*kaufen|neues\s*ticket/i.test(x.label));
                            // Links are not equivalent to final-order buttons.
                            // In particular, /ticketshop/ticket-buchen/ starts
                            // a NEW reservation, not a checkout confirmation.
                            const links=[...document.querySelectorAll("a[href]")]
                                .filter(visible).map(e=>{
                                    const label=norm(e.getAttribute("aria-label")||
                                        e.innerText||"");
                                    let path="external_or_invalid";
                                    try {
                                        const target=new URL(e.href,location.href);
                                        if (target.origin===location.origin)
                                            path=target.pathname;
                                    } catch {}
                                    return {label,path};
                                });
                            const newTicketLinks=links.filter(x=>
                                x.path==="/ticketshop/ticket-buchen/");
                            const checkoutLinks=links.filter(x=>
                                /(?:kostenlos\s*(?:bestellen|buchen)|(?:jetzt|verbindlich)\s*(?:bestellen|buchen|kaufen)|bestellung\s*abschlie(?:ßen|ssen)|buchung\s*abschlie(?:ßen|ssen))/i.test(x.label)
                                && x.path!=="/ticketshop/ticket-buchen/");
                            const unchecked=[...document.querySelectorAll(
                                'input[type="checkbox"][required]')]
                                .filter(e=>!e.checked && !e.disabled);
                            const disabledCheckoutButtons=controls.filter(e=>
                                visible(e) && e.disabled &&
                                /zahlungspflichtig\s+bestellen/i.test(
                                    norm(e.getAttribute("aria-label")||
                                        e.innerText||e.value||"")));
                            const termsCheckboxes=[...document.querySelectorAll(
                                'input[type="checkbox"]')].filter(e=>{
                                    const surrounding=norm(
                                        e.closest("label")?.innerText||
                                        e.parentElement?.innerText||"");
                                    return /allgemeine[n]?\s+geschäftsbedingungen|\bAGB\b/i.test(surrounding);
                                });
                            return {candidateCount:candidates.length,
                                candidateIndex:candidates.length===1
                                    ?candidates[0].index:null,
                                disabledCheckoutButtonCount:disabledCheckoutButtons.length,
                                termsCheckboxCount:termsCheckboxes.length,
                                uncheckedTermsCount:termsCheckboxes.filter(e=>!e.checked).length,
                                newTicketLinkCount:newTicketLinks.length,
                                unverifiedCheckoutLinkCount:checkoutLinks.length,
                                uncheckedRequiredCount:unchecked.length};
                        }""")
                        checkout_action.update({
                            "status":"candidate_inspected",
                            "candidateCount":action.get("candidateCount"),
                            "uncheckedRequiredCount":action.get(
                                "uncheckedRequiredCount"),
                            "newTicketLinkCount":action.get("newTicketLinkCount",0),
                            "disabledCheckoutButtonCount":action.get(
                                "disabledCheckoutButtonCount",0),
                            "termsCheckboxCount":action.get("termsCheckboxCount",0),
                            "uncheckedTermsCount":action.get("uncheckedTermsCount",0),
                            "unverifiedCheckoutLinkCount":action.get(
                                "unverifiedCheckoutLinkCount",0)
                        })
                        # Do not trust the price/trip DOM snapshot taken
                        # BEFORE the AGB interaction. Reconfirm the same
                        # zero-euro, trip and seat constraints immediately
                        # before any binding order control is clicked.
                        final_dom=page.evaluate(r"""(seat) => {
                            const main=document.querySelector("main")||document.body;
                            const text=(main.innerText||"").replace(/\\s+/g," ").trim();
                            const visible=e=>!!e.getClientRects().length &&
                                getComputedStyle(e).visibility!=="hidden";
                            const priceNodes=[...main.querySelectorAll(
                                "div,span,p,strong,b,td")].filter(e=>{
                                    if (!visible(e) || e.children.length>2)return false;
                                    const t=(e.innerText||"").replace(/\\s+/g," ").trim();
                                    return t.length>=3 && t.length<=95 &&
                                        /(?:Gesamt(?:betrag|preis|summe)?|Endpreis|Zu zahlen|Total|Summe)/i.test(t) &&
                                        /(?:€|EUR)/.test(t);
                                }).map(e=>(e.innerText||"").replace(/\\s+/g," ").trim());
                            const seatFound=new RegExp("(^|[^A-Za-z0-9])"+
                                seat+"([^A-Za-z0-9]|$)","i").test(text);
                            const exactZero=priceNodes.length===1 &&
                                /\\b0[,.]00\\s*(?:€|EUR)|(?:€|EUR)\\s*0[,.]00\\b/.test(priceNodes[0]) &&
                                !/\\b[1-9][0-9]*(?:[,.][0-9]{2})?\\s*(?:€|EUR)/.test(priceNodes[0]);
                            return {
                                verified:location.pathname==="/ticketshop/checkout" &&
                                    !/Warenkorb\\s+ist\\s+leer/i.test(text) &&
                                    /20\\.11\\.2026|20\\. November 2026/.test(text) &&
                                    /18:22/.test(text) && /\\b1009\\b/.test(text) &&
                                    /Wien Meidling/i.test(text) &&
                                    /Wiener Neustadt/i.test(text) &&
                                    seatFound && exactZero,
                                totalCandidates:priceNodes.length,
                                checkoutPath:location.pathname
                            };
                        }""",seat_choice.get("code") or "")
                        checkout_action["finalDomReverified"]=final_dom.get(
                            "verified") is True
                        checkout_action["finalTotalCandidates"]=final_dom.get(
                            "totalCandidates")
                        if (action.get("candidateCount")==1
                            and action.get("uncheckedRequiredCount")==0
                            and action.get("uncheckedTermsCount")==0
                            and final_dom.get("verified") is True):
                            checkout_state["armed"]=True
                            CURRENT_STAGE="one_time_zero_euro_checkout_action"
                            try:
                                page.locator("button,input[type=submit]").nth(
                                    action["candidateIndex"]).click(
                                        timeout=7000,no_wait_after=True)
                                checkout_action["status"]="button_clicked"
                            except Exception as err:
                                checkout_action["status"]="click_error"
                                checkout_action["errorClass"]=type(err).__name__[:48]
                            finally:
                                checkout_state["armed"]=False
                            # Navigation/payment UI can update after the
                            # click. Wait without reloading or resubmitting.
                            if checkout_state["requestSent"]:
                                try:
                                    page.wait_for_load_state(
                                        "domcontentloaded",timeout=5000)
                                except Exception:
                                    pass
                            try:
                                page.wait_for_timeout(1800)
                            except Exception:
                                pass
                            checkout_action["requestSent"]=checkout_state[
                                "requestSent"]
                            checkout_action["status"]=(
                                "final_order_request_sent_verification_pending"
                                if checkout_state["requestSent"]
                                else "button_clicked_no_verified_order_request"
                                if checkout_action["status"]=="button_clicked"
                                else checkout_action["status"])
                            checkout_action["requestResponses"]=network[
                                "checkoutOrderResponses"]
                            checkout_action["currentPath"]=urlsplit(
                                page.url).path[:130]
                            # Capture only explicit confirmation indicators
                            # on the SAME session after the one order request.
                            # Do not expose names, ticket IDs or raw page text.
                            checkout_action["confirmationPage"]=page.evaluate(
                                r"""(selected) => {
                                    const main=document.querySelector("main")||document.body;
                                    const txt=(main.innerText||"").replace(/\s+/g," ");
                                    const success=/Buchung erfolgreich|Bestellung erfolgreich|Vielen Dank für (?:Ihre|deine) Buchung|Reservierung erfolgreich/i.test(txt);
                                    const seat=new RegExp("(^|[^A-Za-z0-9])"+
                                        selected+"([^A-Za-z0-9]|$)","i").test(txt);
                                    return {
                                        explicitSuccessMessage:success,
                                        sameDate:/20\.11\.2026|20\. November 2026/.test(txt),
                                        sameSeat:seat,
                                        sameTrain:/\b1009\b/.test(txt),
                                        path:location.pathname.slice(0,130),
                                        independentlyVerifiedInTicketList:false
                                    };
                                }""",seat_choice.get("code") or "")
                            # The confirmed ticket list remains the source
                            # of truth. A success message alone is insufficient.
                            checkout_action["ticketConfirmed"]=False
                        else:
                            # A visible link may lead to a new booking or an
                            # unverified provider flow. Never treat it as a
                            # binding final-order action without endpoint proof.
                            checkout_action["status"]=(
                                "final_checkout_details_changed"
                                if final_dom.get("verified") is not True
                                else "terms_not_accepted"
                                if action.get("uncheckedTermsCount",0)>0
                                else "checkout_button_disabled"
                                if action.get("disabledCheckoutButtonCount",0)>0
                                else "new_ticket_link_not_checkout_action"
                                if action.get("newTicketLinkCount",0)>0
                                and action.get("unverifiedCheckoutLinkCount",0)==0
                                else "unverified_checkout_link_requires_mapping"
                                if action.get("unverifiedCheckoutLinkCount",0)>0
                                else "no_unambiguous_final_action"
                            )
                    except Exception as err:
                        checkout_state["armed"]=False
                        checkout_action={"status":"inspection_error",
                            "errorClass":type(err).__name__[:48],
                            "requestSent":checkout_state["requestSent"],
                            "ticketConfirmed":False}
                result["checkoutAction"]=checkout_action
                # Distinguish absence of a seat token in the provider's
                # basket line-item from the independently confirmed seat in
                # the reservation form. Never turn either into a final-price
                # assertion or automatically bypass the approval gate.
                latest_item=(network["basketTotalEvidence"][-1].get("itemEvidence",{})
                             if network["basketTotalEvidence"] else {})
                result["bookingEvidence"]={
                    "oneBasketItem":latest_item.get("itemCount")==1,
                    "lineItemPriceZero":latest_item.get("numericPriceIsZero") is True,
                    "dateMatches":latest_item.get("matchingDepartureDate") is True,
                    "timeMatches":latest_item.get("matchingDepartureTime") is True,
                    "trainMatches":latest_item.get("matchingTrain") is True,
                    "seatCode":seat_choice.get("code"),
                    "seatIndependentlyConfirmedInForm":bool(
                        confirmed_form and seat_update_ok),
                    "seatEncodedInBasketResponse":bool(
                        seat_choice.get("code") in
                        latest_item.get("seatTokensAnywhere",[])),
                    "providerFinalTotalConfirmed":verified_quote,
                    "oneItemApprovalGatePassed":matching_post_submit_basket_verified,
                    "readyToCommit":False,
                    "reason":"basket_item_price_not_checkout_final_total"
                }
                result["purchaseGate"]={
                    "bookingEvidence":result["bookingEvidence"],
                    "checkoutReviewReadOnly":result["checkoutReviewReadOnly"],
                    "sameBrowserSession":True,
                    "checkoutReviewTripAndZeroEuroVerified":checkout_verified,
                    "nextBindingCheckoutActionAllowed":False,
                    "checkoutAction":result["checkoutAction"],
                    "checkoutState":checkout_state,
                    "checkoutAttemptMarkerExists":checkout_marker.exists(),
                    "userOptIn":purchase_opt_in,
                    "matchingPostSubmitBasketVerified":matching_post_submit_basket_verified,
                    "approvalIsPotentiallyBinding":True,
                    "oneTerminalOrderRequestConditionallyAllowed":True,
                    "unverifiedPaymentRequestsAllowed":False,
                    "providerBasketQuote":(network["basketTotalEvidence"][-1]
                                           if network["basketTotalEvidence"]
                                           else {"verified":False,"reason":"no_quote_response"}),
                    "approvalState":approval_state,
                    "approvalResponses":network["basketApprovalResponses"],
                    "attemptMarkerExists":approval_marker.exists(),
                    "bookingConfirmedByTickets":False,
                    "purchaseExecuted":False
                }
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
                if checkout_state["requestSent"]:
                    result["status"]="checkout_request_sent_confirmation_pending"
                    result["bookingAuthorized"]=True
                    result["purchaseExecuted"]=False
                if os.environ.get("WESTBAHN_COMPACT_OUTPUT")=="1":
                    result={
                        "status":result.get("status"),
                        "date":result.get("datePicker",{}).get("dateFieldValue"),
                        "route":{"from":ORIGIN,"to":DESTINATION,
                                 "departure":"18:22","train":"1009"},
                        "selectedSeat":result.get("prioritySeatChoice"),
                        "seatFormConfirmation":result.get("seatFormConfirmation"),
                        "cartSubmitReadiness":result.get("cartSubmitReadiness"),
                        "cartSubmissionDiagnostic":result.get("cartSubmissionDiagnostic"),
                        "blockedFirstPartyWrites":network["blockedFirstPartyWrites"],
                        "purchaseGate":result["purchaseGate"],
                        "bookingAuthorized":bool(checkout_state["requestSent"]),
                        "purchaseExecuted":False
                    }
                print(json.dumps(result,ensure_ascii=False))
            finally:
                context.close()

if __name__=="__main__":
    try:
        main()
    except Exception as error:
        # Do not echo network payloads, URLs or user details on failures.
        # Persisted one-shot markers are checked before any next attempt.
        print(json.dumps({"status":"station_selection_blocked",
                          "errorClass":type(error).__name__[:48],
                          "errorStage":CURRENT_STAGE,
                          "errorSubtype":(
                              "navigation_race" if "context was destroyed"
                              in str(error).lower()
                              else "page_closed" if "target closed"
                              in str(error).lower()
                              else "timeout" if "timeout" in str(error).lower()
                              else "other"),
                          "approvalMarkerState":{
                              "original":Path(os.environ.get(
                                  "WESTBAHN_BROWSER_PROFILE",
                                  "./data/westbahn-browser")).resolve().joinpath(
                                  "approval_attempt_20261120.flag").exists(),
                              "recovery1":Path(os.environ.get(
                                  "WESTBAHN_BROWSER_PROFILE",
                                  "./data/westbahn-browser")).resolve().joinpath(
                                  "approval_attempt_20261120_recovery1.flag").exists(),
                              "recovery2":Path(os.environ.get(
                                  "WESTBAHN_BROWSER_PROFILE",
                                  "./data/westbahn-browser")).resolve().joinpath(
                                  "approval_attempt_20261120_recovery2.flag").exists(),
                              "recovery3":Path(os.environ.get(
                                  "WESTBAHN_BROWSER_PROFILE",
                                  "./data/westbahn-browser")).resolve().joinpath(
                                  "approval_attempt_20261120_recovery3.flag").exists(),
                              "checkout":Path(os.environ.get(
                                  "WESTBAHN_BROWSER_PROFILE",
                                  "./data/westbahn-browser")).resolve().joinpath(
                                  "checkout_attempt_20261120.flag").exists()
                          },
                          "bookingAuthorized":"unknown_if_approval_sent",
                          "purchaseExecuted":"unverified_check_markers"}))
