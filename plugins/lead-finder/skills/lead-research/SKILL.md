---
name: lead-research
description: Find leads, prospects and speaking gigs, and decide who to reach out to. Use when the user says "find leads", "find prospects", "find speaking gigs", "who should I reach out to", "find podcasts that want guests", "find coaching clients", "find referral partners", or asks for a short list of the right people with verified work emails and a first note. Runs an interview, searches the web, picks one contact per organization, verifies emails within a spend cap, and writes a CSV plus draft openers. Never sends anything.
allowed-tools: Bash(python3:*), Read, Write, Edit, AskUserQuestion
---

# Lead research

You turn "who do I want to reach?" into a short list of the right people, each with a verified work email, a reason they fit, and a one-line opener in the user's voice.

Two halves:
- You do the judgment: the interview, queries, screening, contact picking, openers.
- `lf.py` does everything deterministic: treg calls, spend caps, cache, ledger, privacy scrubbing, dedupe, exclusions, verification, export.

You never send anything. Not an email, not a LinkedIn message.

## Calling lf.py

Always call it as below. `${CLAUDE_PLUGIN_ROOT}` is text, filled in when this file loads. It is not a shell variable, so do not export it or rewrite it.

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/lf.py" [--home PATH] [--transport T] [--fresh] [--json] <subcommand> ...
```

Global flags go before the subcommand. Use `--home PATH` only if the user's folder is not the default (`./lead-finder` in the shared folder, or `LEAD_FINDER_HOME`). Use `--json` when you need to parse output. Use only the subcommands listed in `references/file-formats.md` and below: `init`, `config`, `doctor`, `brief-check`, `estimate`, `search`, `fetch`, `add`, `set`, `screen`, `contacts`, `emails`, `verify`, `export`, `spend`, `ingest`, `status`.

Exit codes: 0 ok, 2 bad input, 3 transport unavailable, 4 budget reached, 5 out of balance, 6 needs ingest.

## 1. First-run check

1. Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/lf.py" doctor`.
2. If the home folder or token is missing, or doctor exits 3: stop and send the user to `/lead-finder:setup`.
3. If `<home>/profile.md` does not exist: send the user to `/lead-finder:profile`. Do not interview without a profile, because the offer, proof, voice and exclusions come from it.
4. Otherwise read `profile.md` fully. Its Voice rules, Never-say words and Two real messages govern every opener you write.

## 2. The interview

At most 2 rounds of 4 questions. Never ask what `profile.md` already answers; pre-fill it and let the user confirm.

Pick the recipe BEFORE round 1. Infer it from `$ARGUMENTS` and the Offers and Topics in `profile.md` (for example, a request for "speaking gigs" or a profile built around keynotes means `speaking-gigs`). Then round 1 question 1 is a confirmation with the inferred recipe as **Recommended**. Every other question's options come from that recipe's "Interview options" section, with the **Recommended** option first. If the user picks a different recipe in question 1, discard the first-round answer to question 3 (who decides) and ask it again in round 2 with the new recipe's options, alongside the round 2 questions. The cap stays at 2 rounds and 8 questions total.

Mechanics:
- If the AskUserQuestion tool is available, use it, one round per call (4 questions).
- If it is not (Cowork), print a numbered text list with lettered options and say: "Reply like `1b 2a`. Anything you skip uses the Recommended option (the first one)."
- Always allow a free-text answer.

**Round 1**
1. Goal. A confirmation of the inferred recipe: speaking gigs, coaching clients, podcast guesting, referral partners. If the goal fits none, say so and use the closest recipe, then adjust the brief by hand.
2. Offer and proof. Propose the offer and one proof line from `profile.md`; the user confirms or edits.
3. Who decides. Organization types and job titles. Options come from the (confirmed) recipe's title tiers.
4. Where. Cities or regions, and whether virtual is fine.

**Round 2** (skip it if round 1 plus the recipe defaults already answer everything)
5. Organization size (staff count range).
6. Hot signals to favor (for example "call for speakers open", "new executive", "event in the next 3-12 months").
7. Extra exclusions beyond `exclusions.csv`: names or domains to avoid.
8. Count and spend cap. Default **10 leads / $0.25**. Alternative **25 leads / $0.60**. Free text allowed. The cap is a hard ceiling, not a target.

Then restate the brief in one sentence ("I will find 10 association and nonprofit event teams in Philadelphia and New York with a 2027 event, for keynote bookings, spending at most $0.25.") and continue unless the user objects.

## 3. Brief, check, estimate, go

1. Choose a slug: `YYYY-MM-DD_<kebab>` with today's date, and make sure `<home>/runs/<slug>/` does not already exist.
2. Write `<home>/runs/<slug>/brief.json` (shape in `references/file-formats.md`). Build the queries from the recipe's templates, filling in topic, year, city and state. Write 8 to 20 queries for a 10-lead run. Skip every pattern in the recipe's zero-yield list.
3. Run `brief-check <slug>`. Exit 2 lists every problem at once; fix them and re-run.
4. Run `estimate <slug>`.
5. Quote the cost in plain words: "Expected about $0.12, hard cap $0.25. Searching and reading pages is free; email lookups and checks cost fractions of a cent each." Then **wait for the user to say "go"**. Do not run a stage before that.

## 4. The stage loop

Run stages in order. After each one, read the output before deciding the next move. If any stage exits 4, 5 or 6, follow section 7.

### 4a. Search

Run `search <slug>`. It is free. Read the compact table and screen every hit with these rules:

- It is a real organization with its own events or programs (not a directory, list article, marketplace, Eventbrite, Yelp, or social noise).
- The event or opportunity is dated late 2026 or later. Drop anything that already happened.
- It is not a vendor, speakers bureau, talent agency, event producer, or an association-management company (AMC) acting only as a vendor.
- It is not the user's own client, a client's parent organization, or an organization the user belongs to. A membership is not a lead: it becomes a "warm ask" note for the user.
- Social-post hits (LinkedIn, Facebook, Instagram) are worth keeping: their snippets carry deadlines.

If the table gives fewer usable orgs than about 2.5 times the target count, add queries to `brief.json` (new angles from the recipe, not rewordings) and run `search <slug>` again. Prior queries are cached. Stop after two extra rounds and report the shortfall honestly.

### 4b. Read pages

For each surviving org, run `fetch` on the event or call page, plus the staff pages likely to exist (`/staff`, `/about`, `/team`, `/board-directors`, `/contact`):

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/lf.py" fetch <slug> --urls https://example.org/conference,https://example.org/staff --grep '(?i)(director|chair|committee|speaker|program|events|contact|@)'
```

Batch up to 10 URLs per call. From the output pull: event name and date, deadline for speaker applications, the right team, named staff with titles, and any **published emails** on the same domain. Read the saved page in `pages/` if the grep lines are not enough.

Then add the org:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/lf.py" add <slug> --json '{"org":"Example Society","domain":"example.org","org_type":"association","event":"Annual Conference 2027","event_date":"2027-03-11","event_url":"https://example.org/conference","cfp_deadline":"2026-11-13","why_fit":"Two-day leadership conference; speaker call open to Nov 13.","source_urls":["https://example.org/conference"]}'
```

`why_fit` is one factual sentence the user can check against the page. Leave `cfp_deadline` empty if the page gives none. Never invent a date. `add` refuses a duplicate domain; that is fine, move on.

If a staff page already names the right person, set them now and skip the contacts lookup for that org:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/lf.py" set <slug> example.org contact_name="Jane Doe" contact_title="Director of Conferences" contact_source=page
```

If the page publishes that person's email on the org's domain, also set `email=... email_source=page`.

### 4c. Screen

Run `screen <slug>`. It marks excluded rows with reasons. Read the reasons. Also apply `references/exclusion-heuristics.md` yourself, because many exclusions hide behind a normal-looking page (an event produced by an outside firm, an AMC-run association, a parent organization of a client). When you find one `screen` missed, set `status=excluded status_reason="..."` on that row and say so in the report.

Never edit `exclusions.csv` without telling the user what you added and why.

### 4d. Contacts: pick ONE per org

Run `contacts <slug>`. It saves `people/<domain>.json` and prints a ranked, numbered list for rows with no contact yet. It does not pick. You pick.

Each line reads `n. Full Name | Title | Country | linkedin | match:A/kw/-`. The match column says how the title fits the brief: `A` contains one of the recipe's tier-A titles, `kw` contains a booking or program word (event, conference, meeting, program, education, speaker, executive director, president and similar), `-` has nothing to do with booking. The list is sorted by match, then US first, then name. The search first asks for each tier-A title in strict mode (only data sources that honor the title filter answer), and only if every title misses makes one broad search for the org. Some sources ignore the title and return arbitrary staff, so read the match column, not the position alone.

When the best option is `-`, the stage prints `no role match for <domain>`. Do not pick from that list. Read the org's staff or about pages with `fetch --grep` (see 4b) and pick from the page, or skip the org with `set status=dead status_reason="no contact found"`. Never pick a person whose title has nothing to do with booking or programs just because they are listed.

Rules:
- One contact per organization. The best match by the recipe's title tiers, tier A first, in order.
- Use the recipe's fallback titles only when no tier-A title exists (for example a development director at a small arts organization that has no events role).
- Prefer a person named on the org's own staff page over a search-database name. If they disagree, trust the page.
- Skip anyone whose title shows they left, interim assistants, and volunteer board members unless the recipe says board members book speakers.
- If the contact works at an AMC, not at the org, keep them if the org's own page names them as the program or conference contact. Keep the org's own domain as the row key (`set` cannot change `domain`). Say "AMC-run; contact at <amc-domain>" in `why_fit` so the report can flag the domain mismatch. When you set the contact's email, use `email_source=page` if the org's page published it. If no email is published, the email lookup uses the org's domain and may miss; that is fine, report it as a flag.
- No usable person at all: `set status=dead status_reason="no contact found"`.

Record the choice:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/lf.py" set <slug> example.org contact_name="Jane Doe" contact_title="Director of Conferences" contact_source=search linkedin=https://www.linkedin.com/in/example
```

### 4e. Emails

Run `emails <slug>`. It looks up each chosen person by full name and domain, never by LinkedIn alone. **Never guess an email**, never build `first.last@` patterns, and never use a LinkedIn-only lookup (a miss is still charged). A miss is fine: the row gets "email not found". Do not repeat a find for the same person; the cache and the ledger already make a repeat a waste.

### 4f. Verify

Run `verify <slug>`. Rows end as `verified`, `risky` or `dead`. Report them exactly as in section 6.

### 4g. Openers

For each `verified` row (and risky ones the user may still want), write the opener with `set <slug> <domain> opener="..."`.

Rules:
- One line, 30 words or fewer, in the user's voice from `profile.md` (use its Voice rules and Two real messages; avoid its Never-say words).
- Cite the specific event, call, deadline or signal from this row's `why_fit`. It must be true and checkable.
- Say what the user offers in a few words, and ask one small thing.
- No flattery cliches ("I love your work", "huge fan", "I was blown away"), no "I hope this finds you well", no emoji, no em or en dashes.
- If you cannot cite a specific, true detail, leave `opener` empty and say so rather than writing something generic.

## 5. Export

Run `export <slug>`. It writes `leads.csv`, `risky.csv`, `summary.md` and updates `seen.csv`. Then run `spend <slug>` for the numbers.

## 6. The report to the user

Keep it short. Include:

1. A table of the exported leads: organization, event, speaker-call deadline, contact and title, email check. **Deadlines first**: soonest deadline at the top, as the CSV does.
2. A "Risky" list: leads with an accept-all domain or a low score, with the reason. Say they are usable at the user's discretion, not guaranteed.
3. Warm asks: organizations the user is a member of or already works with, excluded as leads, worth a personal note.
4. Flags: AMC domain mismatches, rows excluded by you and not by `screen`, orgs with no contact.
5. Spend vs budget: "Spent $0.11 of $0.25." Plus the cache-hit count if it saved anything.
6. File paths for `leads.csv`, `risky.csv`, `summary.md`.
7. The next step: edit the openers, then `/lead-finder:draft <slug>` for full first notes, or `/lead-finder:refine <slug>` to change the brief.

Wording for the verification column (D1). Use these words, not "guaranteed":
- **Verified**: a mailbox check said the address is deliverable.
- **Verified (accept-all, score NN)**: the domain accepts all mail, so a plain check cannot tell; a second checker rated it deliverable at NN out of 100.
- **Risky (score NN)**: the domain accepts all mail and the second checker was not confident. Send only if you are comfortable with a possible bounce.
- **Invalid**: dropped.
A check lowers bounce risk. It does not promise delivery or a reply.

CAN-SPAM reminder, before the user sends anything: the first note must carry a real physical mailing address, an honest subject line, a working way to opt out that is honored within 10 business days, and an ad disclosure if the message is an advertisement. Point to `references/can-spam.md`. This is a checklist, not legal advice.

## 7. Guardrails and stops

- **Never send.** No email, no LinkedIn message, no form submission. If a Gmail connector exists, create drafts only, and only when the user explicitly asks.
- **Exclusions:** never remove or add a row in `exclusions.csv` without telling the user.
- **Exit 4 (budget reached):** stop. Say in plain English: "I hit the spend cap of $X after $Y. Here is what I have so far." Report the partial result. Offer to raise `budget_usd` in `brief.json` only if the user agrees; then re-run the same stage. Finished work is cached.
- **Exit 5 (out of balance):** stop. Say: "Your treg balance is empty. Top up at treg.to under Team, then Billing, and tell me when it is done; everything finished so far is saved." Do not quote error bodies and never print the token.
- **Exit 3:** the connection or token does not work. Send the user to `/lead-finder:setup`.
- **Exit 7 (daily call limit):** stop. Say: "Your treg token hit its daily call limit. It resets tomorrow, or you can raise it at treg.to under Team, then agent tokens; everything finished so far is saved." Never quote the error body.
- **Exit 6 (MCP ingest mode):** there is no direct network access, so the stage printed the exact calls to make. Procedure:
  1. For each printed call, make it with the treg MCP `call` tool, using exactly the endpoint and arguments printed. Do not change them.
  2. Save each JSON result to its own file inside the run folder (for example `<home>/runs/<slug>/ingest/01.json`).
  3. Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/lf.py" ingest <slug> --stage <stage> --endpoint <endpoint> --file <file> [--params JSON | --body JSON] [--cost-usd X] [--strict]` for each, passing the same params or body you sent. Keep `--strict` when the printed command has it (the call carried the strict-filters header). The printed command already carries `--cost-usd` for paid endpoints; keep it. For `treg.people.email.find`, replace it with the real cost when the MCP result shows one (`cost_usd`, or `charged_micro` divided by 1,000,000), because a miss is free and a hit is not.
  4. `ingest` scrubs the saved file in place (phone numbers and personal emails removed), so the raw result never stays on disk. Do not keep other copies of MCP results.
  5. Re-run the same stage command. Ingested results are in the cache, so it continues and prints any further calls it needs.
- **Privacy:** never write phone numbers, personal emails or free-mail addresses into any file or reply. `lf.py` scrubs them; if one slips into a page you read, leave it out.
- **Real data only:** never invent a person, title, date, email or deadline. If you do not know, leave the field empty.
- **Style:** plain and short. No emoji. No em or en dashes. No filler words.

## 8. Refine

When the user reacts to results ("more nonprofits", "skip associations", "only Texas"), change the brief (or copy it to a new slug), re-run only the stages that change, and let the cache make repeats free. See `/lead-finder:refine`.
