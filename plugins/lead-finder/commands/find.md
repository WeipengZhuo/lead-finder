---
description: Find leads. Short interview, then a verified list of the right people with a first line for each.
argument-hint: "[what you want, in a sentence]"
allowed-tools: Bash(python3:*), Read, Write, Edit, AskUserQuestion
---

Find leads for this user. They may have given a starting idea: `$ARGUMENTS`.

Follow the `lead-research` skill (`skills/lead-research/SKILL.md`) from start to finish. It holds the method, the judgment rules and the guardrails. In short:

1. First-run check:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/lf.py" doctor
```

   No home, no token: send them to `/lead-finder:setup`. No `profile.md`: send them to `/lead-finder:profile`.

2. Interview: at most 2 rounds of 4 questions, using the matching recipe in `skills/lead-research/recipes/` for options and defaults. Restate the brief in one sentence.

3. Write `<home>/runs/<slug>/brief.json`, then:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/lf.py" brief-check <slug>
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/lf.py" estimate <slug>
```

   Quote the cost and **wait for the user to say "go"** before running any stage.

4. Stages, in order, reading each output before the next: `search`, screen the hits, `fetch` pages, `add` candidates, `screen`, `contacts`, pick one contact per organization with `set`, `emails`, `verify`, write openers with `set <slug> <domain> opener="..."`, `export`.

5. Report: table of leads (soonest deadline first), the risky list, warm asks, flags, spend vs budget, file paths. Remind about CAN-SPAM before the user sends anything (`skills/lead-research/references/can-spam.md`).

Stop on exit 4 (budget) or 5 (balance) and explain in plain English. On exit 6, follow the ingest procedure in the skill. Never send anything.
