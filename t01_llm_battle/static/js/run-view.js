// ── Run view ─────────────────────────────────────────────
function runView() {
  return {
    runId: null, run: null, polling: null, error: null,

    init(runId) {
      if (this.polling) { clearInterval(this.polling); this.polling = null; }
      this.runId = runId; this.run = null; this.error = null;
      this.startPolling();
    },

    async fetchStatus() {
      if (!this.runId) return;
      try {
        const resp = await fetch('/runs/' + this.runId + '/status');
        if (!resp.ok) throw new Error(await resp.text());
        this.run = await resp.json();
        if (this.run.status === 'complete' || this.run.status === 'error') {
          this.stopPolling();
          if (this.run.status === 'complete') {
            setTimeout(() => { location.hash = '#/results/' + this.runId; }, 500);
          }
        }
      } catch(e) { this.error = e.message; this.stopPolling(); }
    },

    startPolling() { this.fetchStatus(); this.polling = setInterval(() => this.fetchStatus(), 2000); },
    stopPolling() { if (this.polling) { clearInterval(this.polling); this.polling = null; } },

    sources() {
      if (!this.run || !this.run.fighter_results) return [];
      const seen = new Set();
      return this.run.fighter_results.filter(fr => {
        if (seen.has(fr.source_id)) return false; seen.add(fr.source_id); return true;
      }).map(fr => ({ source_id: fr.source_id, source_label: fr.source_label || fr.source_id }));
    },

    fighters() {
      if (!this.run || !this.run.fighter_results) return [];
      const seen = new Set();
      return this.run.fighter_results.filter(fr => {
        if (seen.has(fr.fighter_id)) return false; seen.add(fr.fighter_id); return true;
      }).map(fr => ({ fighter_id: fr.fighter_id, fighter_name: fr.fighter_name || fr.fighter_id }));
    },

    getCellResult(fighter_id, source_id) {
      if (!this.run || !this.run.fighter_results) return null;
      return this.run.fighter_results.find(fr => fr.fighter_id === fighter_id && fr.source_id === source_id) || null;
    }
  };
}
