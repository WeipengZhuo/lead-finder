---
description: Change a finished or partial run based on your feedback, and re-run only what changed.
argument-hint: "<run slug> [what to change]"
allowed-tools: Bash(python3:*), Read, Write, Edit, AskUserQuestion
---

Refine an earlier run. Arguments: `$ARGUMENTS` (a run slug, then the feedback). If no slug is given, list the folders in `<home>/runs/` and ask which one.

1. Look at where the run stands:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/lf.py" status <slug>
```

2. Read `<home>/runs/<slug>/brief.json` and `candidates.jsonl`. Turn the feedback into a change to the brief (more queries, different titles or cities, a smaller or larger size range, extra exclusions, a different count). Examples:
   - "skip associations" -> remove association queries and add a name or domain exclusion.
   - "more in Texas" -> add Texas queries, then re-run search.
   - "this contact is wrong" -> `set` a different contact on that row, clear `email=` and `email_check=`, then re-run `emails` and `verify` for that row.

3. If the change is more than a tweak, copy the brief to a new slug derived from the old one (for example `<slug>-r2`), so the first run stays intact. Otherwise edit the brief in place.

4. Check the budget. If new work will not fit, run `brief-check` and `estimate`, quote the added cost, and wait for "go". Never raise `budget_usd` without the user's agreement.

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/lf.py" brief-check <slug>
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/lf.py" estimate <slug>
```

5. Re-run only the affected stages from the method in the `lead-research` skill. The cache makes repeats free, so re-running `search` is safe. Then `screen`, `contacts`, `emails`, `verify` as needed, rewrite openers for changed rows, and `export`.

6. Report what changed, the new table, and the spend so far.

Tell the user about any exclusion you add. Never send anything.
