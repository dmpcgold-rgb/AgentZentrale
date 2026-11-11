"""Privacy-safe diagnostics for the *visible* contents of an existing ticket page.

These indicators are not a provider booking confirmation. They never expose
page text, URLs, identifiers, booking references, or user account information.
"""
import re


def categorize_detail_text(text, document_type='unknown', has_password_field=False,
                           has_pdf_embed=False):
    """Classify a read-only view using fixed vocabulary and boolean indicators."""
    if not isinstance(text, str):
        text=''
    low=text.casefold()
    content_type=document_type if document_type in ('html','pdf','other') else 'unknown'
    has_product=('reservierung comfort class' in low or 'comfort class' in low)
    seat_label=bool(re.search(r'\bsitzplatz\s*:?\s*[\d♿]',low))
    has_route=('wien meidling' in low and 'wiener neustadt' in low)
    has_time=('18:22' in low and '18:49' in low)
    has_date=bool(re.search(r'\b\d{1,2}\.\d{1,2}\.\d{4}\b',low))
    login_words=any(s in low for s in ('anmelden','einloggen','passwort','sign in','log in'))
    account_words=any(s in low for s in ('westbahn-konto','gültige tickets','meine tickets'))
    loading=any(s in low for s in ('wird geladen','bitte warten','loading'))
    forbidden=any(s in low for s in ('zugriff verweigert','access denied','nicht berechtigt'))
    if content_type=='pdf' or has_pdf_embed:
        page_kind='embedded_document'
    elif has_password_field and login_words:
        page_kind='login_required'
    elif forbidden:
        page_kind='access_denied'
    elif has_product and seat_label and has_route:
        page_kind='ticket_content_present'
    elif has_product or seat_label or has_route:
        page_kind='partial_ticket_content'
    elif loading or len(text.strip())<80:
        page_kind='empty_or_loading'
    elif account_words:
        page_kind='account_overview'
    else:
        page_kind='unrecognized_content'
    body_band=('0-79' if len(text.strip())<80 else
               '80-299' if len(text.strip())<300 else
               '300-1999' if len(text.strip())<2000 else '2000+')
    return {
        'pageKind':page_kind,
        'bodySizeBand':body_band,
        'documentType':content_type,
        'hasPdfEmbed':has_pdf_embed is True,
        'hasLoginForm':has_password_field is True,
        'indicators':{
            'comfortProductVisible':has_product,
            'seatLabelVisible':seat_label,
            'routeVisible':has_route,
            'timesVisible':has_time,
            'fullDateVisible':has_date
        }
    }
