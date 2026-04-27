// ── Shared constants ─────────────────────────────────────
const DEFAULT_RUBRIC = `Score the following LLM output on a scale from 0 to 10.

**Criteria:**
- **Relevance** (0-2): Does the output directly address the input/task?
- **Accuracy** (0-3): Is the content factually correct and free of hallucinations?
- **Conciseness** (0-2): Is the output appropriately brief without omitting important details?
- **Helpfulness** (0-3): Would the output genuinely help someone accomplish their goal?

**Instructions:**
Return a JSON object with exactly these fields:
- \`score\`: integer 0-10
- \`reasoning\`: a brief explanation (2-4 sentences) justifying the score

Do not wrap the JSON in markdown fences.`;

const DEFAULT_MODELS = {
  openai: 'gpt-4o',
  anthropic: 'claude-sonnet-4-5',
  google: 'gemini-2.0-flash',
  groq: 'llama-3.3-70b-versatile',
  openrouter: 'openai/gpt-4o',
  ollama: 'llama3.2',
};
