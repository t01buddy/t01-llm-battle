// ── Sidebar data ─────────────────────────────────────────
function sidebarData() {
  return {
    battles: [],
    loading: false,
    providerInfoList: [],

    async load() {
      this.loading = true;
      try {
        const [battlesResp, providersResp] = await Promise.all([
          fetch('/battles'),
          fetch('/providers'),
        ]);
        if (!battlesResp.ok) throw new Error(await battlesResp.text());
        const data = await battlesResp.json();
        this.battles = (Array.isArray(data) ? data : [])
          .filter(b => b && b.id)
          .sort((a, b) => (b.created_at > a.created_at ? 1 : -1));
        if (providersResp.ok) {
          this.providerInfoList = await providersResp.json();
        }
      } catch(_) {}
      finally { this.loading = false; }
    },

    async toggleProvider(name, enabled) {
      // Optimistic update
      const p = this.providerInfoList.find(p => p.name === name);
      if (p) p.enabled = enabled;
      try {
        const resp = await fetch('/providers/' + name, {
          method: 'PATCH',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ enabled })
        });
        if (!resp.ok) throw new Error(await resp.text());
        window.dispatchEvent(new CustomEvent('provider-updated'));
      } catch(e) {
        // Revert on error
        if (p) p.enabled = !enabled;
      }
    },

    async newBattle() {
      const now = new Date();
      const pad = n => String(n).padStart(2, '0');
      const name = `Battle ${now.getFullYear()}-${pad(now.getMonth()+1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}`;
      try {
        const resp = await fetch('/battles', {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ name, judge_provider: null, judge_model: null, judge_rubric: null })
        });
        if (!resp.ok) throw new Error(await resp.text());
        const battle = await resp.json();
        const f1 = await (await fetch(`/battles/${battle.id}/fighters`, {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ name: 'Fighter 1', is_manual: false, position: 0 })
        })).json();
        await fetch(`/battles/${battle.id}/fighters/${f1.id}/steps`, {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ position: 1, provider: 'openai', model_id: 'gpt-4o', provider_config: '{}' })
        });
        const f2 = await (await fetch(`/battles/${battle.id}/fighters`, {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ name: 'Fighter 2', is_manual: false, position: 1 })
        })).json();
        await fetch(`/battles/${battle.id}/fighters/${f2.id}/steps`, {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ position: 1, provider: 'anthropic', model_id: 'claude-sonnet-4-5', provider_config: '{}' })
        });
        window.dispatchEvent(new CustomEvent('battle-created'));
        window.location.hash = '/battles/' + battle.id;
      } catch(e) { alert('Could not create battle: ' + e.message); }
    },

    async deleteBattle(id) {
      if (!confirm('Delete this battle?')) return;
      try {
        const resp = await fetch('/battles/' + id, { method: 'DELETE' });
        if (!resp.ok) throw new Error(await resp.text());
        // Optimistically remove from sidebar immediately
        this.battles = this.battles.filter(b => b.id !== id);
        const m = window.location.hash.match(/^#\/battles\/([^\/]+)$/);
        const wasCurrent = m && m[1] === id;
        window.dispatchEvent(new CustomEvent('battle-deleted'));
        if (wasCurrent) {
          if (this.battles.length > 0) {
            window.location.hash = '/battles/' + this.battles[0].id;
          } else {
            window.location.hash = '/battles';
          }
        }
      } catch(e) { alert('Delete failed: ' + e.message); }
    }
  };
}
