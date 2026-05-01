// ── News Boards ────────────────────────────────────────────
function newsBoards() {
  return {
    boards: [],
    loading: false,
    showCreate: false,
    formError: null,
    form: { name: '', description: '' },

    async init() {
      await this.load();
    },

    async load() {
      this.loading = true;
      try {
        const resp = await fetch('/boards');
        this.boards = await resp.json();
      } finally {
        this.loading = false;
      }
    },

    async createBoard() {
      this.formError = null;
      if (!this.form.name.trim()) { this.formError = 'Name is required'; return; }
      const resp = await fetch('/boards', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: this.form.name.trim(), description: this.form.description.trim() || null }),
      });
      if (resp.ok) {
        this.showCreate = false;
        this.form = { name: '', description: '' };
        await this.load();
      } else {
        const err = await resp.json();
        this.formError = err.detail || 'Create failed';
      }
    },
  };
}
