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

ROUTE=re.compile(
    r'^/ticketshop/dashboard/(?:tickets?|reservations?)/(?:'
    r'(?:detail|details|view)(?:/[A-Za-z0-9_-]{1,90})?'
    r'|[A-Za-z0-9_-]{8,90})/?$',re.I)
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
        if dest.username or dest.password or dest.fragment or not ROUTE.fullmatch(dest.path):
            return None
        last_segment=dest.path.rstrip('/').rsplit('/',1)[-1]
        if BAD_LABEL.search(last_segment) or re.search(r'cancel|delete|refund|change|edit|purchase|pay',last_segment,re.I):
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
        response=page.goto(url,wait_until='domcontentloaded',timeout=20000)
        if response is None or response.status!=200 or not safe_detail_url(page.url,page.url,'Details'):
            return {'detailStatus':'detail_unavailable','yearVerified':False}
        text=page.locator('body').inner_text(timeout=6000)
        if len(text)>30000:
            return {'detailStatus':'detail_too_large','yearVerified':False}
        exact=extract_explicit_trip_date(text)
        seats={f'{m.group(1)}{m.group(2).upper()}' for m in SEAT_LABEL.finditer(text)}
        journey=all(x in text for x in ('Wien Meidling','Wiener Neustadt','18:22','18:49'))
        product='Reservierung Comfort Class' in text
        year_verified=exact==day and seats=={seat} and journey and product
        refs=reference_indicators(text)
        return {'detailStatus':'detail_read','yearVerified':year_verified,
                'seatMatched':seats=={seat},'tripMatched':journey and product,
                'referenceVisible':any(refs.values()),'dateExplicit':exact is not None}
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
