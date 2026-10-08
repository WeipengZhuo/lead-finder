---
description: Write a first note, in your voice, for each lead you choose. Never sends.
argument-hint: "<run slug> [row numbers, like 1,3,5]"
allowed-tools: Bash(python3:*), Read, Write, Edit
---

Write first notes for chosen leads. Arguments: `$ARGUMENTS` (a run slug, then optional row numbers from `leads.csv`; no rows means all exported leads).

1. Read `<home>/profile.md` (Voice rules, Two real messages, Never-say words, Offers, Proof) and `<home>/runs/<slug>/leads.csv`. If the run has not been exported, run:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/lf.py" export <slug>
```

2. For each chosen lead write one note:
   - 90 to 140 words.
   - In the user's voice: match the sentence length, greeting and sign-off from their two real messages and voice rules.
   - Opens with the specific event, call, deadline or signal from the lead's row, stated plainly and truthfully.
   - Says what the user offers in two or three sentences, with one proof point from the profile.
   - Ends with one small, easy ask.
   - No emoji, no em or en dashes, no "I hope this finds you well", no flattery cliches, none of the user's Never-say words.
   - Also write a subject line: short, honest, specific, no tricks.
   - If you cannot cite a true specific detail, say so and ask the user for one rather than writing something generic.

3. Write all notes to `<home>/runs/<slug>/drafts.md`, one section per lead: organization, contact, email, email check, subject, body.

4. Show a short summary and the path. Then give the CAN-SPAM reminder from `skills/lead-research/references/can-spam.md`: physical address, honest subject, an opt-out line, and honoring opt-outs within 10 business days. It is a checklist, not legal advice.

**Never send.** Do not email, message or submit anything. If a Gmail connector is available, create drafts in it only when the user explicitly asks, and never send.
