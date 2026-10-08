# Lead Finder: setup (about 15 minutes, once)

## 1. Claude

1. Claude Pro (or higher) and the Claude desktop app, signed in.
2. Settings, then Capabilities. Under "Allow network egress", add `treg.to` to Additional allowed domains and click Add.

## 2. treg (where the data comes from)

1. Go to treg.to and sign in with Google. New accounts get $1 of free credit.
2. Team, then Billing: add $10 to $20. A verified lead costs about 1 to 3 cents.
3. Team, then agent tokens: create a token named "lead-finder", allow all tools, and set the daily call limit to 1000. The limit counts calls, not dollars (a 10-lead search makes about 160). Copy the token and treat it like a password.

## 3. Install Lead Finder

In Claude: Customize, then Plugins, then Add, then Upload plugin. Choose the zip you were sent and click Upload. For an update, upload the new zip and click Replace.

If you were invited to the private GitHub repo instead: Add, then Add marketplace, enter `WeipengZhuo/lead-finder`, click Connect GitHub, install Lead Finder, and turn on Sync automatically.

## 4. First run (in Cowork)

Use Cowork in the desktop app. A regular chat forgets its files when it ends, so your profile and lists would be lost.

1. Open Cowork and pick a private folder for your lead files.
2. Run `/lead-finder:setup` and paste your treg token when asked. It runs a free test.
3. Run `/lead-finder:profile`. It reads your website and LinkedIn and asks a few questions so the notes sound like you.
4. Run `/lead-finder:find`. Answer the questions, check the cost estimate, and say "go".

You get `leads.csv` (verified emails), `risky.csv` (check before using) and `summary.md`.

## Before you send

Lead Finder never sends anything. When you email people in the US:

- Use your real name, a real reply address and an honest subject line.
- Include your business mailing address and an easy way to opt out. Honor opt-outs quickly.
- Write to each person and say why them. No bulk blasts.

## Help

- Setup says it cannot reach treg: check the `treg.to` setting in step 1, then start a new chat.
- "Daily call limit reached": it resets tomorrow, or raise the limit in treg under agent tokens.
- Anything else: run `/lead-finder:setup` again. Still stuck? Send a screenshot to the person who sent you this, with your token covered.
