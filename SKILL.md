---
name: event-contact-list
description: Turn a raw event/conference attendee export into a clean, CRM-ready contact list — remove a do-not-contact ("bad scans") list, dedupe, enrich missing company HQ and contact city via Clay, map industries to the CRM picklist, and write the agreed CSV schema. Use when asked to build/structure/clean an event contact list, post-event attendee or badge-scan list, an outreach list from a conference export, or to re-run that structuring on a new event.
---

# Event contact list → CRM-ready CSV

Produces one CSV in a fixed 18-column schema (below). Deterministic transforms
live in `scripts/transform.py`; `scripts/industry_map.py` holds the
industry picklist mapping. The Clay work needs orchestration, so it is
described here as steps.

Everything below assumes the `clay` CLI is installed and signed in
(`clay whoami`). Check `clay credits` before the enrichment steps.

Two sheets come out of this, both sharing the same first 18 columns so they
line up: the **contact list** (everyone who may be contacted) and the
**do-not-contact sheet** (the bad scans, kept as a record of who was removed
and why, with the booth conversation attached).

## Output schema — do not reorder or rename

```
First Name, Last name, Company name, Company domain,
Company City, Company Country, Contact City, Contact Country,
LinkedIn, Email, Phone number, Job title, Event status,
Industry (mapped), Industry (value), Employees,
Company LinkedIn, Company website
```

- **Company City / Country** — parsed from the company's HQ postal address.
- **Contact City / Country** — where the *person* is, from their LinkedIn profile.
- **Industry (mapped)** is the display label, **Industry (value)** the API value.
  Both are emitted because the picklist mixes `UPPER_SNAKE` values with
  labels repeated verbatim; the importer takes whichever it needs.
- **Employees** is a single number, never a range (`51-200` → `200`).
- **Phone number** is digits only, no `+`. Pass `--keep-plus` for E.164.
- Written UTF-8 with BOM so Excel preserves accents (`Côte d'Ivoire`, `José`).

The do-not-contact sheet appends the booth-scan context after those 18:

```
Lead source, Lead quality, Booth member, Lead comment, Exhibitor comment,
Scan time, Decision making role, Solutions spend, Solution needs,
Future speaking, Present in Contact List?
```

`Present in Contact List?` records the audit trail — `Removed (was row N)`, or
`Not present - nothing to remove` when the scan had no match in the full list.

## Step 1 — read the source

Event exports are usually one workbook with several tabs: a full attendee list
and a badge-scan / "bad scans" list. Read the real file, not a text preview —
natural-language previews of spreadsheets run rows together and corrupt the
data. Get the actual bytes:

```bash
# Drive: download_file_content, then decode the base64 the tool result saved
python3 -c "
import json,base64
d=json.load(open('<saved-tool-result>.txt'))
open('source.xlsx','wb').write(base64.b64decode(d['content']))"
python3 -c "
import openpyxl
wb=openpyxl.load_workbook('source.xlsx',data_only=True)
for ws in wb.worksheets: print(ws.title, ws.max_row, ws.max_column)"
```

Confirm with the user which tab is the contact list and which is the
do-not-contact list before removing anything.

## Step 2 — remove the do-not-contact list (the accuracy-critical step)

Match each do-not-contact row against the full list on:

1. **Email**, normalised lowercase — the strongest signal.
2. **First + last name**, accent- and case-folded, with the company name
   corroborating. Needed because badge scans often capture a personal email
   while the attendee list has the work one.

**Never match on phone number alone.** Event exports reuse switchboard numbers
and placeholders (`+447000000000`, `+440`) across many rows — phone matching
looks productive and silently removes innocent contacts.

Then re-check with a fuzzy name sweep (`difflib.SequenceMatcher` ≥ 0.72) across
every row, and eyeball the near-misses: distinct people who share a surname
(e.g. two unrelated people both surnamed Smith) must be kept.

Report do-not-contact rows that are **not** in the full list — that is normal
and means nothing to remove, not a failed match.

## Step 3 — dedupe on email

Same person often registers twice with different statuses. Keep one row per
email, preferring the best status (`Attended` > `No-show` > `Cancelled in
advance via email`), and backfill any field the winner is missing from the
loser. Report what was merged.

## Step 4 — enrich the gaps with Clay

Derive first, then enrich, so no credits go on data already present:

- **Company domain** — take it from the website column; otherwise from the
  email domain when it is not free mail (gmail/outlook/hotmail/yahoo/icloud/
  btinternet/live/aol…).
- Everything else needs Clay. Bulk runs are JSONL, one `{"id","inputs"}` per line:

```bash
clay routines runs start <routineId> --bulk rows.jsonl
clay routines runs get <runId> --bulk --wait 900        # returns a resultUrl
curl -sS "<resultUrl>" -o out.jsonl
```

| Need | Routine (create these in your Clay workspace) | Inputs |
|---|---|---|
| Company HQ address | Company Address | `Company Domain` (req), `Company Name` |
| Contact city | Person Location | `Work Email` (req) + `Social Profile URL`, `Full Name`, `Company Domain` |
| Person / LinkedIn URL | Enrich Person | `Email` or `Professional Profile URL` |
| Domain from name only | Company Domain | `Company Name` |

Run `clay routines list` to look up your routine ids and put them in a local, uncommitted config.

Notes that cost real time to learn:

- Deduplicate inputs by domain before the address run — ~500 companies for
  ~900 contacts, so it roughly halves the spend.
- Pass **every** identifier you have to Person Location, not just the email;
  match rate is far higher with the LinkedIn URL included.
- **Percent-encode non-ASCII URLs** or the whole bulk run fails validation
  with `validation_failed` naming one line (`…/in/josé-núñez` →
  `urlsplit` + `quote` the path).
- A bulk run can sit at *n-1 of n* for many minutes. Use `--wait 900` and let
  it finish; don't cancel and re-run.
- **Do not accept name-only domain guesses.** The Company Domain routine
  returns confident wrong answers for generic names ("Access" → an Egyptian
  travel firm; a company literally named "none" → a dental practice). Accept
  only where the domain is verifiable from the email or website; otherwise
  leave blank and list them for the user.
- Person Location occasionally returns a **LinkedIn headline** instead of a
  location. `transform.py` rejects these, but sanity-check the Contact City
  column for long values or `|`.

## Step 5 — transform and write

Build a JSON array of records with these keys (missing keys are fine):

```
first, last, company, domain, company_address, contact_location_raw,
contact_country_ticket, linkedin, email, phone, title, status,
industry, employees, company_linkedin, website
```

`last` may still carry post-nominals; `company_address` and
`contact_location_raw` are the raw Clay strings. Then:

```bash
python3 <skill-dir>/scripts/transform.py records.json "Event - Contact List.csv"
python3 <skill-dir>/scripts/transform.py scans.json "Event - Bad Scans.csv" --scans
```

`--scans` switches to the do-not-contact schema and additionally reads
`lead_source, lead_quality, booth_member, lead_comment, exhibitor_comment,
scan_time, dm_role, spend, needs, future_speaking, present_note`.

It prints a fill-rate report, flags duplicate emails, and lists any source
industry it could not map — add those to `scripts/industry_map.py` rather than letting
them become blanks.

What the transforms handle, so you don't re-derive it:

- Post-nominals stripped from surnames (`Smith ACCA` → `Smith`).
- Addresses: postcodes in every format, US addresses with no country code
  (`Arlington, TX 76017`), state/province codes that would otherwise land in
  the city field, regions where a city belongs (a county + postcode → the
  postcode's town), street and building lines (`<street> <postcode>` → city), continent suffixes, and names that are both a
  region and a real city (New York, Bristol, Tokyo, Schaffhausen) via a
  second relaxed pass.
- Placeholder addresses (`Worldwide`, `Global`, `PO Box, Global`, a bare
  country) yield **blank** city — never a guess.
- LinkedIn localities normalised to real cities (`Greater Reading Area` →
  Reading, `London Area` → London, `Lahore District` → Lahore).
- Contact Country prefers Clay's country over the ticket country, which is
  frequently wrong (a Berlin-based attendee on a UK ticket).

## Step 5b — fill the do-not-contact sheet from the full list, not from Clay

A badge-scan export is thin: usually just name, email, phone, title, company
and the booth notes. No company address, industry, headcount, LinkedIn or
website. Do **not** reach for Clay first — nearly every scanned person is also
in the full attendee list, so join each scan to the row it knocked out (you
already have that mapping from step 2) and take the firmographics and the real
`Event status` from there. Then:

- Back-fill anything still missing from **any** full-list row sharing the same
  company domain — that covers scans with no match of their own.
- Only then run Clay Company Address for domains the address run never saw,
  because step 4 deduplicated on the *kept* contacts and excluded companies can
  be absent.

On the last event this filled 25/26 company cities for ~14 credits, where
enriching all 26 from scratch would have cost several times that and returned
less.

Leave `Event status` blank for a scan with no full-list match — being scanned
at the booth is not an attendance status, and inferring one invents data.

## Step 6 — verify before handing over

```bash
python3 -c "
import csv
rows=list(csv.DictReader(open('out.csv',encoding='utf-8-sig')))
print('rows',len(rows),'| widths',{len(r) for r in rows})
print('unique emails',len({r['Email'].lower() for r in rows if r['Email']}))
bad={'<do-not-contact emails>'}
print('LEAKS', sorted(bad & {r['Email'].lower() for r in rows}))
print('suspect cities',[r['Contact City'] for r in rows
                        if len(r['Contact City'])>40 or '|' in r['Contact City']])
"
```

Confirm: row count matches expectation, every row the same width, no
do-not-contact email present, no suspect city values.

Save the CSV to the user's Desktop **and** Downloads and `open -R` it —
they will look for it in Finder. State fill rates and what was deliberately
left blank; never present a guessed value as enrichment.
