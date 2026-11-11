"""Inspect existing WESTbahn ticket detail pages without mutating any ticket.

Only safe GET navigation to a uniquely linked, same-origin dashboard detail
page is permitted. No buttons, forms, account management or checkout actions.
All public results omit ticket codes, customer IDs, URLs and personal data.
"""
import re
from datetime import date
from urllib.parse import urljoin, urlsplit, parse_qsl
from booking_evidence import assess_existing_ticket, extract_explicit_trip_date
from confirmation_evidence import reference_indicators
from detail_route_diagnostics import route_signature
from ticket_content_diagnostics import categorize_detail_text

ROUTE=re.compile(
    r'^/ticketshop/dashboard/(?:tickets?|reservations?)/(?:'
    r'(?:detail|details|view)(?:/[A-Za-z0-9_-]{1,90})?'
    r'|[A-Za-z0-9_-]{8,90})/?$',re.I)
# Observed path structure: two opaque IDs inside an existing-ticket detail URL.
# Only strict, view-labeled same-host GET routes can be opened; never checkout.
OPAQUE_TICKET_ROUTE=re.compile(
    r'^/ticketshop/dashboard/ticket/([A-Za-z0-9_-]{8,11})/([A-Za-z0-9_-]{4,7})/?$',re.I)
DANGEROUS_SEGMENT=re.compile(
    r'cancel|delete|refund|change|edit|purchase|pay|rebook|order|'
    r'storno|stornier|umbuch|bearbeit|lösch|bezahl|kauf|zahl|transfer|share|download|pdf|print',re.I)
# Strictly visual/view labels. These variants are not editing or buying commands.
EXACT_VIEW_LABELS=frozenset((
    'details','mehr details','weitere details','details ansehen','details anzeigen',
    'details öffnen','details zur fahrt','details zur reservierung','details zum ticket',
    'ticketdetails','ticketdetails ansehen','ticketdetails anzeigen','ticket details',
    'reservierungsdetails','reservierungsdetails ansehen','reservierungsdetails anzeigen',
    'ticket','ansehen','anzeigen','zum ticket','ticket ansehen',
    'ticket anzeigen','ticket öffnen','reservierung ansehen',
    'reservierung anzeigen','zur ticketansicht','zur detailansicht'
))


def view_label_allowed(caption):
    """Allow only known *read-only* UI captions, ignoring spacing and arrow icons."""
    if not isinstance(caption,str) or len(caption)>75 or BAD_LABEL.search(caption):
        return False
    normalized=' '.join(caption.casefold().split()).strip(' .:›»→↗')
    return normalized in EXACT_VIEW_LABELS
ALLOWED_KEYS={'id','ticketid','ticket','bookingid','reservationid','ref'}
BAD_LABEL=re.compile(r'umbuchen|stornieren|löschen|ändern|bearbeiten|bezahlen|kaufen|bestellen|checkout|'
                     r'zahlung|erstatten|übertragen|weiterleiten|herunterladen|download',re.I)
DETAIL_LABEL=re.compile(r'details?|ansehen|anzeigen|ticket(?:details?| ansehen| anzeigen)?|reservierung ansehen',re.I)
DATE_LABEL=re.compile(r'\b(?:MO|DI|MI|DO|FR|SA|SO)\s+[0-9]{1,2}\s+'
                      r'(?:JAN|JÄN|FEB|MÄR|APR|MAI|JUN|JUL|AUG|SEP|OKT|NOV|DEZ)(?:\s+[0-9]{4})?\b',re.I)
SEAT_LABEL=re.compile(r'\bSitzplatz\s*:?[\s♿]*(\d{2,4})\s*([A-D])\b',re.I)


def safe_detail_url(base, href, caption):
    """A navigation target, never a mutation. Return private URL or None."""
    if not isinstance(href,str) or not href or len(href)>500 or not isinstance(caption,str):
        return None
    if BAD_LABEL.search(caption) or not DETAIL_LABEL.search(caption) or len(caption)>75:
        return None
    try:
        source=urlsplit(base)
        dest=urlsplit(urljoin(base,href))
        if source.scheme!='https' or source.hostname not in ('westbahn.at','westbahn.de'):
            return None
        if dest.scheme!='https' or dest.hostname!=source.hostname or dest.port not in (None,443):
            return None
        if dest.username or dest.password or dest.fragment:
            return None
        opaque=OPAQUE_TICKET_ROUTE.fullmatch(dest.path)
        if opaque:
            if not view_label_allowed(caption) or dest.query:
                return None
            if any(DANGEROUS_SEGMENT.search(x) for x in opaque.groups()):
                return None
            return dest.geturl()
        if not ROUTE.fullmatch(dest.path):
            return None
        last_segment=dest.path.rstrip('/').rsplit('/',1)[-1]
        if BAD_LABEL.search(last_segment) or DANGEROUS_SEGMENT.search(last_segment):
            return None
        query=parse_qsl(dest.query,keep_blank_values=True)
        if len(query)>2 or any(k.lower() not in ALLOWED_KEYS or not v for k,v in query):
            return None
        if not query and not re.search(r'/[A-Za-z0-9_-]{8,90}/?$',dest.path):
            return None
        return dest.geturl()
    except (ValueError,TypeError):
        return None


def rejection_reason(base, candidate):
    """Return a fixed category only; never disclose URLs or ticket identifiers."""
    if not isinstance(candidate,dict) or not isinstance(candidate.get('caption'),str):
        return 'invalid_control'
    caption=candidate['caption']
    if BAD_LABEL.search(caption):
        return 'unsafe_action_label'
    if not DETAIL_LABEL.search(caption):
        return 'not_detail_label'
    if candidate.get('tag','a')!='a':
        return 'non_link_detail_control'
    href=candidate.get('href')
    if not isinstance(href,str) or not href or href.startswith('#'):
        return 'no_static_destination'
    if href.lower().startswith(('javascript:','data:','blob:')):
        return 'script_or_data_destination'
    try:
        source=urlsplit(base)
        target=urlsplit(urljoin(base,href))
        if source.scheme!='https' or source.hostname not in ('westbahn.at','westbahn.de'):
            return 'untrusted_source'
        if target.scheme!='https' or target.hostname!=source.hostname or target.port not in (None,443) or target.username or target.password:
            return 'untrusted_destination'
        if target.fragment:
            return 'fragment_destination'
        opaque=OPAQUE_TICKET_ROUTE.fullmatch(target.path)
        if opaque:
            # These are fixed diagnostic categories. Never expose a caption,
            # URL or either ticket identifier.
            if target.query:
                return 'ticket_view_query_not_allowed'
            if not view_label_allowed(caption):
                return 'ticket_view_caption_not_allowlisted'
            if any(DANGEROUS_SEGMENT.search(part) for part in opaque.groups()):
                return 'ticket_view_token_safety_filter'
            return 'accepted' if safe_detail_url(base,href,caption) else 'ticket_view_other_policy_block'
        if not ROUTE.fullmatch(target.path):
            return 'unrecognized_detail_path'
        last=target.path.rstrip('/').rsplit('/',1)[-1]
        if BAD_LABEL.search(last) or re.search(r'cancel|delete|refund|change|edit|purchase|pay',last,re.I):
            return 'mutation_like_path'
        query=parse_qsl(target.query,keep_blank_values=True)
        if len(query)>2 or any(k.lower() not in ALLOWED_KEYS or not v for k,v in query):
            return 'unrecognized_query'
        if not query and not re.search(r'/[A-Za-z0-9_-]{8,90}/?$',target.path):
            return 'missing_identifier'
        return 'accepted'
    except (ValueError,TypeError):
        return 'invalid_destination'


def visible_ticket_cards(page):
    """Return private in-memory card text and link metadata; never log them."""
    return page.evaluate(r"""() => {
        const norm=s=>(s||'').replace(/\s+/g,' ').trim();
        const visible=e=>!!e.getClientRects().length && getComputedStyle(e).visibility!=='hidden';
        const title='Reservierung Comfort Class';
        const titles=[...document.querySelectorAll('body *')].filter(e=>
           visible(e)&&norm(e.innerText)===title &&
           ![...e.children].some(c=>visible(c)&&norm(c.innerText)===title));
        const records=[];
        for(const heading of titles){
          for(let root=heading;root&&root!==document.body;root=root.parentElement){
            const text=norm(root.innerText);
            if(text.length>3200)break;
            if(!text.includes('Abfahrt') || !text.includes('Ankunft') ||
               !text.includes('Sitzplatz') || text.split(title).length!==2)continue;
            const anchors=[...root.querySelectorAll('a[href],button,[role="button"]')].filter(visible)
                .slice(0,16).map(a=>({tag:a.tagName.toLowerCase(),
                 href:a.tagName.toLowerCase()==='a'?a.getAttribute('href'):null,
                 caption:norm(a.innerText||a.getAttribute('aria-label')||a.title)}));
            records.push({text,anchors});
            break;
          }
        }
        return records.slice(0,60);
    }""")



def matching_card(card, day, seat):
    if not isinstance(card,dict) or not isinstance(card.get('text'),str):
        return False
    text=card['text']
    if len(text)>3200 or 'Wien Meidling' not in text or 'Wiener Neustadt' not in text or '18:22' not in text:
        return False
    seats={f'{m.group(1)}{m.group(2).upper()}' for m in SEAT_LABEL.finditer(text)}
    if seats!={seat}: return False
    match=DATE_LABEL.search(text)
    if not match: return False
    row={'dateLabel':match.group(0),'seat':seat,'fullDate':extract_explicit_trip_date(text)}
    check=assess_existing_ticket([row],day,seat)
    return check['status']=='existing_ticket_visible' and any(m['expectedSeat'] for m in check['matches'])


def read_detail(page, url, day, seat):
    """Navigate once via GET and return sanitized evidence only."""
    if not safe_detail_url(url,url,'Details'):
        return {'detailStatus':'blocked_target','yearVerified':False}
    try:
        # Only allow GET or HEAD and the exact requested top-level detail URL.
        # This also rejects JavaScript-initiated POST/PUT/DELETE requests.
        def read_only_request(route):
            request=route.request
            if request.method.upper() not in ('GET','HEAD'):
                route.abort()
            elif request.is_navigation_request() and request.url!=url:
                route.abort()
            else:
                # Preserve later route handlers (including mocked ticket pages).
                # continue_() skips them and can fetch an unrelated live page.
                route.fallback()
        page.route('**/*',read_only_request)
        response=page.goto(url,wait_until='domcontentloaded',timeout=20000)
        if response is None or response.status!=200 or not safe_detail_url(page.url,page.url,'Details'):
            return {'detailStatus':'detail_unavailable','yearVerified':False}
        text=page.locator('body').inner_text(timeout=6000)
        if len(text)>30000:
            return {'detailStatus':'detail_too_large','yearVerified':False}
        # Some ticket detail views populate after DOMContentLoaded. Give the
        # read-only page one bounded opportunity to render before classifying.
        if not ('Reservierung Comfort Class' in text and 'Sitzplatz' in text):
            page.wait_for_timeout(1200)
            updated=page.locator('body').inner_text(timeout=6000)
            if len(updated)>30000:
                return {'detailStatus':'detail_too_large','yearVerified':False}
            text=updated
        try:
            dom=page.evaluate("""() => ({
                login: !!document.querySelector('input[type="password"]'),
                pdf: !!document.querySelector(
                    'embed[type="application/pdf"],object[type="application/pdf"]'
                )
            })""")
        except Exception:
            dom={}
        if not isinstance(dom,dict):
            dom={}
        mime='unknown'
        try:
            content_type=response.headers.get('content-type','').lower()
            mime=('pdf' if 'application/pdf' in content_type else
                  'html' if 'text/html' in content_type else
                  'other' if content_type else 'unknown')
        except Exception:
            pass
        diagnostic=categorize_detail_text(text,mime,dom.get('login') is True,dom.get('pdf') is True)
        exact=extract_explicit_trip_date(text)
        seats={f'{m.group(1)}{m.group(2).upper()}' for m in SEAT_LABEL.finditer(text)}
        journey=all(x in text for x in ('Wien Meidling','Wiener Neustadt','18:22','18:49'))
        product='Reservierung Comfort Class' in text
        year_verified=exact==day and seats=={seat} and journey and product
        refs=reference_indicators(text)
        return {'detailStatus':'detail_read','yearVerified':year_verified,
                'seatMatched':seats=={seat},'tripMatched':journey and product,
                'referenceVisible':any(refs.values()),'dateExplicit':exact is not None,
                'contentDiagnostics':diagnostic}
    except Exception:
        return {'detailStatus':'detail_unavailable','yearVerified':False}


def inspect_existing_ticket_details(context, day, seat, max_pages=2):
    """Search read-only account pages; open at most one safe detail GET."""
    blocked={'status':'ticket_detail_check','bookingAuthorized':False,'confirmationVerified':False,
             'inventoryComplete':False,'safeToBook':False,'date':day,'seat':seat}
    try:
        date.fromisoformat(day)
    except (ValueError,TypeError):
        return {**blocked,'detailStatus':'invalid_date'}
    if not isinstance(seat,str) or not re.fullmatch(r'[0-9]{3}[A-D]',seat):
        return {**blocked,'detailStatus':'invalid_seat'}
    reports=[]
    matched=0
    safe_links={'westbahn.at':set(),'westbahn.de':set()}
    suspicious=0
    rejection_reasons={}
    control_kinds={}
    route_templates={}
    for host in ('westbahn.at','westbahn.de'):
        for number in range(1,min(max_pages,5)+1):
            page=context.new_page()
            try:
                home=f'https://{host}/ticketshop/dashboard/tickets?page={number}&mode=valid'
                response=page.goto(home,wait_until='domcontentloaded',timeout=20000)
                if response is None or response.status!=200 or urlsplit(page.url).hostname!=host:
                    reports.append('account_unavailable')
                    break
                if not (urlsplit(page.url).path.rstrip('/')=='/ticketshop/dashboard/tickets'
                        and dict(parse_qsl(urlsplit(page.url).query)).get('mode')=='valid'):
                    reports.append('wrong_account_page')
                    break
                page.get_by_text('Westbahn-Konto',exact=True).first.wait_for(state='visible',timeout=8000)
                page.get_by_text('Gültige Tickets',exact=True).first.wait_for(state='visible',timeout=5000)
                found={}
                for iteration in range(12):
                    for item in visible_ticket_cards(page):
                        if not matching_card(item,day,seat): continue
                        # One card may be collected repeatedly when scrolling.
                        identity=item['text']
                        if identity not in found: found[identity]=item
                    if iteration==11: break
                    page.evaluate("""() => {
                       const root=document.scrollingElement;
                       if(root)root.scrollTop=Math.min(root.scrollHeight,root.scrollTop+Math.max(150,root.clientHeight));
                       for(const e of document.querySelectorAll('main,section,div,article')){
                         if(e.clientHeight>50 && e.scrollHeight>e.clientHeight+5 &&
                            /scroll|auto/.test(getComputedStyle(e).overflowY)){
                           e.scrollTop=Math.min(e.scrollHeight,e.scrollTop+e.clientHeight);
                         }
                       }
                    }""")
                    page.wait_for_timeout(200)
                matched+=len(found)
                for item in found.values():
                    for anchor in item.get('anchors',[]):
                        href=anchor.get('href')
                        caption=anchor.get('caption')
                        resolved=safe_detail_url(page.url,href,caption) if anchor.get('tag','a')=='a' else None
                        if resolved:
                            safe_links[host].add(resolved)
                        elif isinstance(caption,str) and DETAIL_LABEL.search(caption):
                            suspicious+=1
                            reason=rejection_reason(page.url,anchor)
                            rejection_reasons[reason]=rejection_reasons.get(reason,0)+1
                            tag=anchor.get('tag','a')
                            kind='anchor' if tag=='a' else 'button' if tag=='button' else 'custom_control'
                            control_kinds[kind]=control_kinds.get(kind,0)+1
                            fingerprint=route_signature(page.url,href,tag)
                            template=(kind,reason,fingerprint['route'],fingerprint['query'],fingerprint.get('ticketRouteShape','not_applicable'))
                            route_templates[template]=route_templates.get(template,0)+1
                reports.append('account_read')
            except Exception:
                reports.append('account_unavailable')
            finally:
                page.close()
    if matched==0:
        return {**blocked,'detailStatus':'ticket_not_visible','accountPagesRead':reports,
                'message':'Keine eindeutige vorhandene Karte erkannt; das beweist keine fehlende Buchung.'}
    # A single existing ticket can appear on both .at and .de. Inspect at
    # most one uniquely safe link on the preferred Austrian domain first.
    all_link_count=sum(map(len,safe_links.values()))
    ambiguous=any(len(links)>1 for links in safe_links.values())
    candidates=safe_links['westbahn.at'] or safe_links['westbahn.de']
    if ambiguous or len(candidates)!=1:
        return {**blocked,'detailStatus':'no_unique_safe_detail_link',
                'matchingCards':matched,'safeDetailLinks':all_link_count,
                'otherDetailControls':suspicious,
                'rejectionReasons':rejection_reasons,'controlKinds':control_kinds,
                'candidatePathPatterns':[
                    {'kind':key[0],'reason':key[1],'route':key[2],'query':key[3],
                     'ticketRouteShape':key[4],'count':n}
                    for key,n in sorted(route_templates.items())[:12]],
                'accountPagesRead':reports,
                'message':'Passende Karte vorhanden; kein eindeutig lesbarer Detail-Link. Kein Klick auf andere Bedienelemente.'}
    # Use a fresh page and one GET. No click, download, form submission or checkout.
    url=next(iter(candidates))
    page=context.new_page()
    try:
        details=read_detail(page,url,day,seat)
    finally:
        page.close()
    return {**blocked,**details,'matchingCards':matched,'safeDetailLinks':1,
            'accountPagesRead':reports,
            'message':'Vorhandene Detailansicht nur lesend geprüft. Keine Bestellung, keine Änderung und keine verifizierte Checkout-Bestätigung.'}
