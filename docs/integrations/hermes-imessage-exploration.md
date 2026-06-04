# Hermes iMessage Exploration

iMessage is an exploration target for Hermes as a read-only/status gateway into Dev-Flow. It is not a production authority path until Josh has manually reviewed the local dependencies, permissions, privacy boundaries, and approval flow.

Use `<repo-root>` for portable command examples. This checkout is referred to as `DevFlow` in docs and handoffs. `/Users/jewelbait/Desktop/DevFlow` is quarantined and forbidden for current work. Do not assume every checkout is named `DevFlow`.

Dev-Flow artifacts beat Hermes memory. Human approval controls mutation and promotion.

## Path A: BlueBubbles Gateway

BlueBubbles uses an always-on Mac as the Messages bridge. Hermes would talk to the gateway; Dev-Flow remains reachable only through supervisor-safe commands.

Prerequisites:

- an always-on Mac
- Messages.app signed in to the intended Apple ID
- BlueBubbles Server installed and configured
- gateway credentials stored outside Dev-Flow logs
- Hermes profile scoped to read-only Dev-Flow commands

Security and privacy concerns:

- BlueBubbles may require Full Disk Access to Messages data
- gateway credentials and message metadata must not be printed in Dev-Flow logs
- message content should be summarized minimally
- personal chat authority must not imply repo mutation authority

Read-only checks:

```bash
test -d /Applications/BlueBubbles.app
test -d "$HOME/Library/Application Support/bluebubbles-server"
command -v bluebubbles
PYTHONPATH=src .venv/bin/python -m devflow.cli hermes imessage-check --json
```

## Path B: macOS imsg / Messages.app Skill

The `imsg` path uses a macOS CLI or skill to read/send through Messages.app. This should start as a local experiment only.

Prerequisites:

- macOS
- Messages.app present and signed in
- `imsg` CLI installed and on `PATH`
- any needed Full Disk Access, Accessibility, or Automation permissions reviewed manually
- Hermes profile scoped to read-only Dev-Flow commands

Security and privacy concerns:

- Full Disk Access can expose message databases
- Accessibility or Automation permissions can broaden control of local apps
- message contents should not become Dev-Flow evidence unless Josh explicitly captures them
- Do not read chat.db
- Do not send a test message from the readiness check

Read-only checks:

```bash
sw_vers
test -d /System/Applications/Messages.app || test -d /Applications/Messages.app
command -v imsg
PYTHONPATH=src .venv/bin/python -m devflow.cli hermes imessage-check --json
```

## Recommended First Experiment

Start with read-only/status interaction only:

1. Run `devflow hermes imessage-check --json`.
2. Configure a Hermes Dev-Flow profile with the command allowlist.
3. Ask Hermes for a short status brief using `status --json` and `supervisor packet --json`.
4. Return the answer to iMessage manually before enabling any send automation.
5. Require explicit approval language before any mutation command is even proposed.

The first iMessage flow should never read raw messages, never dump logs, never send a test message, never run workers, never clean up tasks, never promote, and never push.

## Safe iMessage Interactions

- "Dev-Flow status"
- "What needs review?"
- "What is the next safe action?"
- "Prepare a Codex prompt"
- "Summarize blocked tasks"

Hermes should answer with short status by default and include only the exact command a human can run next.

## Forbidden iMessage Interactions

- "Push it"
- "Merge everything"
- "Delete old worktrees"
- "Let agents fix whatever they want"

Hermes should refuse or translate these into a safe status/approval request. iMessage instructions are not enough to promote, push, merge, delete, or spawn workers.

## Approval Language

For risky actions, Hermes should require wording like:

```text
I approve this exact Dev-Flow command after reviewing the cited readiness evidence:
<command>
```

Hermes should cite the evidence source, such as `supervisor packet --json`, `task review --json`, `task next-action --json`, or `task promote-preview <task-id>`.

## Readiness Command

Dev-Flow provides a read-only readiness probe:

```bash
PYTHONPATH=src .venv/bin/python -m devflow.cli hermes imessage-check --json
```

The command inspects platform/app/config/CLI presence only. It does not request Full Disk Access, does not access `chat.db`, does not read message contents, and does not send messages.
