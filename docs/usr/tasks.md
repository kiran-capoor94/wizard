# Tasks

A task is a unit of tracked work. Tasks have a name, status, priority, and a collection of notes. Wizard uses tasks to organise what your agent saves and to surface the right context when you start working on something.

## Statuses

| Status | What it means |
|---|---|
| `todo` | Not started yet — the default for new tasks |
| `in_progress` | Actively being worked on |
| `blocked` | Waiting on something external; excluded from most prioritisation |
| `done` | Completed |
| `archived` | Set aside; not actively tracked |

You can use natural aliases too — `open`, `pending`, and `wip` are also accepted and resolve to the right status.

## Priorities

Tasks have three priority levels: `low`, `medium` (the default), and `high`. Priority affects how tasks are ranked when you ask wizard what to work on.

## Saving notes to a task

Notes are the main way wizard tracks cognitive work on a task. Call `wizard:save_note` during a session with the task ID and the content you want to save. Notes have a type:

| Type | What to use it for |
|---|---|
| `investigation` | Findings — what you discovered, what you explored, what the code does |
| `decision` | Choices — what you decided and the reasoning behind it |
| `docs` | How things work — factual descriptions worth keeping |
| `learnings` | Surprises — things that weren't obvious or that corrected a wrong assumption |
| `failure` | Dead ends — what didn't work and why, so you don't go down the same path again |

Notes are the unit of cognitive work on a task. Status changes (marking a task `in_progress`, `done`) are administrative actions and don't count as cognitive activity.

## Staleness

A task becomes stale when no notes have been added recently. The staleness counter measures days since the last note, not days since the last status change. A task marked `in_progress` with no notes still accrues stale days.

Staleness is refreshed at every session start, so the numbers are always current when you look at your task list. Staleness affects how tasks are ranked when you ask `wizard:what_should_i_work_on`.

## What should I work on?

Call `wizard:what_should_i_work_on` to get a ranked list of tasks with AI-generated reasoning for each recommendation. Pass a `mode` to adjust the scoring:

| Mode | What it surfaces |
|---|---|
| `focus` | High-priority tasks you've touched recently — best for deep work |
| `quick-wins` | Low-investment tasks that can be closed quickly — best when you want to clear the queue |
| `unblock` | Tasks currently marked as blocked — best when you have time to clear dependencies |

You can also pass a `time_budget` (e.g. `"30m"`) to bias the results toward tasks that are already in progress.

## Linking tasks to external systems

Tasks can be linked to Jira issues or Notion pages via a `source_id` and `source_type`. When you create a task with a `source_id`, wizard deduplicates it — calling `create_task` with the same `source_id` returns the existing task instead of creating a duplicate. This makes it safe to call `create_task` every session for your Jira issues without accumulating duplicates.
