# Cloud-Bean: Fleet Signal Specifications

Updated: 2026-09-13.
Status: Technical specification guiding Signal Worker implementation.

## 1. Overview of Fleet Signals

Fleet signals are cheap, rolling deterministic algorithms executed without LLM calls. They process incoming `FleetEvent` streams over sliding time windows (default: 30 minutes, step: 5 minutes) and flag **Candidate Groups** for bounded evidence assembly.

```text
Incoming Events ──► Sliding Window Buffer ──► Signal Evaluators ──► Candidate Group
                                             ├── 1. Emerging Hubs
                                             ├── 2. Conflicting Writes
                                             ├── 3. Shared Artifact Hashes
                                             └── 4. Collective Overload
```

---

## 2. Signal 1: Emerging Hubs / Destination Concentration

### Objective
Detect when multiple independent tasks or agents suddenly converge on a single shared resource (e.g. wiki page, file, server endpoint) that previously had low fan-in.

### Algorithm
1. Track rolling set of distinct `actor_id`s interacting with each `target` resource over window $W$.
2. Calculate the actor count $N_{actors}(R)$ and event count $N_{events}(R)$ for resource $R$.
3. Check baseline historical distinct actor count $B(R)$ (default: 1).
4. **Trigger Condition**:
   - $N_{actors}(R) \ge 3$ AND
   - $N_{actors}(R) \ge 2 \times B(R)$ AND
   - Interaction rate exceeds $\theta_{rate} = 5$ events per 10 minutes.

### Candidate Output
- `trigger_signal`: `"emerging_hub"`
- `target_resources`: `[R]`
- `actors`: all distinct actors on $R$ during $W$.

---

## 3. Signal 2: Conflicting Writes & Reversions

### Objective
Identify rapid overwrite battles, deletion-recreation loops, or edits alternating between distinct workers on the same resource.

### Algorithm
1. Maintain chronological list of `resource_write` and `resource_delete` events per resource $R$.
2. Detect **Alternating Actor Sequences**:
   - For consecutive writes $e_{i}, e_{i+1}$ to $R$:
     - If $actor(e_i) \ne actor(e_{i+1})$ and $|timestamp(e_{i+1}) - timestamp(e_i)| < \Delta t_{rapid} = 120\text{s}$.
3. Detect **Reversions / Deletions**:
   - Count deletions or reverts followed by edits within 300s.
4. **Trigger Condition**:
   - Alternating rapid edits $\ge 3$ within window $W$, OR
   - Deletions followed by recreation by a different actor $\ge 2$.

### Candidate Output
- `trigger_signal`: `"conflicting_writes"`
- `metrics.rapid_overwrites`: count of alternating edits.

---

## 4. Signal 3: Shared Artifact / Payload Hashing

### Objective
Detect evaluation cheating or cross-task data leakage where identical code blocks, prompt injection tokens, or serialized outputs appear across distinct tasks.

### Algorithm
1. For each `resource_write` or `message_post`, compute payload SHA-256 hash $H = \text{sha256}(payload.body)$.
2. Ignore trivial or empty payloads ($len(body) < 32$ chars or common boilerplate).
3. Record map: $H \mapsto \{(actor_i, task_i, timestamp_i)\}$.
4. **Trigger Condition**:
   - For any hash $H$:
     - Count of distinct tasks $|\{task_i\}| \ge 2$, OR
     - Count of distinct actors $|\{actor_i\}| \ge 2$ where tasks are declared isolated.

### Candidate Output
- `trigger_signal`: `"shared_artifact_reuse"`
- `metrics.shared_artifact_matches`: matching hash count.

---

## 5. Signal 4: Collective Resource Overload

### Objective
Detect coordinated denial-of-service, runaway looping, or queue stuffing where request rates spike across agents while successful output drops.

### Algorithm
1. Aggregate total events across fleet in window $W$.
2. Calculate ratio:
   $$R_{fail} = \frac{\text{Count of failed actions or retries}}{\text{Total requested operations}}$$
3. **Trigger Condition**:
   - Total request rate exceeds $2\times$ moving average, AND
   - $R_{fail} > 0.40$ (40% failure/conflict rate).

### Candidate Output
- `trigger_signal`: `"collective_overload"`

---

## 6. Audit Sampling Pipeline

To benchmark selection recall and detect "blind spots", the selector automatically tags a pseudo-random 10% sample of all interaction windows where $N_{actors} \ge 2$ that did NOT trigger any signal:

$$\text{hash}(group\_id + \text{"audit\_seed\_v1"}) \pmod{10} == 0$$

- Marked with `is_audit_sample = True`.
- Forwarded to Luna Judge using the reserved 10% audit budget.
