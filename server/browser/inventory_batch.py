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
    for domain in ('westbahn.at',):
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
        # Candidate provider totals are hints only, never authoritative evidence.
        total_reports=[r.get('totalHints') for r in scroll_reports
                       if isinstance(r.get('totalHints'),dict)]
        candidate_totals=sorted({n for h in total_reports
                                 for n in (h.get('candidateTotals') or [])
                                 if type(n) is int and 0<=n<=9999})[:10]
        total_observation={
            'pagesWithTotalHints':sum(1 for h in total_reports
                                      if type(h.get('candidateTotalLabels')) is int
                                      and h['candidateTotalLabels']>0),
            'candidateTotals':candidate_totals,
            'conflictingCandidates':len(candidate_totals)>1,
            'authoritativeTotalVerified':False}
        # A provider-rendered count is useful for diagnostics, but cannot by
        # itself prove that the account's complete ticket inventory was loaded.
        # Report both the comparison and why booking remains blocked.
        observed_cards=sum(max(0,r.get('comfortCards',0)) for r in scroll_reports
                           if type(r.get('comfortCards')) is int)
        if not candidate_totals:
            total_observation['comparison']='provider_total_not_exposed'
        elif len(candidate_totals)>1:
            total_observation['comparison']='conflicting_provider_totals'
        elif candidate_totals[0]==observed_cards:
            total_observation['comparison']='visible_count_matches_hint_only'
        else:
            total_observation['comparison']='visible_count_differs_from_hint'
        total_observation['visibleComfortCards']=observed_cards
        total_observation['inventoryProof']='not_authoritative'
        # Aggregate only bounded card counts. Unmatched cards can represent
        # other routes, layouts or parsing gaps; they never prove absence.
        card_counts=[r for r in scroll_reports if type(r.get('comfortCards')) is int
                     and type(r.get('matchingCards')) is int]
        card_coverage={
            'pagesWithCardCounts':len(card_counts),
            'comfortCardsObserved':sum(max(0,r['comfortCards']) for r in card_counts),
            'commuterCardsParsed':sum(max(0,r['matchingCards']) for r in card_counts),
            'pagesWithUnmatchedCards':sum(1 for r in card_counts if r['comfortCards']>r['matchingCards']),
            'unmatchedComfortCards':sum(max(0,r['comfortCards']-r['matchingCards']) for r in card_counts),
            'parserCoverageComplete':False}
        # Decision support, not purchase authorization. A clean parser is
        # distinct from a complete, provider-authoritative account inventory.
        parser_consistent=(len(card_counts)==len(scroll_reports) and
                           bool(card_counts) and
                           card_coverage['unmatchedComfortCards']==0 and
                           all(r['matchingCards']<=r['comfortCards'] for r in card_counts))
        page_scan_clean=(bool(checked) and not failed_pages and
                         not any(n not in checked for n in observed))
        confidence='partial_scan' if page_scan_clean else 'scan_error'
        if parser_consistent and page_scan_clean:
            confidence='visible_cards_consistent'
        card_coverage['visibleParserConsistent']=parser_consistent
        card_coverage['accountInventoryAuthoritative']=False
        card_coverage['assessment']=confidence
        # Compare redacted per-page journey/seat signatures only. An identical
        # second page may be a server-side alias rather than real pagination.
        # Empty pages cannot prove anything and are excluded.
        signatures={}
        for report in scroll_reports:
            sig=report.get('pageCardSignature')
            if not isinstance(sig,list) or not sig or type(report.get('page')) is not int:
                continue
            safe=tuple(sorted(tuple(item) for item in sig if isinstance(item,(list,tuple))
                              and len(item)==2 and all(isinstance(v,str) for v in item)))
            if safe:
                signatures[report['page']]=safe
        repeated_pages=sorted(page for page,sig in signatures.items()
                              if any(other<page and prior==sig for other,prior in signatures.items()))
        pagination[domain]={'pagesVerified':checked,
                            'linkedPagesObserved':observed,
                            'linkedPagesNotVerified':[n for n in observed if n not in checked],
                            'failedPageNumbers':sorted(failed_pages),
                            'failureReasons':failures_by_reason,
                            'verifiedPageCount':len(checked),
                            'repeatedContentPages':repeated_pages,
                            'dynamicPageHints':dynamic_hints,
                            'scrollObservation':scroll_observation,
                            'cardCoverage':card_coverage,
                            'totalObservation':total_observation}
    # Date-specific review evidence is limited to the Austrian account.
    # Page coverage and absence are not an authoritative inventory.
    at_verified=sorted({r.get('page') for r in page_reports
                        if isinstance(r,dict) and r.get('domain')=='westbahn.at'
                        and r.get('status')=='account_verified'
                        and type(r.get('page')) is int})
    at_failures=sum(1 for r in page_reports if isinstance(r,dict)
                    and r.get('domain')=='westbahn.at'
                    and r.get('status')!='account_verified')
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
        # Explain precisely why the unattended booking flow must stop.
        # Account-page absence is never sufficient evidence to purchase.
        blockers=(['existing_reservation_verified'] if verified else
                  ['possible_existing_reservation'] if seen else
                  ['reservation_absence_not_verified'])
        output.append({
            'date':day,
            'status':('detail_verified' if verified else
                      'visible_year_verified' if exact else
                      'possible_existing' if seen else 'review_required'),
            'seats':seats if seen else [],
            'dateVerified':bool(exact or verified),
            'detailVerified':bool(verified),
            'potentialDuplicate':bool(seen),
            'dateSpecificEvidence':{
                'matchingVisibleCards':len(matching),
                'distinctSeatsObserved':len(seats),
                'explicitYearOnAllMatches':bool(exact),
                'ticketDetailVerified':bool(verified),
                'absenceVerified':False,
                'assessment':('existing_ticket_detail_verified' if verified else
                              'matching_cards_visible' if seen else
                              'no_match_in_partial_account_scan')},
            'safeToBook':False,
            'bookingBlockers':blockers,
            'austrianPagesChecked':len(at_verified),
            'absenceEvidence':('existing_ticket_verified' if verified else
                               'possible_reservation_visible' if seen else
                               'partial_scan_with_errors' if at_failures else
                               'not_authoritatively_verified')
        })
    return {
        'status':'inventory_batch_read' if successful else 'account_unavailable',
        'days':output,
        'accountPageReads':successful,
        'coverage':coverage,
        'paginationDiagnostics':pagination,
        'targetedReview':{'domain':'westbahn.at',
                          'datesNeedingReview':[r['date'] for r in output
                                                if r['status']=='review_required'],
                          'verifiedPageNumbers':at_verified,
                          'failedPageCount':at_failures,
                          'absenceVerified':False},
        'inventoryComplete':False,
        'safeToBook':False,
        'bookingAuthorized':False,
        'decisionSupport':{
            'existingReservations':'verify_ticket_details',
            'unmatchedDates':'manual_review_required',
            'absenceProof':'not_available_from_visible_cards',
            'nextSafeAction':'review_missing_dates_without_purchase',
            'purchaseEnabled':False},
        'bookingPreflight':'blocked',
        'message':'Sichtbare Kontokarten geprüft. Fehlende Treffer erlauben keine Buchung.'
    }


def zero_euro_preflight(operator_unbooked, account_absence_verified, exact_trip_verified, seat_verified, final_total_cents):
    """Read-only decision; user confirmation never overrides account evidence."""
    blockers=[]
    if account_absence_verified is not True: blockers.append('reservation_absence_not_verified')
    if exact_trip_verified is not True: blockers.append('exact_trip_not_verified')
    if seat_verified is not True: blockers.append('seat_not_verified')
    if type(final_total_cents) is not int or final_total_cents != 0: blockers.append('final_zero_euro_total_not_verified')
    return {'operatorReportsUnbooked':operator_unbooked is True,
            'bookingBlockers':blockers, 'bookingAuthorized':False,
            'safeToBook':False, 'purchaseExecuted':False}
