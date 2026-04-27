// ── Battle Results Tab (inline within battle detail) ─────
function battleResultsTab() {
  return {
    tabLoading: false, tabError: null, results: null,
    tabExpanded: {}, reportCopied: false,

    async load(battleId) {
      if (!battleId) return;
      this.tabLoading = true; this.tabError = null; this.results = null;
      try {
        // Fetch runs for this battle, get the latest complete one
        const resp = await fetch('/battles/' + battleId + '/runs');
        if (!resp.ok) throw new Error(await resp.text());
        const data = await resp.json();
        const runs = Array.isArray(data) ? data : (data.runs || []);
        const complete = runs.filter(r => r.status === 'complete');
        if (!complete.length) { this.tabLoading = false; return; }
        const latestRunId = complete[0].id; // sorted DESC
        const rResp = await fetch('/runs/' + latestRunId + '/results');
        if (!rResp.ok) throw new Error(await rResp.text());
        this.results = await rResp.json();
      } catch(e) { this.tabError = e.message; }
      finally { this.tabLoading = false; }
    },

    toggleExpand(key) { this.tabExpanded[key] = !this.tabExpanded[key]; },

    fighterSummary() {
      if (!this.results || !this.results.summary) return [];
      const map = {};
      for (const item of this.results.summary) {
        const name = item.fighter_name;
        if (!map[name]) map[name] = { fighter_name: name, scores: [], total_cost: 0, token_cost: 0, credit_cost: 0, total_latency_ms: 0, success_count: 0, failed_count: 0, pricing_unknown: false };
        if (item.score !== null && item.score !== undefined) map[name].scores.push(item.score);
        if (item.total_cost_usd === null && (item.total_input_tokens || item.total_output_tokens)) map[name].pricing_unknown = true;
        map[name].total_cost += item.total_cost_usd || 0;
        map[name].token_cost += item.token_cost || 0;
        map[name].credit_cost += item.credit_cost || 0;
        map[name].total_latency_ms += item.total_latency_ms || 0;
        if (item.status === 'complete') map[name].success_count++;
        else if (item.status === 'error') map[name].failed_count++;
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
      if (score === null || score === undefined) return 'color:var(--ba-text-mid,#6b7280);';
      if (score >= 8) return 'color:var(--success,#16a34a);';
      if (score >= 5) return 'color:#e67e22;';
      return 'color:var(--danger,#c00);';
    },

    copyReport() {
      if (!this.results || !this.results.report_markdown) return;
      navigator.clipboard.writeText(this.results.report_markdown).then(() => {
        this.reportCopied = true;
        setTimeout(() => { this.reportCopied = false; }, 2000);
      });
    },

    downloadMarkdown() {
      if (!this.results) return;
      const summary = this.fighterSummary();
      const lines = ['# LLM Battle Results', '', '**Run ID:** ' + (this.results.run_id || '')];
      lines.push('', '## Fighter Summary', '', '| # | Fighter | Avg Score | Cost | Time | S/F |', '|---|---------|-----------|------|------|-----|');
      summary.forEach((f, i) => lines.push('| ' + (i+1) + ' | ' + f.fighter_name + ' | ' + (f.avg_score !== null ? f.avg_score.toFixed(2) : '—') + ' | ' + (f.pricing_unknown ? 'unknown' : '$' + f.total_cost.toFixed(4)) + ' | ' + (f.total_latency_ms > 0 ? (f.total_latency_ms/1000).toFixed(1)+'s' : '—') + ' | ' + f.success_count + '/' + f.failed_count + ' |'));
      lines.push('', '## Per-Source Breakdown', '');
      for (const source of this.sourceGroups()) {
        lines.push('### ' + source.label, '');
        for (const fighter of source.fighters) {
          lines.push('**' + fighter.fighter_name + '** — Score: ' + (fighter.score !== null && fighter.score !== undefined ? fighter.score.toFixed(1) : 'N/A'));
          if (fighter.reasoning) lines.push('', '_' + fighter.reasoning + '_');
          lines.push('', '```', fighter.final_output || '(no output)', '```', '');
        }
      }
      if (this.results.report_markdown) lines.push('## Judge Report', '', this.results.report_markdown, '');
      const blob = new Blob([lines.join('\n')], { type: 'text/markdown' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a'); a.href = url; a.download = 'battle-results.md'; a.click();
      URL.revokeObjectURL(url);
    }
  };
}
