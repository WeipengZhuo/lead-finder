# Exclusion heuristics

`lf.py screen` catches exact matches: domains in `exclusions.csv`, domains or emails already in `seen.csv`, intermediary keywords in an org name, and free-mail addresses. Many exclusions hide behind a normal-looking page. Look for these before spending on contacts.

When you find one `screen` missed, set `status=excluded status_reason="..."` on the row and tell the user. Never edit `exclusions.csv` without telling the user.

## Event producers

The organization named on the page is not the one that books speakers; a production company is.
- A "produced by", "presented by" or "managed by" line in the footer or on the sponsor page that names a company with "events", "productions", "experiences" or "live" in its name.
- The event site and the producer's site share a template, or the contact form goes to the producer's domain.
- The same conference brand runs in many cities with identical text.
- The contact email is at the producer's domain, not the host organization's.
Action: exclude, or note "produced by X" and exclude. The producer is a vendor.

## Speakers bureaus and talent agencies

- Pages that say "book a speaker", "hire a speaker", "our roster" or list speakers with fees.
- A name containing "speakers", "talent", "booking" or "agency".
- Marketplaces where speakers pay to be listed.
Action: exclude. They are competitors for the same stage, or pay-to-play.

## Association-management companies (AMCs)

Many associations have no in-house staff; an AMC runs them. A management firm's staff then appear with the AMC's email domain.
- The staff page lists "Managed by" or the footer credits a management firm.
- The conference director's email domain differs from the association's domain.
- The same names appear on several unrelated associations' pages.
Rule:
- If the association's own page names an AMC person as the conference, meetings or program contact, keep it. They do book speakers. Use the AMC domain for the row and flag "AMC domain" in `why_fit` and in the report.
- If the only reachable person is a general AMC sales or account contact, or the "organization" itself is an AMC pitching services, exclude.

## Client parent organizations and affiliates

An organization may look unrelated and still be the parent of a client, or the client of a client.
- A venue, foundation or umbrella body whose site lists the user's client as a resident company or program.
- A university or health system that owns a client's department.
- A chapter of a national body when the user already works with the national body.
Action: compare `profile.md` (Clients, Client parent orgs) with each candidate's About and "our members" pages. If linked, exclude with reason "client parent" and mention it to the user.

## Memberships

The user's own site and `profile.md` may list associations they belong to. A membership is not a lead.
- Exclude with reason "member: warm ask".
- Report these separately: the user can ask a contact they already know, which beats a cold note.

## Competitors and intermediaries

- Coaching, consulting, PR, training and staffing firms when the user sells a similar service.
- Recruiting and staffing firms (`staffing`, `recruiting` are in the built-in list).
- Lead-gen marketplaces, directories and "best of" listicle sites.

## Dead or stale

- An event dated before late 2026 (unless the page shows a 2027 edition).
- A call for speakers that closed more than a few weeks ago.
- A site that was last updated years ago.

## How to record a hit

Set the reason in plain words so the user can read it later:
`status=excluded status_reason="event produced by an outside firm"`.
