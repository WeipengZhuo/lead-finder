---
description: Build your profile once (offer, proof, voice, clients, memberships) so leads fit you and notes sound like you.
argument-hint: "[website URL] [LinkedIn URL]"
allowed-tools: Bash(python3:*), Read, Write, Edit, AskUserQuestion
---

Build `<home>/profile.md` for this user. The user may have passed a website and LinkedIn URL in the arguments: `$ARGUMENTS`. Ask for them if missing.

## Steps

1. If the home folder or token is missing, send the user to `/lead-finder:setup` first.

2. Read the user's pages (free). `fetch` needs no brief and no spend, so run it directly into the `profile` run folder:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/lf.py" fetch profile --urls https://example.org,https://www.linkedin.com/in/example
```

Do not write a `brief.json` for this run; a brief with a non-date slug is rejected.

Replace the URLs with the user's. LinkedIn often blocks reads; use whatever came back and ask for the rest. If the fetch is refused, ask the user to paste the text of their site's About and Services pages instead.

3. From the pages, draft what you can for each section below. Then ask only what is missing: at most 2 rounds of 4 questions. Use AskUserQuestion if available; otherwise a numbered list and "reply like 1b 2a". Questions to cover (skip any already answered):
   - Offers and prices: what they sell, to whom, at what price range.
   - Proof: two or three results, named clients they may mention, numbers.
   - Topics: what they speak, write or coach about.
   - Voice: how they write. Ask for two real messages they have sent to a stranger and liked the result of.
   - Never-say words: phrases they hate.
   - Clients: current clients and organizations to leave alone.
   - Memberships: associations or groups they belong to.
   - Parent organizations: who owns or oversees their clients' organizations.

4. Write `<home>/profile.md` with exactly these sections, plain and short:

```
# Profile

## Offers & prices
## Proof
## Topics
## Voice rules
(3 to 5 bullets: sentence length, formality, greeting, sign-off, what they never do)
## Two real messages
(pasted verbatim)
## Never-say words
## Clients
## Memberships
## Client parent orgs
```

5. Add exclusions without asking again, then tell the user exactly what you added:
   - Each client's website domain goes into `<home>/exclusions.csv` as `domain,<domain>,client`.
   - Each membership organization's domain goes in as `domain,<domain>,member: warm ask`.
   - Each client parent organization's domain goes in as `domain,<domain>,client parent`.
   Use the Edit tool to append rows; keep the header `kind,value,reason`. If a domain is unknown, add a `name_keyword` row instead.

6. Show the user a short summary of the profile and the exclusions you added. Ask them to correct anything. Then point to `/lead-finder:find`.

Style: plain, short, no emoji, no em or en dashes. Never put a client's real details anywhere except `profile.md` and `exclusions.csv`.
