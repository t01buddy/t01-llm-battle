// ── News Sources ─────────────────────────────────────────
function newsSources() {
  return {
    sources: [],
    loading: false,
    showAdd: false,
    formError: null,
    form: { name: '', source_type: 'rss', priority: 5, max_items: 20, tags_input: '', fighter_affinity: '', config_raw: '{}' },

    resetForm() {
      this.form = { name: '', source_type: 'rss', priority: 5, max_items: 20, tags_input: '', fighter_affinity: '', config_raw: '{}' };
      this.formError = null;
    },

    async load() {
      this.loading = true;
      try {
        const resp = await fetch('/news-sources');
        this.sources = await resp.json();
      } finally {
        this.loading = false;
      }
    },

    async createSource() {
      this.formError = null;
      let config = {};
      try { config = JSON.parse(this.form.config_raw || '{}'); } catch(e) { this.formError = 'Invalid JSON in Config'; return; }
      const tags = this.form.tags_input.split(',').map(t => t.trim()).filter(Boolean);
      const body = {
        name: this.form.name,
        source_type: this.form.source_type,
        priority: this.form.priority,
        max_items: this.form.max_items,
        tags,
        fighter_affinity: this.form.fighter_affinity || null,
        config,
      };
      const resp = await fetch('/news-sources', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      if (resp.ok) {
        this.showAdd = false;
        this.resetForm();
        await this.load();
      } else {
        const err = await resp.json();
        this.formError = err.detail || 'Create failed';
      }
    },

    async toggleDisable(src) {
      const newStatus = src.status === 'disabled' ? 'active' : 'disabled';
      await fetch('/news-sources/' + src.id, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status: newStatus }) });
      await this.load();
    },

    async deleteSource(id) {
      if (!confirm('Delete this source?')) return;
      await fetch('/news-sources/' + id, { method: 'DELETE' });
      await this.load();
    },
  };
}
