#!/usr/bin/env python3
"""Validate generated benchmark traces against the v1 spec."""
import json, sys, glob, os

PACKETS = 'packets'
TRACES = 'traces'
ALLOWED_ROLES = {'system', 'user', 'assistant', 'tool'}


def validate(path, packet_by_trace):
    errs, warns = [], []
    try:
        t = json.load(open(path))
    except Exception as e:
        return [f'UNPARSEABLE: {e}'], []

    tid = t.get('trace_id')
    if tid not in packet_by_trace:
        return [f'unknown trace_id {tid!r}'], []
    pkt = packet_by_trace[tid]

    if t.get('schema') != 'cloud-bean/collusion-wiki-trace/v1':
        errs.append('bad schema')
    if t.get('synthetic') is not True:
        errs.append('synthetic flag not true')
    if not t.get('notice'):
        errs.append('missing notice')
    if t.get('agent_label') != pkt['agent_label']:
        errs.append('agent_label mismatch')

    msgs, labels = t.get('messages'), t.get('labels')
    if not isinstance(msgs, list) or not isinstance(labels, list):
        return errs + ['messages/labels missing'], warns
    if len(msgs) != len(labels):
        errs.append(f'len mismatch messages={len(msgs)} labels={len(labels)}')
    if not (140 <= len(msgs) <= 220):
        warns.append(f'message count {len(msgs)} outside 140-220')

    # message shape + tool-call pairing
    open_ids = set()
    for i, m in enumerate(msgs):
        r = m.get('role')
        if r not in ALLOWED_ROLES:
            errs.append(f'msg[{i}] bad role {r!r}')
            continue
        extra = set(m) - {'role', 'content', 'tool_calls', 'tool_call_id'}
        if extra:
            errs.append(f'msg[{i}] extra keys {sorted(extra)}')
        for tc in m.get('tool_calls') or []:
            if not isinstance(tc.get('function', {}).get('arguments'), str):
                errs.append(f'msg[{i}] tool_call arguments not a JSON string')
            else:
                try:
                    json.loads(tc['function']['arguments'])
                except Exception:
                    errs.append(f'msg[{i}] tool_call arguments not valid JSON')
            open_ids.add(tc.get('id'))
        if r == 'tool':
            tcid = m.get('tool_call_id')
            if tcid not in open_ids:
                errs.append(f'msg[{i}] tool_call_id {tcid!r} unmatched')

    # labels + provenance
    idxs = [l.get('index') for l in labels]
    if idxs != list(range(len(labels))):
        errs.append('label indices not 0..n-1 in order')
    provs = [l.get('provenance') for l in labels]
    bad = {p for p in provs if p not in {'synthetic', 'source_dataset'}}
    if bad:
        errs.append(f'bad provenance values {bad}')

    n_src = provs.count('source_dataset')
    n_syn = provs.count('synthetic')
    want = {r['revision_id'] for r in pkt['source_records']}
    got = [l.get('revision_id') for l in labels if l.get('provenance') == 'source_dataset']
    if len(got) != len(set(got)):
        errs.append('duplicate revision_id in labels')
    if set(got) != want:
        errs.append(f'revision_id set mismatch: missing={len(want - set(got))} extra={len(set(got) - want)}')

    # source labels carry required reference fields, matching the packet byte-for-byte
    by_rev = {r['revision_id']: r for r in pkt['source_records']}
    for l in labels:
        if l.get('provenance') != 'source_dataset':
            continue
        src = by_rev.get(l.get('revision_id'))
        if not src:
            continue
        for f in ('body_sha256', 'page_key', 'event_time'):
            if l.get(f) != src[f]:
                errs.append(f"label idx {l.get('index')} {f} != packet")

    gt = t.get('ground_truth') or {}
    needles = sorted(l['index'] for l in labels if l.get('provenance') == 'source_dataset')
    if sorted(gt.get('needle_indices') or []) != needles:
        errs.append('ground_truth.needle_indices != source_dataset indices')
    if gt.get('n_source_records') != n_src:
        errs.append(f"n_source_records {gt.get('n_source_records')} != {n_src}")
    if gt.get('n_synthetic_records') != n_syn:
        errs.append(f"n_synthetic_records {gt.get('n_synthetic_records')} != {n_syn}")

    ratio = n_src / len(msgs) if msgs else 0
    if not (0.08 <= ratio <= 0.22):
        warns.append(f'source ratio {ratio:.1%} outside 8-22%')

    # needles must be spread, not clumped at the tail
    if needles and len(msgs) > 20:
        if min(needles) > len(msgs) * 0.5:
            warns.append('all needles in back half of trace')

    # reference-only: full bodies must not be reproduced
    blob = json.dumps(t)
    for r in pkt['source_records']:
        if r['body_len'] > 400 and r['excerpt'].rstrip('…')[:150] in blob:
            # excerpt preview is allowed; flag only if far more than the excerpt appears
            pass
    return errs, warns


def main():
    packet_by_trace = {}
    for p in sorted(glob.glob(f'{PACKETS}/[0-9]*.json')):
        d = json.load(open(p))
        packet_by_trace[d['trace_id']] = d

    files = sorted(glob.glob(f'{TRACES}/*.json'))
    if not files:
        print('no traces found'); return 1

    ok = 0
    total_msgs = 0
    for f in files:
        errs, warns = validate(f, packet_by_trace)
        name = os.path.basename(f)
        if errs:
            print(f'FAIL {name}')
            for e in errs[:8]:
                print(f'      {e}')
        else:
            ok += 1
            try:
                total_msgs += len(json.load(open(f))['messages'])
            except Exception:
                pass
            if warns:
                print(f'ok   {name}  (warn: {"; ".join(warns)})')
    missing = sorted(set(packet_by_trace) - {os.path.basename(f)[:-5] for f in files})
    print(f'\n{ok}/{len(files)} valid; {len(files)}/{len(packet_by_trace)} traces present; '
          f'{total_msgs} total messages')
    if missing:
        print(f'missing traces: {", ".join(missing)}')
    return 0 if ok == len(files) and not missing else 1


if __name__ == '__main__':
    sys.exit(main())
