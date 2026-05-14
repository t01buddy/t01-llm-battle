# t01-llm-battle showcases

These examples show public, user-facing ways to use `t01-llm-battle`. They are not benchmark claims; they are starting points you can recreate with your own inputs and rubric.

## 1. Pick the cheapest model that is good enough

**Question:** Can a small model handle this feature, or do we need a premium model?

**Setup:**

- Sources: 20 representative user messages
- Fighters: small model, mid-tier model, premium model
- Rubric: correctness, tone, missing details, hallucinations

**Decision:** Choose the cheapest fighter whose quality is acceptable on real examples.

## 2. Compare single-step vs multi-step pipelines

**Question:** Is a two-step pipeline worth the extra latency and cost?

**Setup:**

- Sources: messy input documents
- Fighter A: one model call that extracts final JSON
- Fighter B: first normalize the text, then extract final JSON
- Rubric: schema validity, missed fields, incorrect fields

**Decision:** Use the pipeline only if the quality gain is visible enough to justify the cost.

## 3. Keep a human baseline in the loop

**Question:** How far is the model from a careful human answer?

**Setup:**

- Sources: a small set of difficult cases
- Fighters: one or more model approaches plus a manual fighter
- Rubric: task-specific quality criteria

**Decision:** Use the human baseline to calibrate expectations, not to claim universal model superiority.

## 4. Share a decision report

After the run, copy the markdown summary into a design note or pull request. The useful artifact is not just the winning model; it is the record of inputs, rubric, tradeoffs, and why the choice was made.
