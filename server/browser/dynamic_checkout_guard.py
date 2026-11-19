"""Read-only, dynamic WESTbahn checkout validation.

This module has no checkout click, POST, agreement acceptance or retry operation.
The itinerary must be independently established by a trusted provider search
and quote; passing user-supplied fields is NOT purchase authorization.
"""
import re
from datetime import date

_TIME = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
_SEAT = re.compile(r"^\d{3}[A-D]$")
_TRAIN = re.compile(r"^[A-Za-z0-9-]{1,18}$")
_STATION = re.compile(r"^[\wÀ-ÿ .()/-]{3,100}$", re.UNICODE)


def validate_expected(expected):
    if not isinstance(expected, dict):
        raise ValueError("missing_itinerary")
    required = {"date", "origin", "destination", "departure",
                "arrival", "train", "seat"}
    if set(expected) != required:
        raise ValueError("invalid_itinerary_fields")
    try:
        travel_date = date.fromisoformat(expected["date"])
    except (TypeError, ValueError):
        raise ValueError("invalid_date") from None
    for station in ("origin", "destination"):
        value = expected[station]
        if (not isinstance(value, str) or not _STATION.fullmatch(value)
                or value != value.strip()):
            raise ValueError("invalid_station")
    if expected["origin"].casefold() == expected["destination"].casefold():
        raise ValueError("identical_stations")
    if not all(isinstance(expected[k], str) and _TIME.fullmatch(expected[k])
               for k in ("departure", "arrival")):
        raise ValueError("invalid_time")
    if (not isinstance(expected["train"], str)
            or not _TRAIN.fullmatch(expected["train"])):
        raise ValueError("invalid_train")
    if (not isinstance(expected["seat"], str)
            or not _SEAT.fullmatch(expected["seat"])):
        raise ValueError("invalid_seat")
    return travel_date


def dynamic_cart_facts(page, expected):
    """Evaluate only visible text within the single matching checkout card."""
    return page.evaluate(r"""(trip) => {
      const norm = s => (s || '').normalize('NFKC').replace(/\s+/g, ' ').trim();
      const visible = e => !!e.getClientRects().length &&
        getComputedStyle(e).visibility !== 'hidden' &&
        getComputedStyle(e).display !== 'none';
      const txt = e => norm(e.innerText || e.textContent || '');
      const escape = s => s.replace(/[.*+?^\u0024{}()|[\]\\]/g, '\\$&');
      const leaf = label => [...document.querySelectorAll('body *')]
        .filter(e => visible(e) && txt(e) === label &&
          ![...e.children].some(c => visible(c) && txt(c) === label));
      const titles = leaf('Warenkorb');
      const actions = [...document.querySelectorAll('button,[role="button"],input[type="submit"]')]
        .filter(e => visible(e) &&
          /^Zahlungspflichtig bestellen$/i.test(
            norm(e.innerText || e.value || e.getAttribute('aria-label'))));
      const out = {atCheckout: location.protocol === 'https:' &&
        location.hostname === 'westbahn.at' &&
        location.pathname.replace(/\/$/, '') === '/ticketshop/checkout',
        titleCount: titles.length, submitCount: actions.length,
        cardCount: 0, productCount: 0, quantityOne: false,
        routeMatched: false, trainMatched: false, timesMatched: false,
        dateCount: 0, dateMatched: false, seatCount: 0, seatMatched: false,
        prices: [], zeroTotal: false, checkboxCount: 0,
        termsPresent: false, termsAccepted: false};
      if (titles.length !== 1 || actions.length !== 1) return out;
      let card = titles[0], depth = 0;
      while (card && card !== document.body && !card.contains(actions[0]) && depth < 12) {
        card = card.parentElement; depth++;
      }
      if (!card || card === document.body || !card.contains(actions[0])) return out;
      const t = txt(card);
      if (t.length < 90 || t.length > 2600) return out;
      out.cardCount = 1;
      out.productCount = (t.match(/Reservierung\s+Comfort\s+Class/gi) || []).length;
      out.quantityOne = /\bMenge\s+Produkt\s+Summe\s+1\s+Reservierung\s+Comfort\s+Class/i.test(t) ||
        /\b1\s*[×x]\s*Reservierung\s+Comfort\s+Class/i.test(t);
      out.routeMatched = new RegExp(escape(trip.origin) + '\\s*[-–—]\\s*' +
        escape(trip.destination), 'i').test(t);
      out.trainMatched = new RegExp('(^|[^\\w])' + escape(trip.train) +
        '([^\\w]|$)', 'i').test(t);
      const time = x => escape(x).replace(':', '\\s*:\\s*');
      out.timesMatched = new RegExp(time(trip.departure) +
        '\\s*[-–—−]\\s*' + time(trip.arrival)).test(t);
      const dates = [...new Set([...t.matchAll(/\b\d{1,2}\.\s*\d{1,2}\.\s*\d{4}\b/g)]
        .map(m => m[0].replace(/\s+/g, '')))];
      const [y, m, d] = trip.date.split('-');
      const matching = new Set([d + '.' + m + '.' + y,
        Number(d) + '.' + Number(m) + '.' + y]);
      out.dateCount = dates.length;
      out.dateMatched = dates.length === 1 && matching.has(dates[0]);
      const seats = [...new Set([...t.matchAll(/Sitzpl(?:atz|ätze)\s*:?\s*(\d{2,4}\s*[A-D])\b/gi)]
        .map(m => m[1].replace(/\s+/g, '').toUpperCase()))];
      out.seatCount = seats.length;
      out.seatMatched = seats.length === 1 && seats[0] === trip.seat;
      out.prices = [...t.matchAll(/(?:€\s*(\d+(?:[.,]\d{2}))|(\d+(?:[.,]\d{2}))\s*€)/g)]
        .map(m => m[1] || m[2]);
      out.zeroTotal = /Gesamtsumme\s*€\s*0[,.]00/i.test(t);
      const boxes = [...card.querySelectorAll('input[type="checkbox"]')].filter(visible);
      out.checkboxCount = boxes.length;
      out.termsPresent = /Ich akzeptiere die Allgemeinen Geschäftsbedingungen der Westbahn/i.test(t);
      out.termsAccepted = boxes.length === 1 && boxes[0].checked === true;
      return out;
    }""", expected)


def audit_dynamic_cart(page, expected):
    """Fail-closed checkout diagnosis; never supplies permission to book."""
    try:
        validate_expected(expected)
    except ValueError as exc:
        return {"verified": False, "reason": str(exc),
                "bookingAuthorized": False}
    try:
        f = dynamic_cart_facts(page, expected)
    except Exception:
        return {"verified": False, "reason": "checkout_unreadable",
                "bookingAuthorized": False}
    if not isinstance(f, dict):
        return {"verified": False, "reason": "invalid_checkout_evidence",
                "bookingAuthorized": False}
    checks = {
        "officialCheckout": f.get("atCheckout") is True,
        "singleCart": f.get("titleCount") == 1 and f.get("cardCount") == 1,
        "singleSubmit": f.get("submitCount") == 1,
        "singleComfortProduct": f.get("productCount") == 1 and
            f.get("quantityOne") is True,
        "exactRoute": f.get("routeMatched") is True,
        "exactTrain": f.get("trainMatched") is True,
        "exactTimes": f.get("timesMatched") is True,
        "exactTravelDate": f.get("dateCount") == 1 and
            f.get("dateMatched") is True,
        "exactSeat": f.get("seatCount") == 1 and f.get("seatMatched") is True,
        "zeroEuroOnly": f.get("zeroTotal") is True and
            isinstance(f.get("prices"), list) and len(f["prices"]) >= 2 and
            all(p in ("0,00", "0.00") for p in f["prices"]),
        "termsDisplayed": f.get("checkboxCount") == 1 and
            f.get("termsPresent") is True,
    }
    return {"verified": all(checks.values()), "checks": checks,
            "bookingAuthorized": False,
            "message": "Nur dynamische Lesekontrolle. Kein Bestellklick oder Warenkorb-Eingriff."}
