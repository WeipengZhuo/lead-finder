# Recipe: coaching clients

Find leaders and teams who are likely to need executive communication coaching, speechwriting or presentation training right now, and the one person who buys it. This recipe is account-first: you start from companies, then look for a trigger event.

Brief field `recipe`: `coaching-clients`.

## Interview options

Recommended option is first in each list.

**Goal** (fixed by this recipe): win coaching or training engagements.

**Who decides (org types)**
- a. Mid-size companies and nonprofits with a recent leadership change (Recommended)
- b. Professional services and associations
- c. Healthcare and higher education
- d. Free text

**Who decides (titles)**
- a. Chief Communications Officer, VP Communications (Recommended)
- b. Chief of Staff to the CEO or president
- c. Head of Internal Communications
- d. Executive Director (small organizations)

**Where**
- a. National, remote coaching is fine (Recommended)
- b. My region only, in person
- c. Free text

**Organization size (staff)**
- a. 50 to 2,000 (Recommended)
- b. 11 to 200
- c. 200 to 10,000

**Hot signals**
- a. New CEO or president in the last 6 months (Recommended)
- b. Rebrand, merger or restructuring announced
- c. Public crisis or leadership transition
- d. Hiring a speechwriter or communications lead

**Count and cap**
- a. 10 leads, $0.25 (Recommended)
- b. 25 leads, $0.60

## Brief defaults

```
org_types: company, nonprofit, association
titles_tier_a: Chief Communications Officer, VP Communications, Chief of Staff, Head of Internal Communications, Executive Director
titles_fallback: Director of Communications
size_min: 50, size_max: 2000
signals: new CEO or president, rebrand, merger, crisis, hiring a speechwriter
target_count: 10, budget_usd: 0.25
```

The `budget_usd` default of 0.25 is an assumption for this recipe. Raise it to 0.40 if `estimate` shows it will not fit.

## Query templates

All discovery runs through the free web search (`search <slug>`), with the queries listed in `brief.json`. `lf.py` has no company-database, news or LinkedIn-post call in this version, so do not try to make those calls another way (an MCP or curl call would skip the spend cap and the ledger). Build account lists from the signal queries below, plus an industry-and-region phrasing such as `{industry} {size} employees {region} new CEO {year}`.

Signal queries:
- `new CEO named {year} {industry} announces leadership transition`
- `names new president {year} {industry} association`
- `rebrand announced {year} {industry} company new brand`
- `merger announced {year} {industry} integration communications`
- `hiring speechwriter {year}` and `director of executive communications hiring {year}`
- LinkedIn post signals (via search): `"excited to welcome" new CEO {industry} {year}`, `"we are hiring" "executive communications"`

The LinkedIn-style phrases above are ordinary web-search text. They sometimes surface public posts; do not expect many.

## Zero-yield patterns (draft, not yet measured)

- "Executive coach" or "communication coach near me": the results are other coaches.
- Job boards for coaches.
- Press-release wire pages with no named company.

## Title tiers

- **Tier A, in order:** Chief Communications Officer, VP Communications, Chief of Staff, Head of Internal Communications, Executive Director.
- **Fallback:** Director of Communications.
- For a new-executive trigger, the chief of staff or the communications head is usually the right door, not the new executive.

## Screening rules

1. Real organization, inside the size range.
2. A dated trigger inside the last 6 months, or an announced change coming in the next 6 months. State it in `why_fit` with its source URL.
3. Not a coaching, consulting, training or PR firm.
4. Not the user's own client, a client's parent, or an organization the user belongs to.
5. One organization, one contact.
6. Prefer organizations where the trigger is public and specific. A generic "growth" story is not a trigger.

## Exclusions to hunt for

See `references/exclusion-heuristics.md`. For this recipe: other coaching and communications consultancies, the user's current clients and their parent companies, and subsidiaries where the group's communications office is the real buyer (point to the group's communications head, not the subsidiary).

## Opener angle

One line that names the trigger and a small, specific offer.

Pattern: `With {leader} starting in {month}, the first all-hands and the first public remarks come fast; I help new executives prepare for both. Open to a short call?`

Do not copy this pattern. Write it in the user's voice, name the real trigger, and avoid flattery. If the trigger is a crisis, be restrained and practical, not salesy.

## Budget default

10 leads at $0.25, 25 leads at $0.60. This recipe is account-first, so expect a lower yield per query than speaking-gigs.

## Status

Draft recipe, built from the speaking-gigs recipe's method. Not yet field-tested on a real run. Report yield and cost after the first run so the numbers can be tuned.
