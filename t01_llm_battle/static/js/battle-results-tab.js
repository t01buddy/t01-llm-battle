// ── Runs Tab (battle detail) ──────────────────────────────
function runsTab() {
  return {
    loading: false, error: null, runs: [],

    async load(battleId) {
      if (!battleId) return;
      this.loading = true; this.error = null; this.runs = [];
      try {
        const resp = await fetch('/battles/' + battleId + '/runs');
        if (!resp.ok) throw new Error(await resp.text());
        const data = await resp.json();
        this.runs = Array.isArray(data) ? data : (data.runs || []);
      } catch(e) { this.error = e.message; }
      finally { this.loading = false; }
    },

    formatDuration(startedAt, finishedAt) {
      if (!startedAt || !finishedAt) return '—';
      const ms = new Date(finishedAt) - new Date(startedAt);
      if (isNaN(ms) || ms < 0) return '—';
      return ms < 1000 ? ms + 'ms' : (ms / 1000).toFixed(1) + 's';
    },

    formatStarted(startedAt) {
      if (!startedAt) return '—';
      try {
        return new Date(startedAt).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
      } catch(_) { return startedAt; }
    },

    statusColor(status) {
      if (status === 'complete') return 'color:var(--success,#16a34a);';
      if (status === 'error') return 'color:var(--danger,#c00);';
      if (status === 'running' || status === 'pending') return 'color:var(--gold,#d4a02a);';
      return 'color:var(--ba-text-mid,#6b7280);';
    }
  };
}
