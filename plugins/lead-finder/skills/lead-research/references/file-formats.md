# Files Lead Finder keeps

All files live in the user's working folder, called home. By default that is `lead-finder/` inside the shared folder, or the path in `LEAD_FINDER_HOME`, or a path passed with `--home`. Everything is plain text the user can open.

## Home folder

| File | What it is |
|---|---|
| `config.json` | Connection settings and the token. Readable only by the user. The token is never printed. Do not share this file |
| `profile.md` | The user's offer, proof, voice rules, clients and memberships. Written by `/lead-finder:profile` |
| `exclusions.csv` | Organizations to skip. Columns: `kind,value,reason`. `kind` is `domain`, `name_keyword` or `email` |
| `seen.csv` | Everyone already exported, so they are not suggested twice. Columns: `domain,email,run,ts` |
| `ledger.jsonl` | One line per paid or cached call: time, run, stage, endpoint, status, cost in micro-dollars. No names, emails or search text |
| `cache/` | Saved results of earlier calls. A repeated call is free |
| `runs/<slug>/` | One folder per search. The slug looks like `2026-10-05_philly-speaking` |

## Run folder

| File | Written by | What it is |
|---|---|---|
| `brief.json` | Claude | The goal, offer, geography, titles, queries, lead count and spend cap |
| `hits.jsonl` | search | Every search result: query, title, url, snippet, date, domain |
| `pages/<id>.md` | fetch | The text of each page that was read; first line is `<!-- url: ... -->` |
| `candidates.jsonl` | add, set, screen, contacts, emails, verify | One row per organization: event, deadline, contact, email, checks, status, opener |
| `people/<domain>.json` | contacts | The people found at one organization, as options |
| `leads.csv` | export | The deliverable: verified leads, soonest deadline first |
| `risky.csv` | export | Leads with an email that could not be fully verified |
| `summary.md` | export | Funnel counts, spend by endpoint, cache hits, next steps |
| `drafts.md` | `/lead-finder:draft` | Full first notes, one per chosen lead |

## brief.json fields

Required: `slug`, `recipe`, `target_count` (1 to 100), `budget_usd` (above 0, up to 20), `queries` (1 to 80, each with `q`). Others: `goal`, `offer`, `geo`, `virtual_ok`, `org_types`, `titles_tier_a`, `titles_fallback`, `size_min`, `size_max`, `signals`. Each query may carry `location` and `after_date`.

## candidates.jsonl row fields

`org`, `domain` (the key, lowercase, no `www.`), `org_type`, `event`, `event_date`, `event_url`, `cfp_deadline`, `why_fit`, `source_urls`, `contact_name`, `contact_title`, `contact_source` (`page`, `search` or `manual`), `linkedin`, `email`, `email_source` (`page`, `find` or `manual`), `find_verified`, `find_served_by`, `email_check`, `verify_detail`, `status`, `status_reason`, `opener`.

Statuses: `new` (added), `excluded` (skipped, with a reason), `ready` (has a contact), `verified`, `risky`, `dead`.

## leads.csv columns

`#, Organization, Event, Event date, Event / speaker page, Speaker call deadline, Contact, Title, Email, Email check, LinkedIn, Why it fits, Draft opener (edit freely)`

Rows are ordered by speaker-call deadline (soonest first, blank last), then by event date.

## Email check values

- `Verified`: a mailbox check said deliverable.
- `Verified (accept-all, score NN)`: the domain accepts all mail; a second checker rated it deliverable at NN of 100 (97 or higher).
- `Risky (score NN)`: accept-all domain and the second checker was not confident.
- `Invalid`: the address does not exist. The row is dropped.
- Empty: the check could not run (a network error); re-running `verify` retries it.

## What is never stored

Phone numbers, personal or free-mail addresses, home addresses. They are removed before anything is written to disk.
