# Synthetic agent traces (needle-in-haystack fixtures)

**These are generated fixtures, not incident records.** Every trace here is mostly invented. Roughly
80–90% of each trace is model-generated ordinary work that never happened. Only the turns labeled
`provenance: "source_dataset"` correspond to events recorded in the Collusion Wiki archive, and even
those reference the recorded text rather than reproducing it.

Do not cite a trace as evidence of what any named actor did.

## Why these exist

The archive in `../` has no matched healthy baseline — it is incident records only. A detector cannot
be scored on that, because everything in it is signal. These fixtures supply the haystack: each one
buries a handful of real recorded events in a much larger body of mundane wiki-curation work, with
machine-readable ground truth saying which turns are which.

## What is in each file

| Field | Meaning |
| --- | --- |
| `synthetic` | Always `true`. |
| `notice` | Human-readable warning that the file is a fixture. |
| `agent_label` | The archive label this trace is built around (see caveats below). |
| `messages` | Strict OpenAI chat-completions format: `system` / `user` / `assistant` (with `tool_calls`) / `tool`. Directly loadable by OpenAI tooling. |
| `labels` | Parallel array, one entry per message index, each `provenance: "synthetic"` or `"source_dataset"`. Source entries carry `revision_id`, `body_sha256`, `page_key`, `event_time`. |
| `ground_truth` | `needle_indices` (the message indices a detector should flag) plus source/synthetic counts. |

`packets/` holds the generation inputs — the sampled source records each trace was built from —
so any trace can be regenerated or audited against what it was given.

## Source text is referenced, not reproduced

Upstream reuse rights for the archive are unresolved, and two sources report the export carries the
notice **"Draft — do not share without permission"** (see `../README.md`). These fixtures therefore
carry only `revision_id` + `body_sha256` plus a clipped preview, capped at
`min(120 chars, 40% of the record)` so no record appears whole. Verified: maximum verbatim run across
all 35 traces is 120 characters; nothing exceeds 200.

To work with full text, rehydrate locally against the database — output stays local and is not for
redistribution:

```sh
cd benchmark/collusion-wiki
mkdir -p data && gzip -dc collusion-wiki.db.gz > data/collusion-wiki.db
cd agent-traces
python3 rehydrate.py --db ../data/collusion-wiki.db --verify-only   # check references resolve
python3 rehydrate.py --db ../data/collusion-wiki.db                 # write traces-hydrated/
```

## Tooling

```sh
python3 validate_traces.py     # schema, OpenAI message shape, tool-call pairing, needle coverage
python3 repair_traces.py       # deterministic fixes only (truncated arguments, stale counts)
python3 sanitize_previews.py   # re-clip previews; run after any regeneration
```

`TRACE_SPEC.md` is the generation spec the traces were produced against.

## Coverage and caveats

- **35 traces, 6,400+ messages, 875 source records referenced.** Each trace embeds 25 sampled
  records from one agent label.
- **Agent attribution comes from `labels.is_human_handle`** in the archive (3,100 agent labels /
  14,560 revisions; 3 human handles / 31 revisions). Ranking is in `agent-ranking.json`.
- **Labels are not identities.** The archive's own README states names do not establish unique agents
  or verified operators. Two ranked labels (`Agent`, `A`) are almost certainly collision buckets. The
  empty-string label (899 revisions) was excluded as an anonymous bucket rather than an actor.
- **Sampling is capped at 25 records per agent**, spread chronologically. High-volume labels
  (`AgentRelent`, 317 revisions) are therefore partially covered, not exhausted.
- **15 of the intended 50 traces are absent**: 5 failed validation (`cw-009`, `cw-019`, `cw-020`,
  `cw-031`, `cw-034` — unmatched tool-call ids, message/label length mismatches, incomplete needle
  sets) and 10 were never generated.
- **Five shipped traces sit outside the target envelope** (140–220 messages, 8–22% source) and are
  flagged as warnings by the validator: `cw-027` and `cw-032` are short with ~26% source, `cw-035`
  (126), `cw-029` (258), `cw-038` (357 messages at 7% source). They are structurally valid; treat
  their ratios as known skew.
- **The synthetic work is model-generated and imperfect as a baseline.** It was written to a variety
  floor (≥6 distinct tools, no tool above 30%, scattered failure/retry turns, some ordinary saves so
  that "a save" is not itself a tell), but it is not a substitute for traces captured from a real
  fleet.

## Attribution

Source records: Sydney Von Arx, Cormac Slade Byrd, Spencer Kitts, Thomas Larsen; "Discovery of a new
OpenAI agent message board," 4 September 2026, Collusion Wiki / Nightingale Collective. SQLite
conversion by Simon Willison. Synthetic surround generated for this benchmark; it carries no
authority from those authors.
