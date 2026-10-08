---
description: First-time setup for Lead Finder. Creates your working folder and connects your treg account.
argument-hint: "[none]"
allowed-tools: Bash(python3:*), Bash(printf:*), Read
---

Set up Lead Finder for this user. Keep it short and friendly. Follow the method in the `lead-research` skill for anything not covered here.

## Steps

1. Create the working folder (safe to re-run):

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/lf.py" init
```

Tell the user where the folder is (the command prints it).

2. Check whether a token is already set:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/lf.py" doctor
```

If doctor already reports a token and the free live call is OK, skip to step 5.

If doctor's `home:` line is under `/home/claude`, this is a regular claude.ai chat. Its workspace is wiped when the chat ends, so the folder, token, profile and lists will not carry over to a new chat. Say so in one sentence and recommend Cowork in the Claude desktop app (or Claude Code), where the folder lives on the user's computer. If they continue here, remind them at the end of each run to download `leads.csv`, `risky.csv` and `profile.md`.

3. Explain how to get a treg token. Lead Finder uses treg (https://treg.to), a pay-per-call data service, on the user's own account. Typical cost is a few cents per search run.
   - Open treg.to and sign in with Google.
   - Add a balance under Team, then Billing. $10 to $20 covers many runs.
   - Create an agent token, allow all tools, set its daily call limit to 1000, and copy it. Or, from a terminal with the treg CLI: `treg org agent-new lead-finder --cap 1000 --all-tools --local-run off`. The limit counts calls per day, not dollars: a 10-lead search makes about 160 calls, so 1000 covers roughly 60 leads a day. Spending is limited by the treg balance and by the budget the user approves for each run.

4. Ask the user to paste the token. When they do:
   - Pipe it into the config command so it is never a command-line argument or echoed back by you:

```
printf '%s' 'PASTED_TOKEN' | python3 "${CLAUDE_PLUGIN_ROOT}/scripts/lf.py" config --token-stdin
```

   - Replace `PASTED_TOKEN` with the pasted value. Tell the user up front that the token will be visible in this tool call. Never repeat the token in your reply, in a summary, or in any file other than through this command.
   - In Claude Code, a more private option is for the user to export the token as an environment variable in their terminal and have you run `... config --token-env VAR_NAME` with that variable's name.
   - Tell the user the token is stored only in `config.json` in their folder, readable only by them, and that a pasted token stays in this chat history, so a capped token is wise.

5. Test the connection:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/lf.py" doctor
```

   - Exit 0: say it works, and report the transport and that the free test call was OK.
   - Exit 3 or a FAIL line: the sandbox cannot reach treg.to. In claude.ai (web, desktop chat or Cowork) the fix is one setting: Settings, then Capabilities, then under "Allow network egress" add `treg.to` to Additional allowed domains. Then start a new chat and run `/lead-finder:setup` again.
   - Only if that setting is not available: Lead Finder can run in a slower "ingest" mode where Claude makes each treg call itself through a connector. In claude.ai the user adds treg as a custom connector with the URL only (`https://treg.to/mcp/`); the form has no header field, and treg asks the user to sign in, so no token is needed. In Claude Code, the plugin ships a `.mcp.json.example` file (agent token in a Bearer header); renaming it to `.mcp.json` does the same.
   - Exit 7: the token hit its daily call limit. Say it resets tomorrow, or raise the limit at treg.to under Team, then agent tokens.
   - After the connector is added, switch modes. The stored token is kept, so no re-paste is needed:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/lf.py" config --transport ingest
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/lf.py" doctor
```

6. Next step: run `/lead-finder:profile` so the notes sound like the user and clients are excluded.

Never print the token. Never send anything anywhere except through `lf.py`.
