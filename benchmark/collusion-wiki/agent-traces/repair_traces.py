#!/usr/bin/env python3
"""Deterministically repair mechanical defects in generated traces.

Fixes only things with a single unambiguous correct answer:
  1. tool_call `arguments` truncated mid-object (append missing closing braces/brackets)
  2. ground_truth counts that disagree with the labels array
  3. ground_truth.needle_indices that disagree with the labels array

Anything else is left alone and reported, so it can be regenerated instead of guessed at.
"""
import glob, json, os, sys


def try_close(s):
    """Append missing closers to a truncated JSON object, if that makes it parse."""
    try:
        json.loads(s)
        return s, False
    except Exception:
        pass
    stack = []
    in_str = False
    esc = False
    for ch in s:
        if esc:
            esc = False
            continue
        if ch == '\\':
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch in '{[':
            stack.append('}' if ch == '{' else ']')
        elif ch in '}]' and stack:
            stack.pop()
    for cand in (s + ('"' if in_str else '') + ''.join(reversed(stack)),
                 s + ''.join(reversed(stack))):
        try:
            json.loads(cand)
            return cand, True
        except Exception:
            continue
    return s, False


def main():
    files = sorted(glob.glob('traces/*.json'))
    if not files:
        print('no traces'); return 1
    fixed_args = fixed_counts = unrepairable = 0
    bad_files = []
    for f in files:
        try:
            t = json.load(open(f))
        except Exception as e:
            print(f'UNPARSEABLE {os.path.basename(f)}: {e}')
            bad_files.append(f); unrepairable += 1
            continue
        changed = False
        for m in t.get('messages', []):
            for tc in m.get('tool_calls') or []:
                a = tc.get('function', {}).get('arguments')
                if not isinstance(a, str):
                    continue
                new, did = try_close(a)
                if did:
                    tc['function']['arguments'] = new
                    fixed_args += 1
                    changed = True
                else:
                    try:
                        json.loads(a)
                    except Exception:
                        unrepairable += 1
                        if f not in bad_files:
                            bad_files.append(f)
        labels = t.get('labels') or []
        if labels:
            provs = [l.get('provenance') for l in labels]
            gt = t.setdefault('ground_truth', {})
            needles = sorted(l['index'] for l in labels
                             if l.get('provenance') == 'source_dataset')
            want = {'needle_indices': needles,
                    'n_source_records': provs.count('source_dataset'),
                    'n_synthetic_records': provs.count('synthetic')}
            for k, v in want.items():
                if gt.get(k) != v:
                    gt[k] = v
                    fixed_counts += 1
                    changed = True
        if changed:
            json.dump(t, open(f, 'w'), indent=1)

    print(f'traces:            {len(files)}')
    print(f'arguments closed:  {fixed_args}')
    print(f'count fields set:  {fixed_counts}')
    print(f'unrepairable:      {unrepairable}')
    if bad_files:
        print('needs regeneration: ' + ', '.join(os.path.basename(b) for b in bad_files))
    return 0


if __name__ == '__main__':
    sys.exit(main())
