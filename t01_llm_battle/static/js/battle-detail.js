// ── Battle detail (sources) ──────────────────────────────
function battleDetail() {
  return {
    sources: [], uploading: false, error: null,
    running: false, fighterCount: 0, runError: null, currentBattleId: null,
    battleName: '', nameInput: '', nameSaving: false,
    showTextForm: false, textItems: [{ content: '', label: '' }], addingText: false,
    // Judge state
    judgeEnabled: false, judgeProvider: 'openai', judgeModel: 'gpt-4o', judgeModelCustom: '',
    judgeRubric: DEFAULT_RUBRIC, judgeSaving: false, judgeSaved: false, judgeError: null,

    init() {
      window.addEventListener('fighters-updated', e => { this.fighterCount = e.detail.count; });
    },

    llmProviders() {
      const pi = window._providerInfoList || [];
      return pi.filter(p => p.provider_type === 'llm' && p.enabled);
    },

    judgeProviderModels() {
      const pi = window._providerInfoList || [];
      const info = pi.find(p => p.name === this.judgeProvider);
      return info ? info.models : [];
    },

    onJudgeProviderChange() {
      const p = this.judgeProvider;
      const models = this.judgeProviderModels();
      this.judgeModel = models.length ? models[0].id : (DEFAULT_MODELS[p] || 'gpt-4o');
      this.judgeModelCustom = '';
    },

    onJudgeToggle() {
      if (!this.judgeEnabled) {
        // Disable: clear judge on server
        this.saveJudgeDisabled();
      }
    },

    async saveJudgeDisabled() {
      if (!this.currentBattleId) return;
      try {
        await fetch(`/battles/${this.currentBattleId}`, {
          method: 'PUT', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ judge_enabled: false })
        });
      } catch(_) {}
    },

    async saveJudge() {
      if (!this.currentBattleId) return;
      this.judgeSaving = true; this.judgeError = null; this.judgeSaved = false;
      try {
        const resp = await fetch(`/battles/${this.currentBattleId}`, {
          method: 'PUT', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            judge_provider: this.judgeProvider,
            judge_model: this.judgeModel || this.judgeModelCustom,
            judge_rubric: this.judgeRubric
          })
        });
        if (!resp.ok) throw new Error(await resp.text());
        this.judgeSaved = true;
        setTimeout(() => { this.judgeSaved = false; }, 2000);
      } catch(e) { this.judgeError = e.message; }
      finally { this.judgeSaving = false; }
    },

    async load(battleId) {
      if (!battleId) return;
      this.currentBattleId = battleId; this.error = null;
      try {
        const [srcResp, bResp] = await Promise.all([
          fetch(`/battles/${battleId}/sources`),
          fetch(`/battles/${battleId}`)
        ]);
        if (!srcResp.ok) throw new Error(await srcResp.text());
        const data = await srcResp.json();
        this.sources = data.sources || [];
        if (bResp.ok) {
          const b = await bResp.json();
          this.battleName = b.name || '';
          this.nameInput = this.battleName;
          // Restore judge state
          this.judgeEnabled = !!(b.judge_provider && b.judge_model);
          if (this.judgeEnabled) {
            this.judgeProvider = b.judge_provider;
            this.judgeRubric = b.judge_rubric || DEFAULT_RUBRIC;
            // Check if saved model is in catalog; if not, treat as custom
            const catalogModels = this.judgeProviderModels();
            const inCatalog = catalogModels.some(m => m.id === b.judge_model);
            if (inCatalog || catalogModels.length === 0) {
              this.judgeModel = b.judge_model;
              this.judgeModelCustom = '';
            } else {
              this.judgeModel = '';
              this.judgeModelCustom = b.judge_model;
            }
          }
        }
      } catch(e) { this.error = e.message; }
    },

    async saveName() {
      if (!this.currentBattleId || !this.nameInput.trim()) return;
      this.nameSaving = true;
      try {
        const resp = await fetch(`/battles/${this.currentBattleId}`, {
          method: 'PUT',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ name: this.nameInput.trim() })
        });
        if (!resp.ok) throw new Error(await resp.text());
        this.battleName = this.nameInput.trim();
        window.dispatchEvent(new CustomEvent('battle-created'));
      } catch(e) { this.error = e.message; }
      finally { this.nameSaving = false; }
    },

    async runBattle() {
      if (!this.currentBattleId) return;
      this.running = true; this.runError = null;
      try {
        const resp = await fetch('/runs', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ battle_id: this.currentBattleId })
        });
        if (!resp.ok) throw new Error(await resp.text());
        const data = await resp.json();
        window.location.hash = '#/runs/' + data.run_id;
      } catch(e) { this.runError = e.message; this.running = false; }
    },

    async upload(event, battleId) {
      if (!battleId) return;
      const files = Array.from(event.target?.files || event.dataTransfer?.files || []);
      if (!files.length) return;
      this.uploading = true; this.error = null;
      for (const file of files) {
        try {
          const formData = new FormData();
          formData.append('file', file);
          const resp = await fetch(`/battles/${battleId}/sources`, { method: 'POST', body: formData });
          if (!resp.ok) throw new Error(`${file.name}: ${await resp.text()}`);
          const data = await resp.json();
          const newItems = data.sources || (data.id ? [data] : []);
          this.sources.push(...newItems);
        } catch(e) { this.error = e.message; }
      }
      event.target.value = '';
      this.uploading = false;
      window.dispatchEvent(new CustomEvent('source-updated'));
    },

    async addTextSources(battleId) {
      if (!battleId) return;
      this.addingText = true; this.error = null;
      const items = this.textItems.filter(i => i.content.trim());
      for (let idx = 0; idx < items.length; idx++) {
        try {
          const formData = new FormData();
          const content = items[idx].content.trim();
          formData.append('text', content);
          const words = content.split(/\s+/);
          const lbl = words.length <= 6
            ? content
            : words.slice(0, 3).join(' ') + ' ... ' + words.slice(-3).join(' ');
          formData.append('label', lbl);
          const resp = await fetch(`/battles/${battleId}/sources`, { method: 'POST', body: formData });
          if (!resp.ok) throw new Error(await resp.text());
          const data = await resp.json();
          const newItems = data.sources || (data.id ? [data] : []);
          this.sources.push(...newItems);
        } catch(e) { this.error = e.message; }
      }
      this.textItems = [{ content: '', label: '' }];
      this.showTextForm = false;
      this.addingText = false;
      window.dispatchEvent(new CustomEvent('source-updated'));
    },

    async remove(battleId, sourceId) {
      this.error = null;
      try {
        const resp = await fetch(`/battles/${battleId}/sources/${sourceId}`, { method: 'DELETE' });
        if (!resp.ok) throw new Error(await resp.text());
        this.sources = this.sources.filter(s => s.id !== sourceId);
        window.dispatchEvent(new CustomEvent('source-updated'));
      } catch(e) { this.error = e.message; }
    }
  };
}
