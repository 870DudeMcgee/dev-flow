# DEVFLOW_PHILOSOPHY.md

# Dev-Flow Engineering Philosophy

Dev-Flow is a local-first agentic operating system for software development.

It is not merely a coding agent, not a model wrapper, not a workflow ceremony, and not a dev-team roleplay system.

Its purpose is to let a human developer safely run, observe, coordinate, verify, and review AI coding workers across isolated local workspaces.

## Core Belief

Agents are replaceable. State is sacred. Visibility is mandatory. Isolation comes before autonomy. Verification belongs to Dev-Flow. Humans control promotion to main.

## What Dev-Flow Owns

Dev-Flow owns:

* task lifecycle,
* local state,
* workspace creation,
* worker boundaries,
* logs,
* questions,
* artifacts,
* verification evidence,
* CLI-visible state now and richer dashboard visibility later,
* merge-readiness reporting.

Agents may plan, code, test, review, debug, summarize, or design.

But Dev-Flow owns the control layer.

## Model Philosophy

Use frontier models for judgment.

Use Dev-Flow for control.

Use local models for bounded labor.

Use deterministic tools for truth.

Frontier models are useful as:

* architects,
* planners,
* UI designers,
* reviewers,
* debuggers,
* risk analysts,
* orchestrators.

Local models are useful for smaller bounded work:

* summarizing logs,
* classifying failures,
* making small edits,
* writing simple tests,
* filling templates,
* cleaning documentation,
* mechanical refactors.

Do not expect local models to act like senior engineers. They need small tasks, explicit context, limited scope, and clear verification.

## Critical Rule

The frontier model should not become the OS.

The model proposes.

Dev-Flow records.

Workers execute.

Dev-Flow verifies.

The human decides.

## Engineering Values

Dev-Flow values:

* clarity over cleverness,
* contracts over vibes,
* evidence over confidence,
* visible state over hidden memory,
* small vertical slices over impressive abstractions,
* boring correctness over futuristic complexity.

A change is good only if it makes the system more:

* observable,
* isolated,
* durable,
* recoverable,
* verifiable,
* or easier to understand.

## Prime Directive

Dev-Flow is not trying to make agents smarter first.

Dev-Flow is trying to make agent work observable, isolated, durable, recoverable, and reviewable.

A dumb worker with excellent state, logs, isolation, and verification is more valuable than a smart worker operating in chaos.

## Build Philosophy

Build the smallest durable system that makes the next step obvious.

Do not invent future architecture unless the current milestone demands it.

Prefer one working vertical slice over five impressive abstractions.

Every command should leave enough plain-text evidence that another human or agent can understand what happened after a restart.

When uncertain, reduce scope.

When stuck, expose state.

When tempted to be clever, make it boring.

## The Mantra

Make it visible.

Make it small.

Make it safe.

Make it repeatable.

Make it verifiable.

Then make it smart.

Intelligence without structure is just faster confusion.
