---
description: Show what Lead Finder has spent on your treg account, by run, today and all time.
argument-hint: "[run slug]"
allowed-tools: Bash(python3:*), Read
---

Show spend. Argument: `$ARGUMENTS` (an optional run slug).

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/lf.py" spend $ARGUMENTS
```

Then explain it in one or two plain sentences: what the run cost against its cap, what today and all time add up to, and the account balance if it printed one (otherwise say the balance is unavailable and can be seen at treg.to under Team, then Billing). Mention that searching and reading pages are free and that repeated calls are served from the cache at no cost.

Do not print the token. Do not show raw ledger lines unless the user asks.
