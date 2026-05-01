// ── News Fighters ─────────────────────────────────────────
function newsFighters() {
  return {
    fighters: [],
    loading: false,

    async load() {
      this.loading = true;
      try {
        const resp = await fetch('/news-fighters');
        this.fighters = await resp.json();
      } finally {
        this.loading = false;
      }
    },

    async deleteFighter(id) {
      if (!confirm('Delete this fighter?')) return;
      await fetch('/news-fighters/' + id, { method: 'DELETE' });
      await this.load();
    },
  };
}
