# t01-llm-battle manual

`t01-llm-battle` is a local browser tool for comparing model and pipeline choices on your own inputs. It is for early project decisions: which model, prompt, or multi-step approach is good enough for the job?

## 1. Install and start

```bash
pipx install t01-llm-battle
t01-llm-battle serve
```

The command starts a local server and opens the browser. Your battles, keys, prompts, and results stay on your machine.

## 2. Create a battle

A battle is one comparison run. Give it a name that describes the decision you are trying to make, for example:

- `Summarize support tickets`
- `Extract invoice fields`
- `Rewrite docs for beginners`

Choose a judge model and edit the rubric so the score matches your task.

## 3. Add sources

Sources are the inputs every fighter will receive. Add them as:

- `.txt` or `.md` files, one input per file
- a `.csv` file, one input per row

Use real examples when possible. The tool is most useful when the inputs look like the work you actually need to ship.

## 4. Add fighters

A fighter is one approach you want to compare. It can be:

- a single model call
- a prompt variation
- a multi-step pipeline
- a manual baseline entered by a human

Examples:

- `Haiku single-step`
- `Sonnet single-step`
- `Cheap model draft + strong model edit`
- `Human baseline`

## 5. Run and inspect results

Start the run and inspect:

- final answer quality
- judge score and reasoning
- token usage
- estimated cost
- latency
- step-level outputs for pipeline fighters

Do not treat the judge as an oracle. Use the reasoning and raw outputs to sanity-check the score.

## 6. Export the decision

Use the generated markdown report to record what you tried, which fighter won, and why. The report is meant for sharing in issues, pull requests, design docs, or team notes.

## Privacy model

`t01-llm-battle` is local-first. It does not host your battles or publish your results. Provider API calls happen only when you configure a provider and run a battle.
