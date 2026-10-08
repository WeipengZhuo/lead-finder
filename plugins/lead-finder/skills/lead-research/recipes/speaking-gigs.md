# Recipe: speaking gigs

Find organizations with an upcoming event that books outside speakers (keynotes, panels, emcees), and the one person who books them. Field-tested on a first real run: 10 verified leads for about $0.11 total.

Brief field `recipe`: `speaking-gigs`.

## Interview options

Recommended option is first in each list.

**Goal** (fixed by this recipe): book keynote, panel or emcee gigs.

**Who decides (org types)**
- a. Associations and professional societies with an annual conference (Recommended)
- b. Arts and civic nonprofits with a gala or luncheon
- c. Corporate summits and employee-leadership events
- d. Podcasts and webinar series with guest speakers

**Who decides (titles)**
- a. Conference, meetings and education directors (Recommended)
- b. Executive directors of small organizations
- c. Development or events directors (galas)
- d. Program chairs and committee leads

**Where**
- a. My home region plus 2-3 nearby metros, virtual OK (Recommended)
- b. In person only, my region
- c. National, virtual OK
- d. Free text

**Organization size (staff)**
- a. 11 to 1,000 (Recommended)
- b. 11 to 200
- c. Any size

**Hot signals**
- a. Call for speakers open, plus an event in the next 3-12 months (Recommended)
- b. Event in the next 3-12 months
- c. New program or new executive director

**Count and cap**
- a. 10 leads, $0.25 (Recommended)
- b. 25 leads, $0.60

## Brief defaults

```
org_types: association, arts/civic nonprofit, corporate summit, podcast
titles_tier_a: Conference Director, Director of Meetings, Director of Education, Program Chair, Director of Special Events, Executive Director
titles_fallback: Director of Development
size_min: 11, size_max: 1000
signals: call for speakers open, event in next 3-12 months
target_count: 10, budget_usd: 0.25
```

Set `after_date` on every query to about 4 months before today, so stale pages drop out.

## Query templates

Fill in `{topic}`, `{city}`, `{state}`, `{year}` (the next calendar year, plus the current one if it is early in the year). Each template below produced usable events in the field run.

Intent plus year plus topic:
- `call for speakers {year} {topic} conference`
- `{topic} summit {year} call for speakers`
- `{year} call for proposals {topic} annual meeting`

City plus format:
- `{city} gala {year} emcee host keynote nonprofit`
- `{year} leadership conference call for speakers association {city}`
- `{city} annual luncheon {year} keynote speaker`

Women's leadership calls (the richest seam for a keynote-plus-performance act; use it when the offer fits):
- `{year} women's leadership conference call for keynote speakers`
- `women's leadership summit {year} keynote RFP`

Association of associations (the audience books speakers for their own events, so one set can lead to more):
- `{state} society of association executives {year} conference call for proposals`
- `{state} chamber of commerce annual conference {year} speakers`

Named-niche podcasts and series:
- `{niche} podcast guest interview request`

Social posts surface the freshest calls, with deadlines in the snippet. Keep those hits:
- `"call for speakers" {topic} deadline {month} {year}`
- `"seeking speakers" {year} {topic}`

Run roughly 8 to 20 queries for a 10-lead run, about 60 percent usable per query is a good result. Add more angles, not rewordings, if yield is short.

## Zero-yield patterns (do not use)

- Generic "podcast be a guest" queries: they return how-to articles and marketplaces.
- "Seeking emcee for gala": it returns emcee vendors.
- "{city} nonprofit gala emcee": it returns ticketing, review and social-media noise.
- Any query that names a speakers bureau or "hire a speaker": the results are the competition.

## Title tiers

- **Tier A, in order:** Conference Director, Director of Meetings, Director of Education, Program Chair, Director of Special Events, Executive Director.
- **Fallback:** Director of Development. Small arts organizations often have no events role, so the development director owns the gala. Use it only when no tier A person exists.
- Read the staff and committee pages before the people database. A program committee chair named on the CFP page is the best contact, even if the database lists someone else.

## Screening rules

Apply before spending anything.
1. Real organization with its own event (not a list article, marketplace or ticketing page).
2. Event date late 2026 or later. A call that closed more than a few weeks ago is dead unless the page says it is still open.
3. Not a vendor, bureau, event producer or AMC acting only as a vendor.
4. Not the user's own client, a client's parent organization, or an organization the user belongs to (memberships become warm-ask notes).
5. Size inside the brief range. Treat database headcounts as noisy: a society may list its member count as staff. If the staff page shows under about 10 people, it is small, not large.
6. One organization, one contact.
7. Social-post snippets carry deadlines. Copy the deadline into `cfp_deadline` only when the snippet states it plainly, and confirm it on the event page if you can.

## Exclusions to hunt for

See `references/exclusion-heuristics.md`. For this recipe the common ones are:
- A conference run by an outside event-management firm (the CFP page footer or "produced by" line names it).
- A conference produced by an events company, not by the association (often a "women's conference" brand).
- A venue or arts organization that is the parent of one of the user's clients.
- Organizations the user's own site lists under memberships.
- An association whose only listed contact sits at an AMC: valid only if the page names that person as the conference or program contact. Flag the domain mismatch in the report.

## Opener angle

One line that names the event or call and the deadline, then what the user would bring in a few words.

Pattern: `Saw the call for keynotes for {event} closes {date}; I speak on {topic} for {audience type}. Worth sending a one-page overview?`

Use the user's real voice from `profile.md`, not this pattern word for word. Cite only what the page says.

## Budget default

About $0.01 to $0.025 per shipped lead in practice. For 10 leads set $0.25, which leaves headroom for email misses and accept-all checks. For 25 leads set $0.60.

Cost drivers: email lookups (fractions of a cent to $0.02 each, depending on the provider that serves them) and accept-all checks ($0.004 each). Search and page reads are free.

## Known limits

- Some trial data providers allow only a handful of calls per day. A 429 means skip that source for today; do not retry.
- Accept-all domains are common at associations. They stay risky unless the second checker rates them 97 or higher.
- A person's email on the org's own staff page beats any lookup. Use it and mark `email_source=page`.
