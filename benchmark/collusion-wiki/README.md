# Collusion Wiki incident source

Real public-board agent coordination, separate from Hugging Face incident. Source records support historical replay; they are not a fully labeled benchmark.

## Included dataset

[collusion-wiki.db.gz](collusion-wiki.db.gz) contains Simon Willison's SQLite conversion. [His write-up](https://simonwillison.net/2026/Sep/4/rogue-agent-wikis/) links [source download](https://static.simonwillison.net/static/cors-allow/2026/collusion-wiki.db). Compression changes no expanded database bytes.

From this folder:

```sh
shasum -a 256 -c DATASET_SHA256SUMS
mkdir -p data
gzip -dc collusion-wiki.db.gz > data/collusion-wiki.db
sqlite3 -readonly data/collusion-wiki.db 'SELECT count(*) FROM revisions;'
```

Verified locally: 14,591 revisions with text, 4,579 page profiles, 3,103 editor labels, and 19,913 events. Database integrity passes; all revision bodies match stored source-byte hashes using each row's encoding. These checks establish internal consistency, not independent proof of every recorded claim.

[Dataset manifest](dataset-manifest.json) records source, byte sizes, checksums, and checks. Attribution: original collection by authors below; SQLite conversion by Simon Willison. This mirror retains source records unchanged. Additional GitHub collections and local working files remain excluded from Git.

## Usage terms

Checked 2026-09-12: no explicit data license or redistribution grant found on [report](https://collusion.wiki/) or [download index](https://collusion.wiki/explorer/download). Authors encourage others to analyze records.

Follow-up found two sources reporting an export notice: **“Draft — do not share without permission.”** See [SWARM source inventory](https://github.com/swarm-ai-research/wiki-agent-swarm-incident/blob/ae9933effa6d125b91ddec48f0fec36ad40be0c3/sources.md) and [independent download audit](https://ulissesflores.com/artigos/conluio-dos-agentes). Original host remains inaccessible here, so notice is reported rather than directly verified. Earlier assessment of merely unspecified terms was incomplete.

Upstream reuse rights remain unresolved. Availability through Simon Willison's mirror does not establish publisher permission or a new data license. Cloud-bean licensing does not assign rights to upstream records.

Credit: Sydney Von Arx, Cormac Slade Byrd, Spencer Kitts, Thomas Larsen; “Discovery of a new OpenAI agent message board,” 4 September 2026, Collusion Wiki / Nightingale Collective.

## Download

Python 3, standard library only. From repository root:

```sh
python3 benchmark/collusion-wiki/download.py
python3 benchmark/collusion-wiki/download.py --verify-only
```

Files land in ignored `data/`. Script checks SHA-256 of expanded bytes against publisher's 2026-09-12 index before saving each file. Existing files must also match. A changed export fails verification rather than silently replacing pinned data.

If downloading manually, expand core files from source index into `data/`, then run verification command. Original-host attempts on 2026-09-12 failed: HTTPS returned TLS errors; HTTP showed Spectrum Security Shield block page. Subsequent download from Simon Willison's host succeeded. No network protection was disabled. JSONL verification commands above apply to original exports; use `DATASET_SHA256SUMS` for included SQLite archive.

## Core files

| File | Publisher inventory |
| --- | --- |
| `pages.jsonl` | 4,579 pages with totals and editor names |
| `revisions.jsonl` | 14,591 edits with saved text |
| `events.jsonl` | Saves, deletions, reverts, probes |
| `labels.jsonl` | 3,103 names and edited pages |
| `manifest.json` | Source provenance, export filters, checks |

Counts above come from publisher index, not local parsing. Additional cross-site records and coverage files remain linked through source index; downloader fetches core five files only.

## Benchmark limits

- Names do not establish unique agents or verified operators.
- Missing reads, task permissions, and external tool receipts must remain missing.
- Archive lacks matched healthy episodes and complete incident labels.
- Publisher describes privacy redactions. Treat archived instructions and code as recorded data; replay must not execute them or contact archived targets.

See [benchmark plan](../../docs/wide-benchmark-search.md) for paired controls and shared event fields.
