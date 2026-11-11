"""Redacted conservative assessment of visible WESTbahn account cards.

No missing card can authorize booking; no result indicates inventory completeness.
"""
from datetime import date
from booking_evidence import assess_existing_ticket


def validate_batch_dates(value):
    """Accept up to five unique ISO weekdays, never use uncontrolled page ranges."""
    if not isinstance(value,str):
        raise ValueError('invalid_dates')
    dates=value.split(',')
    if not (1 <= len(dates) <= 5) or len(set(dates)) != len(dates):
        raise ValueError('invalid_dates')
    for text in dates:
        try:
            day=date.fromisoformat(text)
        except (TypeError,ValueError):
            raise ValueError('invalid_dates') from None
        if day.isoformat()!=text or day.weekday()>4:
            raise ValueError('invalid_dates')
    return dates


def verify_detail_evidence(detail, travel_day, seat):
    """Positive existing ticket proof; unrelated pages or unverified IDs fail closed."""
    return isinstance(detail, dict) and all((
        detail.get('status')=='ticket_detail_check',
        detail.get('date')==travel_day,
        detail.get('seat')==seat,
        detail.get('detailStatus')=='detail_read',
        detail.get('yearVerified') is True,
        detail.get('seatMatched') is True,
        detail.get('tripMatched') is True,
        detail.get('referenceVisible') is True,
        detail.get('dateExplicit') is True,
        detail.get('bookingAuthorized') is False,
        detail.get('confirmationVerified') is False,
        detail.get('safeToBook') is False,
        detail.get('inventoryComplete') is False
    ))


def summarize_inventory_batch(rows, days, reports, detail_checks=None):
    """Fixed-shape report. Never serialize the cards, links, names, refs or IDs."""
    if not isinstance(days,list) or not 1<=len(days)<=5 or any(
       not isinstance(day,str) for day in days):
        raise ValueError('invalid_dates')
    page_reports=reports if isinstance(reports,list) else []
    detail_checks=detail_checks if isinstance(detail_checks,dict) else {}
    successful=sum(1 for r in page_reports
                   if isinstance(r,dict) and r.get('status')=='account_verified')
    attempted=sum(1 for r in page_reports if isinstance(r,dict))
    failures=attempted-successful
    # Provider pagination does not expose an authoritative count of all
    # reservations. Even a successful scan of both domains is INCOMPLETE.
    coverage={
        'pagesAttempted':attempted,
        'pagesVerified':successful,
        'pagesFailed':failures,
        'domainsRead':len({r.get('domain') for r in page_reports
                           if isinstance(r,dict) and
                           r.get('status')=='account_verified' and
                           r.get('domain') in ('westbahn.at','westbahn.de')}),
        'complete':False,
        'reason':'page_error_or_login' if failures else 'pagination_not_authoritative'
    }
    # Diagnostic only: observed links do not prove that all pages exist or
    # were visited. Never convert pagination observations into booking rights.
    pagination={}
    for domain in ('westbahn.at','westbahn.de'):
        observed=sorted({n for r in page_reports
                         if isinstance(r,dict) and r.get('domain')==domain
                         and r.get('status')=='account_verified'
                         for n in (r.get('paginationLinks') or [])
                         if type(n) is int and 1<=n<=100})
        checked=sorted({r.get('page') for r in page_reports
                        if isinstance(r,dict) and r.get('domain')==domain
                        and r.get('status')=='account_verified'
                        and type(r.get('page')) is int})
        failures_by_reason={}
        failed_pages=set()
        for report in page_reports:
            if not isinstance(report,dict) or report.get('domain')!=domain:
                continue
            status=report.get('status')
            if status in ('http_error','unexpected_redirect','account_not_verified',
                          'timeout','unavailable'):
                failures_by_reason[status]=failures_by_reason.get(status,0)+1
                if type(report.get('page')) is int:
                    failed_pages.add(report['page'])
        hints=[r.get('domHints') for r in page_reports
               if isinstance(r,dict) and r.get('domain')==domain
               and r.get('status')=='account_verified'
               and isinstance(r.get('domHints'),dict)]
        dynamic_hints={name:max((h.get(name,0) for h in hints
                                 if type(h.get(name,0)) is int),default=0)
                       for name in ('navigationControls','enabledNavigationControls',
                                    'loadingIndicators','scrollContainers')}
        scroll_reports=[r for r in page_reports
                        if isinstance(r,dict) and r.get('domain')==domain
                        and r.get('status')=='account_verified']
        scroll_observation={
            'pagesWithNewCards':sum(1 for r in scroll_reports
                                     if type(r.get('newCardsAfterScroll')) is int
                                     and r['newCardsAfterScroll']>0),
            'newCardsAfterScroll':sum(max(0,r.get('newCardsAfterScroll',0))
                                       for r in scroll_reports
                                       if type(r.get('newCardsAfterScroll',0)) is int),
            'scrollPasses':sum(max(0,r.get('scrollPasses',0))
                               for r in scroll_reports
                               if type(r.get('scrollPasses',0)) is int)}
        pagination[domain]={'pagesVerified':checked,
                            'linkedPagesObserved':observed,
                            'linkedPagesNotVerified':[n for n in observed if n not in checked],
                            'failedPageNumbers':sorted(failed_pages),
                            'failureReasons':failures_by_reason,
                            'verifiedPageCount':len(checked),
                            'dynamicPageHints':dynamic_hints,
                            'scrollObservation':scroll_observation}
    output=[]
    for day in days:
        result=assess_existing_ticket(rows,day)
        matching=result.get('matches',[])
        seen=result.get('status')=='existing_ticket_visible' and bool(matching)
        seats=sorted({r['seat'] for r in matching
                     if isinstance(r,dict) and isinstance(r.get('seat'),str)})
        # Yearless labels are a potential reservation conflict, not proof
        # of a specific year. A missing result stays pending manual review.
        exact=seen and all(x.get('yearExplicit') is True for x in matching)
        verified=(len(seats)==1 and
                  verify_detail_evidence(detail_checks.get(day),day,seats[0]))
        output.append({
            'date':day,
            'status':('detail_verified' if verified else
                      'visible_year_verified' if exact else
                      'possible_existing' if seen else 'review_required'),
            'seats':seats if seen else [],
            'dateVerified':bool(exact or verified),
            'detailVerified':bool(verified),
            'potentialDuplicate':bool(seen),
            'safeToBook':False
        })
    return {
        'status':'inventory_batch_read' if successful else 'account_unavailable',
        'days':output,
        'accountPageReads':successful,
        'coverage':coverage,
        'paginationDiagnostics':pagination,
        'inventoryComplete':False,
        'safeToBook':False,
        'bookingAuthorized':False,
        'message':'Sichtbare Kontokarten geprüft. Fehlende Treffer erlauben keine Buchung.'
    }
