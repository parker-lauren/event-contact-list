# -*- coding: utf-8 -*-
"""Deterministic transforms for the event contact list schema.

Library + CLI. Reads a JSON array of raw records (see RAW_FIELDS) and writes
the final CSV. Every transform here is pure and testable; all the Clay calls
live in SKILL.md because they need orchestration.
"""
import csv, json, re, sys

RAW_FIELDS = (
    'first', 'last', 'company', 'domain', 'company_address',
    'contact_location_raw', 'contact_country_ticket', 'linkedin', 'email',
    'phone', 'title', 'status', 'industry', 'employees', 'company_linkedin',
    'website',
)

OUT_COLS = [
    'First Name', 'Last name', 'Company name', 'Company domain',
    'Company City', 'Company Country', 'Contact City', 'Contact Country',
    'LinkedIn', 'Email', 'Phone number', 'Job title', 'Event status',
    'Industry (mapped)', 'Industry (value)', 'Employees',
    'Company LinkedIn', 'Company website',
]

# Badge-scan context kept on the do-not-contact sheet, appended after the
# shared core columns so both sheets align on their first 18 fields.
SCAN_COLS = [
    'Lead source', 'Lead quality', 'Booth member', 'Lead comment',
    'Exhibitor comment', 'Scan time', 'Decision making role',
    'Solutions spend', 'Solution needs', 'Future speaking',
    'Present in Contact List?',
]
SCAN_FIELDS = (
    'lead_source', 'lead_quality', 'booth_member', 'lead_comment',
    'exhibitor_comment', 'scan_time', 'dm_role', 'spend', 'needs',
    'future_speaking', 'present_note',
)

# ---------------------------------------------------------------- names -----

POSTNOM = {
    'fcca','acca','aca','fca','acma','cgma','cima','mba','cpa','fcma','maat',
    'aat','ca','acis','msc','bsc','ba','phd','cfa','mcips','icaew','fcpa',
    'maicd','cma','cpfa','llb','cfe','frm','pmp','acipp','fmaat','amct','mchem',
    'micb','sbm','acsi','cae','csca','fcia','crma','cia',
}

def clean_last_name(last):
    """Strip trailing professional designations: 'Smith ACCA' -> 'Smith'."""
    parts = str(last or '').replace(',', ' ').split()
    while len(parts) > 1 and parts[-1].strip('.()').lower() in POSTNOM:
        parts.pop()
    return ' '.join(parts) if parts else str(last or '').strip()

# ------------------------------------------------------------- location -----

ISO = {
 'GB':'United Kingdom','US':'United States','FR':'France','DE':'Germany',
 'CA':'Canada','DK':'Denmark','CH':'Switzerland','NL':'Netherlands',
 'AU':'Australia','IE':'Ireland','AE':'United Arab Emirates','AT':'Austria',
 'IT':'Italy','IN':'India','BE':'Belgium','IL':'Israel','MY':'Malaysia',
 'LU':'Luxembourg','HK':'Hong Kong','CN':'China','SE':'Sweden','CZ':'Czechia',
 'BD':'Bangladesh','MT':'Malta','BR':'Brazil','JP':'Japan','UA':'Ukraine',
 'ID':'Indonesia','CI':"Côte d'Ivoire",'ES':'Spain','PT':'Portugal','PL':'Poland',
 'NO':'Norway','FI':'Finland','GR':'Greece','RO':'Romania','TR':'Türkiye',
 'SA':'Saudi Arabia','SG':'Singapore','NZ':'New Zealand','ZA':'South Africa',
 'NG':'Nigeria','KE':'Kenya','PK':'Pakistan','GE':'Georgia','ET':'Ethiopia',
 'RU':'Russia','HU':'Hungary','MX':'Mexico','JO':'Jordan','QA':'Qatar',
 'KW':'Kuwait','KZ':'Kazakhstan','LT':'Lithuania','LV':'Latvia','EE':'Estonia',
 'SK':'Slovakia','SI':'Slovenia','HR':'Croatia','RS':'Serbia','BG':'Bulgaria',
 'PH':'Philippines','TH':'Thailand','VN':'Vietnam','KR':'South Korea',
 'TW':'Taiwan','AR':'Argentina','CL':'Chile','CO':'Colombia','PE':'Peru',
 'EG':'Egypt','MA':'Morocco','GH':'Ghana','TZ':'Tanzania','UG':'Uganda',
 'IS':'Iceland','IQ':'Iraq','LB':'Lebanon','CY':'Cyprus','MU':'Mauritius',
}
COUNTRY_NAMES = {v.lower(): v for v in ISO.values()}
COUNTRY_NAMES.update({
    'uk':'United Kingdom','england':'United Kingdom','scotland':'United Kingdom',
    'wales':'United Kingdom','northern ireland':'United Kingdom',
    'usa':'United States','u.s.a':'United States','us':'United States',
    'czech republic':'Czechia','luxemburgh':'Luxembourg','turkey':'Türkiye',
    'ivory coast':"Côte d'Ivoire",'holland':'Netherlands',
})
CONTINENTS = {'africa','europe','north america','south america','asia',
              'oceania','antarctica','middle east','emea','apac'}
NOWHERE = {'worldwide','global','oo','n/a','na','none','','global 000000',
           'remote','various','multiple'}
# Country reachable from a region name when the country code is a placeholder
REGION_COUNTRY = {
    'québec':'Canada','quebec':'Canada','ontario':'Canada',
    'british columbia':'Canada','alberta':'Canada',
    'england':'United Kingdom','scotland':'United Kingdom','wales':'United Kingdom',
}
# Administrative regions that are NOT the city. Names that are also a real city
# in their own right (Bristol, Hamburg, Tokyo, Basel, Milano, New York,
# Schaffhausen, Dhaka, Kyiv City...) are deliberately absent: the second pass
# below falls back to them when nothing else qualifies.
REGIONS = {
 'québec','quebec','ontario','british columbia','alberta','manitoba',
 'saskatchewan','nova scotia','newfoundland','queensland','tasmania',
 'northern territory','western australia','south australia',
 'england','scotland','wales','northern ireland','greater london',
 'london london','middlesex','surrey','kent','essex','hertfordshire',
 'berkshire','buckinghamshire','hampshire','west midlands','midlands',
 'north yorkshire','east yorkshire','yorkshire','lancashire','cheshire',
 'derbyshire','nottinghamshire','northamptonshire','leicestershire',
 'oxfordshire','cambridgeshire','suffolk','norfolk','dorset','somerset',
 'devon','cornwall','wiltshire','gloucestershire','worcestershire',
 'warwickshire','staffordshire','shropshire','lincolnshire',
 'northumberland','cumbria','merseyside','greater manchester',
 'south yorkshire','west yorkshire','tyne and wear','bedfordshire',
 'east sussex','west sussex','sussex','midlothian','fife','ayrshire',
 'lanarkshire','sabah','sarawak',
 'california','washington','illinois','massachusetts','texas','florida',
 'ohio','michigan','pennsylvania','new jersey','delaware','maryland',
 'virginia','north carolina','south carolina','tennessee','wisconsin',
 'indiana','minnesota','colorado','arizona','nevada','oregon','utah',
 'kansas','missouri','rhode island','connecticut','new hampshire','maine',
 'iowa','nebraska','oklahoma','arkansas','louisiana','alabama','mississippi',
 'kentucky','west virginia','idaho','montana','wyoming','alaska','hawaii',
 'new mexico','south dakota','north dakota','vermont',
 'bavaria','sachsen','north holland','zuid-holland','flemish region',
 'catalunya','valencian community','calabria','vicenza','lower austria',
 'auvergne-rhône-alpes','île-de-france','hovedstaden','dki jakarta',
 'karnataka','punjab','lagos state','lagunes','new south wales','victoria',
 'riyadh region','goiás','lombardia','greater accra','abu dhabi','sharjah',
 'vaud','bs','stj',
}

def _norm(s):
    return re.sub(r'\s+', ' ', str(s or '')).strip().lower()

def _strip_postcode(seg):
    """Drop trailing postcode tokens and bare state/province codes.

    Postcodes here always contain a digit and city names never do, so peeling
    digit-bearing trailing tokens covers every format seen (UK full and partial
    outcodes, US ZIP+4, Canadian, European). Short all-caps tokens are state or
    province abbreviations ('NY 10001' -> '', 'Massachusetts MA' -> 'Massachusetts').
    """
    toks = str(seg or '').split()
    while toks and (any(c.isdigit() for c in toks[-1])
                    or (len(toks[-1]) <= 3 and toks[-1].isupper() and toks[-1].isalpha())):
        toks.pop()
    return ' '.join(toks).strip(' ,-')

STREET_LAST = {
 'road','rd','street','st','avenue','ave','lane','ln','drive','dr','way',
 'place','pl','square','sq','court','ct','close','terrace','parkway','pkwy',
 'highway','hwy','plaza','wharf','quay','mews','crescent','walk','gate','row',
 'hill','broadway','americas','towers','tower','wing','house','mill','works',
 'studios','estate','floor',
}

def _looks_like_street(seg):
    s = str(seg or '').strip()
    if re.match(r'^(unit|suite|floor|level|building|po box|block|apt|room|ste|'
                r'bldg|office)\b', s, re.I):
        return True
    if re.match(r'^\d+(st|nd|rd|th)\s+floor$', s, re.I):
        return True
    if ' - ' in s:                       # "Netherlands - Belgium - Dubai - UK"
        return True
    toks = s.split()
    return bool(toks) and toks[-1].strip('.,').lower() in STREET_LAST

def parse_address(addr):
    """Postal address -> (city, country). Either may be ''."""
    if not str(addr or '').strip():
        return '', ''
    parts = [p.strip() for p in str(addr).split(',')]
    parts = [p for p in parts if p and _norm(p) not in NOWHERE]
    if not parts:
        return '', ''

    country = ''
    while parts and _norm(parts[-1]) in CONTINENTS:
        parts.pop()
    if not parts:
        return '', ''

    # "…, Arlington, TX 76017" -- US state + ZIP with the country code omitted
    if re.match(r'^[A-Z]{2}\s+\d{5}(-\d{4})?$', parts[-1].strip().upper()):
        country = 'United States'
        parts.pop()
        if not parts:
            return '', country

    # a trailing postcode-only segment can hide the country ("…, Russia, 105082")
    while (len(parts) > 1 and not _strip_postcode(parts[-1])
           and parts[-1].strip().upper() not in ISO
           and _norm(parts[-1]) not in COUNTRY_NAMES):
        parts.pop()

    last, up = parts[-1], parts[-1].strip().upper()
    if country:
        pass
    elif up in ISO:
        country = ISO[up]; parts.pop()
    elif _norm(last) in COUNTRY_NAMES:
        country = COUNTRY_NAMES[_norm(last)]; parts.pop()
    elif _norm(_strip_postcode(last)) in COUNTRY_NAMES:      # "France 92220"
        country = COUNTRY_NAMES[_norm(_strip_postcode(last))]; parts.pop()

    while parts and _norm(parts[-1]) in CONTINENTS:
        parts.pop()
    if not country:
        for seg in reversed(parts):
            if _norm(_strip_postcode(seg)) in REGION_COUNTRY:
                country = REGION_COUNTRY[_norm(_strip_postcode(seg))]
                break
    if not parts:
        return '', country

    def scan(allow_region):
        for i in range(len(parts) - 1, -1, -1):
            base = _strip_postcode(parts[i])
            base = re.sub(r'^\d[\d\-/]*\s+(?=\S)', '', base).strip()  # "91000 Tawau"
            nb = _norm(base)
            if not base or nb in NOWHERE or nb in CONTINENTS:
                continue
            if re.fullmatch(r'[\d\s\-]+', base):
                continue
            if not allow_region and (nb in REGIONS or nb in COUNTRY_NAMES):
                continue
            if _looks_like_street(base):
                continue
            return base
        return ''

    # Pass 1 skips regions; pass 2 allows them, because several names are both
    # a region and a real city.
    city = scan(False) or scan(True)
    city = re.sub(r'\s{2,}', ' ', city).strip(' ,.-')
    if _norm(city) in NOWHERE:
        city = ''
    if city.isupper() and len(city) > 3:
        city = city.title()
    return {'Luxemburgh': 'Luxembourg', 'The Joan': ''}.get(city, city), country


def parse_person_location(raw, fallback_country=''):
    """Clay Person Location ('London, England, United Kingdom') -> (city, country).

    A country-only value carries no city. Clay sometimes returns a LinkedIn
    headline instead of a location; those are rejected outright.
    """
    raw = str(raw or '').strip()
    if not raw or _is_headline(raw):
        return '', fallback_country
    parts = [p.strip() for p in raw.split(',') if p.strip()]
    if not parts:
        return '', fallback_country

    country = fallback_country
    if len(parts) >= 2 and _norm(parts[-1]) in COUNTRY_NAMES:
        country = COUNTRY_NAMES[_norm(parts[-1])]
    elif len(parts) == 1 and _norm(parts[0]) in COUNTRY_NAMES:
        return '', COUNTRY_NAMES[_norm(parts[0])]

    city = ''
    if len(parts) >= 2:
        city = _tidy_locality(parts[0])
    elif _norm(parts[0]) not in COUNTRY_NAMES:
        city = _tidy_locality(parts[0])
    if _norm(city) in COUNTRY_NAMES or _norm(city) in NOWHERE:
        city = ''
    return city, country


def _is_headline(s):
    """LinkedIn headlines leak into the location field; reject them."""
    s = str(s or '')
    return ('|' in s or len(s) > 60 or re.search(r'\bat\s+\S', s)
            or s.count(',') > 4)

def _tidy_locality(seg):
    """'Greater Reading Area' -> 'Reading'; 'London Area' -> 'London'."""
    c = str(seg or '').strip()
    c = re.sub(r'^Greater\s+', '', c, flags=re.I)
    c = re.sub(r'\s+Metropolitan\s+Area$', '', c, flags=re.I)
    c = re.sub(r'\s+Metropolitan$', '', c, flags=re.I)
    c = re.sub(r'\s+Area$', '', c, flags=re.I)
    c = re.sub(r'\s+District$', '', c, flags=re.I)
    return c.strip()

# ------------------------------------------------------------ employees -----

def employee_count(value):
    """Headcount band -> one number (the top of the band).

    '51-200' -> 200,  '10,000+' -> 10000,  '2-10' -> 10,  '500' -> 500.
    Returns '' when there is nothing to read.
    """
    s = str(value or '').strip()
    if not s:
        return ''
    nums = [int(n.replace(',', '')) for n in re.findall(r'\d[\d,]*', s)]
    return str(max(nums)) if nums else ''

# --------------------------------------------------------------- phone ------

def phone(value, keep_plus=False):
    """Digits only (matching the agreed output), or E.164 with keep_plus."""
    s = str(value or '').strip()
    if not s:
        return ''
    digits = re.sub(r'\D', '', s)
    if not digits:
        return ''
    return ('+' + digits) if keep_plus else digits

# ------------------------------------------------------------- industry -----

from industry_map import INDUSTRY_MAP

def industry(value):
    """Source industry -> (taxonomy label, taxonomy value). ('','') if unknown."""
    return INDUSTRY_MAP.get(str(value or '').strip(), ('', ''))

# ---------------------------------------------------------------- build -----

def build_row(rec, keep_plus=False):
    ccity, ccountry = parse_address(rec.get('company_address'))
    pcity, pcountry = parse_person_location(
        rec.get('contact_location_raw'), rec.get('contact_country_ticket', ''))
    ind_label, ind_value = industry(rec.get('industry'))
    return {
        'First Name':        str(rec.get('first') or '').strip(),
        'Last name':         clean_last_name(rec.get('last')),
        'Company name':      str(rec.get('company') or '').strip(),
        'Company domain':    str(rec.get('domain') or '').strip().lower(),
        'Company City':      ccity,
        'Company Country':   ccountry,
        'Contact City':      pcity,
        'Contact Country':   pcountry,
        'LinkedIn':          str(rec.get('linkedin') or '').strip(),
        'Email':             str(rec.get('email') or '').strip(),
        'Phone number':      phone(rec.get('phone'), keep_plus),
        'Job title':         str(rec.get('title') or '').strip(),
        'Event status':      str(rec.get('status') or '').strip(),
        'Industry (mapped)': ind_label,
        'Industry (value)':  ind_value,
        'Employees':         employee_count(rec.get('employees')),
        'Company LinkedIn':  str(rec.get('company_linkedin') or '').strip(),
        'Company website':   str(rec.get('website') or '').strip(),
    }

def build_scan_row(rec, keep_plus=False):
    """Do-not-contact row: the shared core plus the booth-scan context."""
    row = build_row(rec, keep_plus)
    for col, field in zip(SCAN_COLS, SCAN_FIELDS):
        row[col] = str(rec.get(field) or '').strip()
    return row

def write_csv(records, out_path, keep_plus=False, scans=False):
    """Write the contact list, or the do-not-contact sheet with scans=True."""
    cols = OUT_COLS + SCAN_COLS if scans else OUT_COLS
    builder = build_scan_row if scans else build_row
    rows = [builder(r, keep_plus) for r in records]
    with open(out_path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader(); w.writerows(rows)
    return rows

def report(records, rows):
    n = len(rows) or 1
    unmapped = sorted({str(r.get('industry') or '').strip()
                       for r in records
                       if str(r.get('industry') or '').strip()
                       and not industry(r.get('industry'))[0]})
    def filled(col):
        return sum(1 for r in rows if r[col])
    lines = [f'rows: {len(rows)}']
    for col in ('Company City', 'Company Country', 'Contact City',
                'Contact Country', 'Company domain', 'LinkedIn',
                'Industry (mapped)', 'Employees', 'Phone number'):
        lines.append(f'  {col:<18} {filled(col):>4}/{len(rows)}  ({100*filled(col)/n:.1f}%)')
    if unmapped:
        lines.append('UNMAPPED INDUSTRIES (add to industry_map.py): ' + ', '.join(unmapped))
    dup = {}
    for r in rows:
        if r['Email']:
            dup.setdefault(r['Email'].lower(), []).append(r)
    dups = [e for e, v in dup.items() if len(v) > 1]
    if dups:
        lines.append(f'DUPLICATE EMAILS ({len(dups)}): ' + ', '.join(dups[:10]))
    return '\n'.join(lines)

if __name__ == '__main__':
    if len(sys.argv) < 3:
        sys.exit('usage: transform.py records.json out.csv [--keep-plus] [--scans]')
    recs = json.load(open(sys.argv[1], encoding='utf-8'))
    rows = write_csv(recs, sys.argv[2], keep_plus='--keep-plus' in sys.argv,
                     scans='--scans' in sys.argv)
    print(f'wrote {sys.argv[2]}')
    print(report(recs, rows))
