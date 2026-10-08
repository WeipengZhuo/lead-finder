# Recipe: podcast guesting

Draft recipe, not yet field-tested. Treat the query templates and yield numbers as starting points and report what worked after the first run.

Find podcasts and interview shows that book guests on the user's topic, and the one person who books them (usually the host or producer).

Brief field `recipe`: `podcast-guesting`.

## Interview options

Recommended option is first in each list.

**Goal** (fixed by this recipe): get booked as a podcast guest.

**Who decides (org types)**
- a. Niche shows aimed at my buyers' profession (Recommended)
- b. Association and industry-body podcasts
- c. Business and leadership interview shows
- d. Free text

**Who decides (titles)**
- a. Host or founder (Recommended)
- b. Producer or booking contact
- c. Content or partnerships lead (for company-run shows)

**Where**
- a. Anywhere, remote recording (Recommended)
- b. In person only
- c. Free text

**Organization size**
- a. Any size (Recommended)
- b. Independent shows only
- c. Company or association shows only

**Hot signals**
- a. Episode in the last 60 days and a "be a guest" or "apply" page (Recommended)
- b. New season announced
- c. Show recently sponsored or relaunched

**Count and cap**
- a. 10 leads, $0.25 (Recommended)
- b. 25 leads, $0.60

## Brief defaults

```
org_types: podcast, association podcast, company podcast
titles_tier_a: Host, Founder, Producer, Booking Manager
titles_fallback: Content Director
size_min: 1, size_max: 500
signals: guest application page, episode in last 60 days
target_count: 10, budget_usd: 0.25
```

## Query templates

Fill in `{topic}`, `{audience}`, `{niche}`.
- `{niche} podcast guest application page`
- `{niche} podcast "be a guest" OR "pitch us" OR "guest submission"`
- `{audience} podcast interviews {topic} episode {year}`
- `podcast for {audience} "guest" {topic} apply`
- `{state} society {niche} podcast`

## Zero-yield patterns (expected, to confirm)

- Generic "podcast be a guest" queries return how-to articles and booking marketplaces (observed in the speaking-gigs run).
- Directory pages (podcast app listings) are not leads. Open the show's own site.
- Pay-to-play guest booking agencies are intermediaries; exclude them.

## Title tiers

- **Tier A:** Host, Founder, Producer, Booking Manager.
- **Fallback:** Content Director.
- Small shows often list only the host. That is fine; the host is the booker.

## Screening rules

1. A real show with an episode in the last 60 days (check the episode list).
2. Its audience matches the user's buyers, not just their topic.
3. Not a pay-to-play guest booking agency, not a marketplace.
4. Not the user's own client, a client's parent, or a show the user already appeared on (note it as a warm ask if so).
5. Prefer shows with a published guest page; quote its rule ("episodes are 30 minutes", "submit a one-paragraph pitch") in `why_fit`.
6. One show, one contact.

## Exclusions to hunt for

See `references/exclusion-heuristics.md`. Pay-to-play booking agencies, networks that rebrand the same show under many names, and shows whose host is the user's client.

## Opener angle

One line that names a recent episode and the specific idea the user could bring.

Pattern: `I listened to your episode on {topic}; I have a story on {angle} your audience of {audience} rarely hears. Want a two-line pitch?`

Write in the user's voice. Name an episode the user can verify. Never praise generically.

## Budget default

10 leads at $0.25, 25 leads at $0.60. Search and page reads are free, so cost is email lookups and checks. Many podcast hosts publish a booking email, which costs nothing: use it and mark `email_source=page`.

## Status

Draft recipe, not yet field-tested.
