#!/usr/bin/env python3
"""Rehydrate referenced source bodies into traces, locally.

Traces ship reference-only: source turns carry revision_id + body_sha256 but not the recorded
text. This script reads the Collusion Wiki SQLite database and fills in the full bodies, verifying
each against its recorded hash. Output stays local and is not intended for redistribution.

Usage:
    python3 rehydrate.py --db data/collusion-wiki.db --traces traces --out traces-hydrated
    python3 rehydrate.py --db data/collusion-wiki.db --traces traces --verify-only
"""
import argparse, glob, hashlib, json, os, sqlite3, sys


def load_bodies(db, revision_ids):
    con = sqlite3.connect(f'file:{db}?mode=ro', uri=True)
    out = {}
    ids = list(revision_ids)
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        q = ','.join('?' * len(chunk))
        for rid, body, sha, enc in con.execute(
                f'select revision_id, body, body_sha256, body_encoding '
                f'from revisions where revision_id in ({q})', chunk):
            out[rid] = {'body': body, 'body_sha256': sha, 'body_encoding': enc}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--db', default='data/collusion-wiki.db')
    ap.add_argument('--traces', default='traces')
    ap.add_argument('--out', default='traces-hydrated')
    ap.add_argument('--verify-only', action='store_true')
    a = ap.parse_args()

    if not os.path.exists(a.db):
        sys.exit(f'database not found: {a.db}\n'
                 'Expand it first:  gzip -dc collusion-wiki.db.gz > data/collusion-wiki.db')

    files = sorted(glob.glob(os.path.join(a.traces, '*.json')))
    if not files:
        sys.exit(f'no traces in {a.traces}')

    wanted = set()
    traces = {}
    for f in files:
        t = json.load(open(f))
        traces[f] = t
        for l in t.get('labels', []):
            if l.get('provenance') == 'source_dataset' and l.get('revision_id'):
                wanted.add(l['revision_id'])

    bodies = load_bodies(a.db, wanted)
    missing = wanted - set(bodies)
    mismatched = []

    for rid, rec in bodies.items():
        # verify the stored body reproduces its recorded source-byte hash
        raw = rec['body'].encode(
            {'ascii': 'ascii', 'utf8': 'utf-8', 'latin1': 'latin-1'}[rec['body_encoding']],
            errors='strict')
        if hashlib.sha256(raw).hexdigest() != rec['body_sha256']:
            mismatched.append(rid)

    print(f'traces:      {len(files)}')
    print(f'referenced:  {len(wanted)} revisions')
    print(f'resolved:    {len(bodies)}')
    print(f'missing:     {len(missing)}')
    print(f'hash fail:   {len(mismatched)}')

    # cross-check each trace's recorded sha against the database
    ref_mismatch = 0
    for f, t in traces.items():
        for l in t.get('labels', []):
            if l.get('provenance') != 'source_dataset':
                continue
            db_rec = bodies.get(l.get('revision_id'))
            if db_rec and l.get('body_sha256') != db_rec['body_sha256']:
                ref_mismatch += 1
    print(f'ref sha bad: {ref_mismatch}')

    if missing or mismatched or ref_mismatch:
        sys.exit('verification failed')
    print('verification OK')

    if a.verify_only:
        return

    os.makedirs(a.out, exist_ok=True)
    for f, t in traces.items():
        for l in t.get('labels', []):
            if l.get('provenance') == 'source_dataset':
                rec = bodies.get(l.get('revision_id'))
                if rec:
                    l['body'] = rec['body']
                    l['body_encoding'] = rec['body_encoding']
        t['rehydrated'] = True
        t['redistribution_note'] = (
            'REHYDRATED LOCALLY — now contains full source bodies. Upstream export reports '
            "notice: 'Draft — do not share without permission.' Do not redistribute this file.")
        json.dump(t, open(os.path.join(a.out, os.path.basename(f)), 'w'), indent=1)
    print(f'wrote {len(traces)} hydrated traces to {a.out}/ (keep local)')


if __name__ == '__main__':
    main()
