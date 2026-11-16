"""Metadata-only descriptions of blocked browser requests. No network I/O."""
import json
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit, parse_qsl

SAFE_KEY = re.compile(r"^[a-zA-Z_][a-zA-Z_0-9-]{0,39}$")
ROUTE_LABEL = re.compile(r"^(?:api|v[1-9]|rest|graphql|ticketshop|booking|bookings|reservation|reservations|seat|seats|seatmap|seat-map|availability|search|offers|price|checkout|cart|payment|confirm|selection|select|coach|wagon|journey|journeys|train|trains|tickets|dashboard|layout|config|data)$",re.I)
DATE = re.compile(r"^\\d{4}-\\d{1,2}-\\d{1,2}$")
SENSITIVE = re.compile(r"(?:token|secret|password|passwd|cookie|authorization|bearer|session|csrf|jwt|email|phone|address|name|birth|passenger|person|card|iban|account|key)",re.I)

def safe_key(key):
    if not isinstance(key,str) or not SAFE_KEY.fullmatch(key) or SENSITIVE.search(key):
        return "{field}"
    return key

def body_paths(obj, prefix="", depth=0, output=None):
    if output is None:
        output=set()
    if depth>7 or len(output)>=60:
        return output
    if isinstance(obj,dict):
        for k,v in list(obj.items())[:60]:
            name=safe_key(k)
            body_paths(v, f"{prefix}.{name}" if prefix else name, depth+1,output)
    elif isinstance(obj,list):
        if obj:
            body_paths(obj[0],prefix+"[]",depth+1,output)
        else:
            output.add(prefix+"[]")
    elif prefix:
        output.add(prefix)
    return output

def describe(request,step="seat_selection"):
    u=urlsplit(request.url)
    host=(u.hostname or "").lower()
    provider=host in ("westbahn.at","westbahn.de") or host.endswith((".westbahn.at",".westbahn.de"))
    segments=[seg if ROUTE_LABEL.fullmatch(seg) and not DATE.fullmatch(seg) else "{id}"
              for seg in u.path.split("/") if seg]
    path="/"+"/".join(segments) if provider else "/{redacted}"
    query_keys=sorted(set(safe_key(k) for k,_ in parse_qsl(u.query,keep_blank_values=True)))[:40] if provider else []
    try:
        raw=request.post_data
        size=len(raw.encode("utf-8")) if isinstance(raw,str) else 0
    except Exception:
        raw=None
        size=0
    try:
        headers=request.headers
        content_type=str(headers.get("content-type","")).split(";",1)[0].strip().lower()
        if not re.fullmatch(r"[a-z0-9.+-]+/[a-z0-9.+-]+",content_type):
            content_type="{redacted}"
    except Exception:
        content_type="{unknown}"
    paths=[]
    if raw is not None and size<=65536 and content_type=="application/json":
        try:
            paths=sorted(body_paths(json.loads(raw)))[:60]
        except (ValueError,TypeError,RecursionError):
            paths=["{unparseable}"]
    elif raw is not None:
        paths=["{non_json_or_oversize}"]
    return {"method":request.method if request.method in ("GET","HEAD","POST","PUT","PATCH","DELETE") else "OTHER",
            "host":host if provider else "other-origin","path":path,
            "query_keys":query_keys,"body_keys":paths,
            "content_type":content_type,"body_size_bytes":size,
            "timestamp_utc":datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "step":step}


def abort_and_record(route, blocked_requests, step="seat_selection", limit=100):
    """Fail-closed offline route guard: always abort, never continue/fulfill."""
    try:
        if len(blocked_requests)<limit:
            item=describe(route.request,step=step)
            item["resourceType"]=route.request.resource_type
            item["requestIndex"]=len(blocked_requests)+1
            blocked_requests.append(item)
    finally:
        route.abort()

def risk_summary(blocked_requests):
    """Offline-only grouped evidence; never grants network permission."""
    groups={}
    for item in blocked_requests:
        method=item.get("method","OTHER")
        host=item.get("host","other-origin")
        path=item.get("path","/{redacted}")
        ctype=item.get("content_type","{unknown}")
        key=(method,host,path,ctype)
        group=groups.setdefault(key,{"method":method,"host":host,"path":path,
                                     "content_type":ctype,"count":0,
                                     "body_keys":set(),"body_size_bytes":[]})
        group["count"]+=1
        group["body_keys"].update(item.get("body_keys",[]))
        group["body_size_bytes"].append(item.get("body_size_bytes",0))
    results=[]
    for group in groups.values():
        sizes=group.pop("body_size_bytes")
        group["body_size_range"]=[min(sizes),max(sizes)]
        group["body_keys"]=sorted(group["body_keys"])
        group["risk"]="mutation_possible" if group["method"] not in ("GET","HEAD") else "unverified_read_candidate"
        group["contractStatus"]="unverified"
        results.append(group)
    return {"groups":sorted(results,key=lambda g:(g["host"],g["path"],g["method"])),
            "allowLiveRequests":False,"bookingAuthorized":False,
            "purchaseExecuted":False,
            "providerContractVerified":False,
            "nextStep":"Independent provider endpoint documentation or authorized read-only evidence required"}
