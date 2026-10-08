# Endpoints and call rules

Everything goes through treg, a pay-per-call gateway, on the user's own account. `lf.py` makes the calls; this page is for understanding cost and for ingest mode. Prices below were measured on 2026-10-04 and will drift. The ledger is the truth; run `lf.py spend` for real numbers.

## Endpoint table

| Endpoint | Method | Used for | Budget estimate (USD) | Measured 2026-10-04 |
|---|---|---|---|---|
| `tinyfish.web.search` | GET | Discovery. Params: `query`, `domain_type=web`, `location`, `after_date`, `page` | 0 | Free. About 30 per minute, 500 per hour |
| `tinyfish.web.fetch` | POST | Read pages, up to 10 URLs per call, markdown | 0 | Free |
| `tinyfish.web.search.news` | GET | Not called by `lf.py` in this version (listed for reference) | 0 | Free |
| `treg.companies.search` | POST | Not called by `lf.py` in this version (listed for reference) | 0.002 | Not used in the speaking run |
| `treg.people.search` | POST | Named people at a domain, by title | 0.0025 | 12 calls cost $0.0008 total; mostly served free with names, titles and LinkedIn but no emails |
| `getleadsio.people.decision_makers` | POST | Decision makers with a flagged email | 0 | Free trial: 5 calls per day per team, resets 00:00 UTC. A 429 means skip it today. Times out on very large orgs |
| `treg.people.email.find` | POST | Work email from name plus domain | 0.01 | Usually $0.005; one provider charged $0.02; a LinkedIn-only lookup missed and was still charged about $0.006 |
| `treg.people.email.verify` | POST | Mailbox check | 0.002 | Usually free; sometimes $0.0015 |
| `bounceban.people.email.verify` | GET | Second check for accept-all domains | 0.004 | $0.004 each, returns a score 0 to 100 |
| `exa.web.search` | POST | Not called by `lf.py` in this version (listed for reference) | 0.007 | Not needed in the speaking run |
| `anyapi.linkedin.search.posts` | POST | Not called by `lf.py` in this version (listed for reference) | 0.002 | Not measured |

Measured speaking-gigs run (10 shipped leads): $0.1065 total over 163 calls, about $0.011 per shipped lead. Email lookups were $0.0862 of that; verification was about $0.02.

Not used: Google Events through a SERP provider was down (50304) and needed a JSON array body. Plain search plus social-post snippets covered the gap. Do not depend on it.

## Response shapes (for ingest mode)

- Search: `result.results[]` with `title,url,snippet,date,site_name,position`.
- Fetch: `result.results[]` with `url,final_url,title,description,text,author,published_date,format`, plus `result.errors[]`.
- People search: `result.output.people[]` (null on a miss). The row shape depends on which provider the router used, so do not assume field names. `lf.py` normalizes all three:
  - snake_case (quickenrich): `first_name,last_name,title,employee_linkedin,company_url,company_name,email_domain,has_email`.
  - camelCase (leadsforge): `firstName,lastName,jobTitle,linkedinUrl,location{city,state,country},company{domain,...}`. It ignores the `title` filter and returns arbitrary employees.
  - nested (aiark): `profile{first_name,last_name,full_name,title,headline}`, `link{linkedin}`, `location{country,city,state}`. It matches titles loosely.
  - Strict mode: send `X-Treg-Route-Strict-Filters: 1` on a titled search so only providers that honor the title answer; a miss then costs nothing and returns no loose matches. Strict and non-strict answers differ, so they are cached separately. In ingest mode pass `--strict` to `ingest` for a strict call (the printed command already does).
- Email find: `result.output.email` and `result.output.verified`.
- Email verify: `result.output.valid` and `result.output.status` (`valid`, `invalid`, `accept_all`, `catch_all`, `unknown`, `risky`).
- BounceBan: `result.result` (`deliverable`, `undeliverable`, `risky`, `unknown`), `result.score`, `result.is_accept_all`.
- Decision makers: `result.contacts[]`. It includes phone fields. `lf.py` drops them before saving; never copy them anywhere.

## Call rules

1. **Cap every call.** Each call carries a max-cost header (default 0.01, never above 0.05 without an explicit override). If the price would exceed it, the call is declined with a `route_max_cost` 402: treat it as a miss for that row and continue.
2. **429 or 5xx:** the provider is busy or down. Move to the next provider or the next row. Do not hammer it.
3. **Other 4xx:** the request was wrong or refused. Never retry it. Fix the input or skip the row.
4. **Never repeat an email find** for the same person. It costs again and returns the same answer. The cache serves repeats for free, but do not rely on it for a changed query.
5. **Never send a LinkedIn-only email lookup.** Always send full name plus domain. A LinkedIn URL may be added only alongside them.
6. **402 that is not `route_max_cost`:** the balance is empty. Stop, tell the user to top up (treg.to, Team, Billing), re-run later.
7. **The run cap is checked before each paid call.** If the next call would pass `budget_usd`, nothing is called and the stage stops with exit 4.
8. **The find endpoint's `verified` flag is a useful pre-filter.** In the field run, every "true" came back valid on the check, and no "false" did. Spend the check only where it adds information.
9. **The daily trial cap on decision-maker data** is the binding limit, not money. Save it for small and mid organizations.

## Headers sent by lf.py

- `X-Treg-Token`: the user's token. Never printed.
- `X-Treg-Route-Max-Cost`: the cap above.
- `X-Treg-Meta`: `run=<slug>,recipe=<recipe>`. Contains no names, emails or other personal data.
- `X-Treg-Route-Strict-Filters: 1`: only on titled `treg.people.search` calls (contacts stage). Never on the broad fallback call.
