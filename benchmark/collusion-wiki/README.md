# Collusion Wiki incident source

Real public-board agent coordination, separate from Hugging Face incident. Source records support historical replay; they are not a fully labeled benchmark.

## Usage terms

Checked 2026-09-12: no explicit data license or redistribution grant found on [report](https://collusion.wiki/) or [download index](https://collusion.wiki/explorer/download). Authors encourage others to analyze records. That invitation does not specify commercial reuse, redistribution, or training terms. License status remains unspecified, not prohibited or confirmed open.

Raw records are excluded from Git. This folder publishes download tooling, source links, and publisher checksums only. Obtain explicit reuse terms before mirroring raw corpus publicly. Cloud-bean licensing does not assign rights to upstream records.

Credit: Sydney Von Arx, Cormac Slade Byrd, Spencer Kitts, Thomas Larsen; “Discovery of a new OpenAI agent message board,” 4 September 2026, Collusion Wiki / Nightingale Collective.

## Download

Python 3, standard library only. From repository root:

```sh
python3 benchmark/collusion-wiki/download.py
python3 benchmark/collusion-wiki/download.py --verify-only
```

Files land in ignored `data/`. Script checks SHA-256 of expanded bytes against publisher's 2026-09-12 index before saving each file. Existing files must also match. A changed export fails verification rather than silently replacing pinned data.

If downloading manually, expand core files from source index into `data/`, then run verification command. Local download attempt on 2026-09-12 failed: HTTPS returned TLS errors; HTTP showed Spectrum Security Shield block page. No raw archive was fetched in that attempt.

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
