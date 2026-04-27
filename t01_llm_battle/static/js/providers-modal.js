// ── Providers Modal ───────────────────────────────────────
function providersModal() {
  return {
    open: false,
    keys: [], providerInfoList: [], loading: false, error: null,
    inputs: {}, displayNames: {}, baseUrls: {}, saved: {}, saveErrors: {},
    pricingRefreshing: false, pricingCacheLabel: '',
    expandedProvider: null,

    init() {
      window.addEventListener('open-providers-modal', () => { this.open = true; this.load(); });
      window.addEventListener('keydown', (e) => { if (e.key === 'Escape') this.open = false; });
    },

    async load() {
      this.loading = true; this.error = null;
      try {
        const [keysResp, infoResp, pricingResp] = await Promise.all([
          fetch('/keys'), fetch('/providers'), fetch('/providers/pricing')
        ]);
        if (!keysResp.ok) throw new Error(await keysResp.text());
        this.keys = await keysResp.json();
        if (pricingResp.ok) {
          const pc = await pricingResp.json();
          this.pricingCacheLabel = pc ? `Updated ${pc.age_days}d ago` : 'Using bundled defaults';
        }
        if (infoResp.ok) this.providerInfoList = await infoResp.json();
        this.keys.forEach(k => {
          if (this.inputs[k.provider] === undefined) this.inputs[k.provider] = '';
          if (this.displayNames[k.provider] === undefined) this.displayNames[k.provider] = '';
          if (this.baseUrls[k.provider] === undefined) this.baseUrls[k.provider] = '';
        });
      } catch(e) { this.error = e.message; }
      finally { this.loading = false; }
    },

    getProviderType(provider) {
      const info = this.providerInfoList.find(p => p.name === provider);
      return info ? info.provider_type : 'llm';
    },

    llmKeys() { return this.keys.filter(k => this.getProviderType(k.provider) === 'llm'); },
    toolKeys() { return this.keys.filter(k => this.getProviderType(k.provider) === 'tool'); },

    keyStatus(k) {
      if (k.source === 'env') return 'env var';
      if (k.source === 'db') return 'key set';
      if (k.provider === 'ollama') return 'local';
      return 'no key';
    },

    hasKey(k) { return k.source === 'env' || k.source === 'db' || k.provider === 'ollama'; },

    showBaseUrl(provider) { return ['ollama', 'llm-studio'].includes(provider); },

    getUrlPlaceholder(provider) {
      if (provider === 'ollama') return 'e.g. http://localhost:11434';
      if (provider === 'llm-studio') return 'e.g. http://localhost:8000';
      return 'Server URL…';
    },

    async refreshPricing() {
      this.pricingRefreshing = true;
      try {
        const resp = await fetch('/providers/pricing/refresh', { method: 'POST' });
        if (!resp.ok) throw new Error(await resp.text());
        const data = await resp.json();
        this.pricingCacheLabel = `Updated just now (${data.models_updated} models)`;
      } catch(e) { this.pricingCacheLabel = 'Refresh failed'; }
      finally { this.pricingRefreshing = false; }
    },

    toggleEdit(provider) {
      this.expandedProvider = this.expandedProvider === provider ? null : provider;
    },

    async save(provider) {
      const val = (this.inputs[provider] || '').trim();
      if (!val) { this.saveErrors[provider] = 'Please enter a key.'; return; }
      delete this.saveErrors[provider];
      try {
        const body = { key: val };
        if (this.displayNames[provider]) body.display_name = this.displayNames[provider];
        if (this.baseUrls[provider]) body.base_url = this.baseUrls[provider];
        const resp = await fetch('/keys/' + provider, {
          method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)
        });
        if (!resp.ok) throw new Error(await resp.text());
        this.inputs[provider] = ''; this.saved[provider] = true;
        setTimeout(() => { delete this.saved[provider]; }, 3000);
        this.expandedProvider = null;
        await this.load();
        window.dispatchEvent(new CustomEvent('provider-updated'));
      } catch(e) { this.saveErrors[provider] = e.message; }
    },

    async remove(provider) {
      delete this.saved[provider]; delete this.saveErrors[provider];
      try {
        const resp = await fetch('/keys/' + provider, { method: 'DELETE' });
        if (!resp.ok) throw new Error(await resp.text());
        await this.load();
        window.dispatchEvent(new CustomEvent('provider-updated'));
      } catch(e) { this.saveErrors[provider] = e.message; }
    }
  };
}
