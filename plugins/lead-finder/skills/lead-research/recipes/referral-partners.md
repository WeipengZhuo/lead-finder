# Recipe: referral partners

Draft recipe, not yet field-tested. Treat the query templates and yield numbers as starting points and report what worked after the first run.

Find professionals and firms who serve the same buyers as the user without competing, so they can send introductions both ways, and the one person who runs partnerships there.

Brief field `recipe`: `referral-partners`.

## Interview options

Recommended option is first in each list.

**Goal** (fixed by this recipe): find referral and co-marketing partners.

**Who decides (org types)**
- a. Small firms that serve my buyers with an adjacent service (Recommended)
- b. Associations and networking groups my buyers join
- c. Software and platform vendors with partner programs
- d. Free text

**Who decides (titles)**
- a. Founder, owner or managing partner (Recommended)
- b. Head of partnerships or alliances
- c. Executive director (associations)

**Where**
- a. My region plus remote (Recommended)
- b. In person only
- c. National

**Organization size (staff)**
- a. 2 to 100 (Recommended)
- b. 11 to 500
- c. Any size

**Hot signals**
- a. A partner or referral page on their site (Recommended)
- b. Recently launched a service adjacent to mine
- c. Hosts events or webinars my buyers attend

**Count and cap**
- a. 10 leads, $0.25 (Recommended)
- b. 25 leads, $0.60

## Brief defaults

```
org_types: professional services firm, association, software vendor
titles_tier_a: Founder, Managing Partner, Head of Partnerships, Director of Partnerships, Executive Director
titles_fallback: Director of Business Development
size_min: 2, size_max: 100
signals: partner page, referral program, adjacent service
target_count: 10, budget_usd: 0.25
```

## Query templates

Fill in `{buyer}`, `{adjacent service}`, `{city}`, `{state}`.
- `{adjacent service} firm for {buyer} {city}`
- `partner program {adjacent service} {buyer} "become a partner"`
- `referral partners {adjacent service} {state}`
- `{buyer} association sponsors {year} {adjacent service}`
- `{city} {buyer} networking group members {adjacent service}`

## Zero-yield patterns (expected, to confirm)

- Software directories and "best of" lists: they are ads, not firms.
- Pure lead-generation marketplaces: they sell leads, they do not partner.
- Search terms that name the user's own service: the results are competitors.

## Title tiers

- **Tier A:** Founder, Managing Partner, Head of Partnerships, Director of Partnerships, Executive Director.
- **Fallback:** Director of Business Development.
- In firms under 20 people the founder is the partnership lead.

## Screening rules

1. Serves the same buyers, with a non-competing service. If the service overlaps the user's offer, drop it.
2. Real firm with a live site and visible clients or case studies.
3. Not a lead-gen marketplace, directory or affiliate site.
4. Not the user's own client, a client's parent, or an organization the user already belongs to (a warm ask instead).
5. A partner page or a recent co-marketing signal strengthens the case; say which in `why_fit`.
6. One firm, one contact.

## Exclusions to hunt for

See `references/exclusion-heuristics.md`. Direct competitors, firms that are the user's clients, and firms under common ownership with a client.

## Opener angle

One line that names the overlap in buyers and a small, concrete exchange.

Pattern: `We both work with {buyer type}: you on {their service}, I on {user's service}. I can send you {kind of intro} when it fits; would a short call to compare notes make sense?`

Write in the user's voice. Name something real from their site. No flattery.

## Budget default

10 leads at $0.25, 25 leads at $0.60. Search and page reads are free. Small firms often publish the founder's email on a contact page; use it and mark `email_source=page`.

## Status

Draft recipe, not yet field-tested.
