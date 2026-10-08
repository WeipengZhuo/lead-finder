Licensed to Karen Louisa Gross (Communication That Sings). Not for redistribution.

# Lead Finder

Lead Finder turns "who do I want to reach?" into a short list of the right people, each with a verified work email, a line on why they fit, and a first note written in your voice.

It never sends anything. You read the list, edit the notes, and send them yourself.

## Commands

| Command | What it does |
|---|---|
| `/lead-finder:setup` | One-time: creates your lead folder, saves your treg token, runs a free connection test. |
| `/lead-finder:profile` | Reads your website and LinkedIn, asks a few questions, and writes your profile (offers, proof, voice, clients to leave out). |
| `/lead-finder:find` | Interviews you about who you want to reach, shows a cost estimate, and on your "go" runs the search and produces your lead files. |
| `/lead-finder:refine` | Takes your feedback on a run ("fewer associations, more corporate") and re-runs only what changed. Repeated work is cached and free. |
| `/lead-finder:draft` | Writes a first note for each lead you pick, 90 to 140 words, in your voice. Saved as a file. Never sent. |
| `/lead-finder:spend` | Shows what you have spent, per run and in total, and your treg balance when available. |

## What it costs

Lead Finder itself has no usage fee. The data comes from treg (treg.to) on your own account, and you pay treg for each call. Measured so far: about $0.01 to $0.03 per verified lead. Before any paid call, `/lead-finder:find` shows an estimate and asks for your go-ahead, and every run has a spend cap you set. A top-up of $10 to $20 covers many runs.

## What it never does

- Send email or messages, or log into your email, LinkedIn, or any messaging account.
- Spend past the cap you approved for a run.
- Keep phone numbers, home addresses, or personal email addresses. These are dropped before anything is saved.
- Guess an email address. An email is only listed as Verified after a check, and uncertain ones go in a separate Risky file.

## Privacy

- Your lead files, profile, and spend log live in the folder you chose. They are not uploaded anywhere by Lead Finder.
- Your treg token is stored in a settings file inside that folder, readable only by you, and is never printed or logged. Do not put that folder in a shared drive.
- Searches and page fetches go through treg and its data providers under your own account and their terms. Search terms and company domains are sent to them. Your profile and drafts are not.
- Run it in Cowork (Claude desktop app) or Claude Code, where the folder lives on your computer. A regular claude.ai chat wipes its files when the chat ends.
- Review each draft before you send. You are responsible for the messages you send, including meeting the rules in `SETUP_FOR_CLIENTS.md` (CAN-SPAM basics).

## Setup

Follow `SETUP_FOR_CLIENTS.md`. It is one page.

## Optional: treg as a connector

Lead Finder talks to treg directly over HTTP. If Claude's sandbox blocks it, `/lead-finder:setup` will say so; the fix is Settings, then Capabilities, then add `treg.to` to Additional allowed domains. If that is not possible, add treg as a custom connector with the URL only (`https://treg.to/mcp/`) and sign in to treg when asked. Lead Finder then runs in a slower mode where Claude makes each call through the connector. The file `.mcp.json.example` shows the same server for Claude Code users (agent token in a Bearer header). It is not active by default.
