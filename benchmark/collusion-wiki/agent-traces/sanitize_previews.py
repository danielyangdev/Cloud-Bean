#!/usr/bin/env python3
"""Cap preview text so no source record is ever reproduced in full or near-full.

Preview budget per record: min(120 chars, 40% of the real body). Short records therefore keep
only a fragment instead of their whole text.
"""
import json, glob, sqlite3

con = sqlite3.connect('file:data/collusion-wiki.db?mode=ro', uri=True)
bodylen = {rid: n for rid, n in con.execute('select revision_id, length(body) from revisions')}


def budget(rid):
    n = bodylen.get(rid, 0)
    return max(0, min(120, int(n * 0.4)))


def clip(val, cap):
    if not isinstance(val, str) or cap <= 0:
        return '', True
    s = ' '.join(val.split())
    if len(s) <= cap:
        return s, False
    return s[:cap].rstrip() + '…', True


def walk(obj, cap):
    """Truncate any preview/excerpt string field found anywhere in obj."""
    changed = False
    if isinstance(obj, dict):
        for k, v in list(obj.items()):
            if k in ('preview', 'excerpt', 'body_preview', 'body_excerpt'):
                new, did = clip(v, cap)
                if did:
                    obj[k] = new
                    changed = True
            else:
                changed |= walk(v, cap)
    elif isinstance(obj, list):
        for v in obj:
            changed |= walk(v, cap)
    return changed


total = files_changed = 0
for f in sorted(glob.glob('traces/*.json')):
    try:
        t = json.load(open(f))
    except Exception:
        continue
    # map message index -> revision_id via labels
    rid_at = {l['index']: l.get('revision_id') for l in t.get('labels', [])
              if l.get('provenance') == 'source_dataset'}
    changed = False
    for i, m in enumerate(t.get('messages', [])):
        rid = rid_at.get(i)
        cap = budget(rid) if rid else 80
        for tc in m.get('tool_calls') or []:
            a = tc.get('function', {}).get('arguments')
            if not isinstance(a, str):
                continue
            try:
                parsed = json.loads(a)
            except Exception:
                continue
            if walk(parsed, cap):
                tc['function']['arguments'] = json.dumps(parsed, ensure_ascii=False)
                changed = True
                total += 1
    if changed:
        json.dump(t, open(f, 'w'), indent=1)
        files_changed += 1

print(f'previews clipped: {total} across {files_changed} files')
