// ── Results view ─────────────────────────────────────────
function resultsView() {
  return {
    runId: null, results: null, expanded: {}, error: null, loading: false,

    async load(runId) {
      this.runId = runId; this.results = null; this.error = null; this.expanded = {}; this.loading = true;
      try {
        const resp = await fetch('/runs/' + runId + '/results');
        if (!resp.ok) throw new Error(await resp.text());
        this.results = await resp.json();
      } catch(e) { this.error = e.message; }
      finally { this.loading = false; }
    },

    toggleExpand(key) { this.expanded[key] = !this.expanded[key]; },

    fighterSummary() {
      if (!this.results || !this.results.summary) return [];
      const map = {};
      for (const item of this.results.summary) {
        const name = item.fighter_name;
        if (!map[name]) map[name] = { fighter_name: name, scores: [], total_cost: 0, token_cost: 0, credit_cost: 0, total_latency_ms: 0, success_count: 0, failed_count: 0, pricing_unknown: false };
        if (item.score !== null && item.score !== undefined) map[name].scores.push(item.score);
        if (item.total_cost_usd === null && (item.total_input_tokens || item.total_output_tokens)) map[name].pricing_unknown = true;
        map[name].total_cost += item.total_cost_usd || 0;
        if (item.total_input_tokens || item.total_output_tokens) map[name].token_cost += item.total_cost_usd || 0;
        else if (item.total_cost_usd) map[name].credit_cost += item.total_cost_usd || 0;
        map[name].total_latency_ms += item.total_latency_ms || 0;
        if (item.status === 'complete') map[name].success_count += 1;
        else if (item.status === 'error') map[name].failed_count += 1;
      }
      return Object.values(map).map(f => ({
        ...f, avg_score: f.scores.length ? f.scores.reduce((a, b) => a + b, 0) / f.scores.length : null,
      })).sort((a, b) => (b.avg_score ?? -Infinity) - (a.avg_score ?? -Infinity));
    },

    sourceGroups() {
      if (!this.results || !this.results.summary) return [];
      const order = []; const map = {};
      for (const item of this.results.summary) {
        const label = item.source_label || item.source_id || 'Unknown';
        if (!map[label]) { map[label] = { label, fighters: [] }; order.push(label); }
        map[label].fighters.push(item);
      }
      return order.map(l => map[l]);
    },

    scoreColor(score) {
      if (score === null || score === undefined) return 'color:var(--mid);';
      if (score >= 8) return 'color:var(--success);';
      if (score >= 5) return 'color:#e67e22;';
      return 'color:var(--danger);';
    },

    renderMarkdown(text) {
      if (typeof marked !== 'undefined') {
        const raw = marked.parse ? marked.parse(text) : marked(text);
        return typeof DOMPurify !== 'undefined' ? DOMPurify.sanitize(raw) : raw;
      }
      return text.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    },

    downloadMarkdown() {
      if (!this.results) return;
      const summary = this.fighterSummary();
      const lines = ['# LLM Battle Results', '', '**Run ID:** ' + (this.results.run_id || this.runId)];
      if (this.results.battle_id) lines.push('**Battle ID:** ' + this.results.battle_id);
      lines.push('', '## Fighter Summary', '', '| Fighter | Avg Score | Total Cost USD | Token Cost | Credit Cost | Time | Success | Failed |', '|---------|-----------|---------------|-----------|-------------|------|---------|--------|');
      for (const f of summary) lines.push('| ' + f.fighter_name + ' | ' + (f.avg_score !== null ? f.avg_score.toFixed(2) : '—') + ' | ' + (f.pricing_unknown ? 'unknown' : '$' + f.total_cost.toFixed(4)) + ' | ' + (f.token_cost > 0 ? '$' + f.token_cost.toFixed(4) : '—') + ' | ' + (f.credit_cost > 0 ? '$' + f.credit_cost.toFixed(4) : '—') + ' | ' + (f.total_latency_ms > 0 ? (f.total_latency_ms / 1000).toFixed(1) + 's' : '—') + ' | ' + f.success_count + ' | ' + f.failed_count + ' |');
      lines.push('', '## Per-Source Breakdown', '');
      for (const source of this.sourceGroups()) {
        lines.push('### ' + source.label, '');
        for (const fighter of source.fighters) {
          const reasoningLine = fighter.reasoning ? '_' + fighter.reasoning + '_' : '';
          lines.push('**' + fighter.fighter_name + '** — Score: ' + (fighter.score !== null && fighter.score !== undefined ? fighter.score.toFixed(1) : 'N/A'));
          if (reasoningLine) lines.push('', reasoningLine);
          lines.push('', '```', fighter.final_output || '(no output)', '```', '');
        }
      }
      if (this.results.report_markdown) lines.push('## Judge Report', '', this.results.report_markdown, '');
      const blob = new Blob([lines.join('\n')], { type: 'text/markdown' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = 'battle-results-' + (this.runId || 'export') + '.md'; a.click();
      URL.revokeObjectURL(url);
    },

    reportCopied: false,
    copyReportMarkdown() {
      if (!this.results || !this.results.report_markdown) return;
      navigator.clipboard.writeText(this.results.report_markdown).then(() => {
        this.reportCopied = true;
        setTimeout(() => { this.reportCopied = false; }, 2000);
      });
    }
  };
}
