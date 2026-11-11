"""Read-only, fail-closed WESTbahn zero-euro checkout audit.

No booking, agreement acceptance or basket mutation happens in this module.
The exact order and success pages must be verified before enabling live checkout.
"""
import re
from datetime import date


def cart_facts(page):
    """Capture only structural facts from one on-screen checkout card, never its text."""
    return page.evaluate(r"""() => {
      const visible=e => !!e.getClientRects().length && getComputedStyle(e).visibility!=='hidden' && getComputedStyle(e).display!=='none';
      const norm=s => (s||'').normalize('NFKC').replace(/\s+/g,' ').trim();
      const txt=e => norm(e.innerText||e.textContent||'');
      const leaf=label => [...document.querySelectorAll('body *')].filter(e => visible(e) && txt(e)===label && ![...e.children].some(c => visible(c) && txt(c)===label));
      const titles=leaf('Warenkorb');
      const checkouts=[...document.querySelectorAll('button,[role="button"],input[type="submit"]')].filter(e=>visible(e) && /^Zahlungspflichtig bestellen$/i.test(norm(e.innerText||e.value||e.getAttribute('aria-label'))));
      const result={atCheckout:location.protocol==='https:' && location.hostname==='westbahn.at' && location.pathname.replace(/\/$/,'')==='/ticketshop/checkout',
        titleCount:titles.length,submitCount:checkouts.length,cardCount:0,productCount:0,checkboxCount:0,termsLabel:false,hasQuantityOne:false,
        hasComfort:false,hasRoute:false,hasTrain:false,hasTime:false,seatCodes:[],dates:[],prices:[],hasTotal:false,buttonDisabled:true};
      if(titles.length!==1 || checkouts.length!==1)return result;
      const button=checkouts[0];
      let card=titles[0],depth=0;
      while(card && card!==document.body && !card.contains(button) && depth<12){card=card.parentElement;depth++;}
      if(!card || card===document.body || !card.contains(button))return result;
      // Scope must not be an entire page, which may contain unrelated fares.
      const t=txt(card);
      if(t.length>2600 || t.length<90)return result;
      result.cardCount=1;
      result.productCount=(t.match(/Reservierung\s+Comfort\s+Class/gi)||[]).length;
      result.hasComfort=result.productCount===1;
      result.hasRoute=/Wien\s+Meidling\s*[-–—]\s*Wiener\s+Neustadt/i.test(t);
      result.hasTrain=/\b1009\b/.test(t);
      result.hasTime=/18\s*:\s*22\s*[-–—−]\s*18\s*:\s*49/.test(t);
      result.seatCodes=[...new Set([...t.matchAll(/Sitzpl(?:atz|ätze)\s*:?\s*(\d{2,4}\s*[A-D])\b/gi)].map(m=>m[1].replace(/\s+/g,'').toUpperCase()))];
      result.dates=[...new Set([...t.matchAll(/\b\d{1,2}\.\s*\d{1,2}\.\s*\d{4}\b/g)].map(m=>m[0].replace(/\s+/g,'')))];
      result.prices=[...t.matchAll(/(?:€\s*(\d+(?:[.,]\d{2}))|(\d+(?:[.,]\d{2}))\s*€)/g)].map(m=>m[1]||m[2]);
      result.hasTotal=/Gesamtsumme\s*€\s*0[,.]00/i.test(t);
      result.hasQuantityOne=/\bMenge\s+Produkt\s+Summe\s+1\s+Reservierung\s+Comfort\s+Class/i.test(t)
        || /\b1\s*[×x]\s*Reservierung\s+Comfort\s+Class/i.test(t);
      const boxes=[...card.querySelectorAll('input[type="checkbox"]')].filter(visible);
      result.checkboxCount=boxes.length;
      result.termsLabel=/Ich akzeptiere die Allgemeinen Geschäftsbedingungen der Westbahn/i.test(t);
      result.buttonDisabled=button.matches(':disabled,[aria-disabled="true"]');
      return result;
    }""")


def audit_cart(page, day, seat):
    """Only a matching one-item cart with entirely zero prices is suitable.

    No control handles or private page text leave this function.
    """
    try:
        expected=date.fromisoformat(day)
    except (ValueError, TypeError):
        return {'verified': False, 'reason': 'invalid_date'}
    if not isinstance(seat,str) or not re.fullmatch(r'\d{3}[A-D]',seat):
        return {'verified': False, 'reason': 'invalid_seat'}
    facts=cart_facts(page)
    expected_dates={expected.strftime('%d.%m.%Y'), f'{expected.day}.{expected.month}.{expected.year}'}
    checks={
        'checkoutUrl': facts.get('atCheckout') is True,
        'oneCart': facts.get('titleCount')==1 and facts.get('cardCount')==1,
        'oneSubmit': facts.get('submitCount')==1,
        'oneComfortProduct': facts.get('productCount')==1 and facts.get('hasComfort') is True and facts.get('hasQuantityOne') is True,
        'correctRouteTrainTime': all(facts.get(k) is True for k in ('hasRoute','hasTrain','hasTime')),
        'correctDate': bool(facts.get('dates')) and set(facts['dates']).issubset(expected_dates),
        'correctSeat': facts.get('seatCodes')==[seat],
        'zeroTotal': facts.get('hasTotal') is True and len(facts.get('prices',[]))>=2 and all(p in ('0,00','0.00') for p in facts['prices']),
        'termsPresent': facts.get('checkboxCount')==1 and facts.get('termsLabel') is True
    }
    return {'verified': all(checks.values()), 'checks':checks, 'bookingAuthorized':False,
            'message': 'Warenkorb nur lesend geprüft; kein Warenkorb-Klick, keine AGB-Zustimmung und keine Buchung.'}
