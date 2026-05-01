// ── Fighter list ─────────────────────────────────────────
function fighterList() {
  return {
    battleId: null, fighters: [], loadingFighters: false, fightersError: null,
    showAddFighter: false, newFighter: { name: '', is_manual: false },
    addingFighter: false, addFighterError: null,
    activeStepFighterId: null,
    newStep: { system_prompt: '', provider: 'openai', model_id: '', model_id_custom: '', provider_config: '{}', selected_tools: [] },
    addingStep: false, addStepError: null,
    activeEditStepId: null,
    editStep: { system_prompt: '', provider: 'openai', model_id: '', provider_config: '{}' },
    savingStep: false, editStepError: null,
    providers: ['openai', 'anthropic', 'google', 'groq', 'openrouter', 'ollama'],
    providerInfoList: [],

    _dispatchCount() {
      window.dispatchEvent(new CustomEvent('fighters-updated', { detail: { count: this.fighters.length } }));
    },

    stepProviderType() {
      const info = this.providerInfoList.find(p => p.name === this.newStep.provider);
      return info ? info.provider_type : null;
    },
    stepProviderModels() {
      const info = this.providerInfoList.find(p => p.name === this.newStep.provider);
      return info ? info.models : [];
    },
    stepPricingHint() {
      const mid = this.newStep.model_id;
      if (!mid) return null;
      const m = this.stepProviderModels().find(x => x.id === mid);
      return m ? m.pricing_label : null;
    },
    stepNativeTools() {
      const info = this.providerInfoList.find(p => p.name === this.newStep.provider);
      return (info && info.native_tools) ? info.native_tools : [];
    },
    onStepProviderChange() {
      const models = this.stepProviderModels();
      this.newStep.model_id = models.length ? models[0].id : '';
      this.newStep.model_id_custom = '';
      this.newStep.selected_tools = [];
    },

    editStepProviderType() {
      const info = this.providerInfoList.find(p => p.name === this.editStep.provider);
      return info ? info.provider_type : null;
    },
    editStepProviderModels() {
      const info = this.providerInfoList.find(p => p.name === this.editStep.provider);
      return info ? info.models : [];
    },

    startEditStep(step) {
      const provider = step.provider;
      const model_id = step.model_id;
      this.editStep = { system_prompt: step.system_prompt || '', provider: provider, model_id: model_id, provider_config: step.provider_config || '{}' };
      this.editStepError = null;
      this.$nextTick(() => {
        this.activeEditStepId = step.id;
        this.$nextTick(() => {
          this.editStep.provider = provider;
          this.editStep.model_id = model_id;
        });
      });
    },

    cancelEditStep() { this.activeEditStepId = null; this.editStepError = null; },

    async saveEditStep(fighterId, step) {
      if (!this.battleId || !fighterId || !step.id) return;
      this.savingStep = true; this.editStepError = null;
      try {
        const resp = await fetch(`/battles/${this.battleId}/fighters/${fighterId}/steps/${step.id}`, {
          method: 'PUT', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ position: step.position, system_prompt: this.editStep.system_prompt || null, provider: this.editStep.provider, model_id: this.editStep.model_id, provider_config: this.editStep.provider_config || '{}' })
        });
        if (!resp.ok) throw new Error(await resp.text());
        const updated = await resp.json();
        const fighter = this.fighters.find(f => f.id === fighterId);
        if (fighter) {
          const idx = fighter.steps.findIndex(s => s.id === step.id);
          if (idx !== -1) fighter.steps.splice(idx, 1, updated);
        }
        this.activeEditStepId = null;
      } catch(e) { this.editStepError = e.message; }
      finally { this.savingStep = false; }
    },

    async moveStep(fighterId, stepId, direction) {
      if (!this.battleId) return;
      try {
        const resp = await fetch(`/battles/${this.battleId}/fighters/${fighterId}/steps/${stepId}/move?direction=${direction}`, { method: 'PATCH' });
        if (!resp.ok) throw new Error(await resp.text());
        const steps = await resp.json();
        const fighter = this.fighters.find(f => f.id === fighterId);
        if (fighter) fighter.steps = steps;
      } catch(e) { alert('Move failed: ' + e.message); }
    },

    async deleteStep(fighterId, stepId) {
      if (!this.battleId) return;
      try {
        const resp = await fetch(`/battles/${this.battleId}/fighters/${fighterId}/steps/${stepId}`, { method: 'DELETE' });
        if (!resp.ok) throw new Error(await resp.text());
        const fighter = this.fighters.find(f => f.id === fighterId);
        if (fighter) fighter.steps = fighter.steps.filter(s => s.id !== stepId);
        if (this.activeEditStepId === stepId) this.activeEditStepId = null;
      } catch(e) { alert('Delete failed: ' + e.message); }
    },

    async load(battleId) {
      this.battleId = battleId;
      this.loadingFighters = true; this.fightersError = null;
      try {
        const [fightersResp, provResp] = await Promise.all([
          fetch('/battles/' + battleId + '/fighters'),
          fetch('/providers'),
        ]);
        if (!fightersResp.ok) throw new Error(await fightersResp.text());
        const fighters = await fightersResp.json();
        if (provResp.ok) {
          this.providerInfoList = await provResp.json();
          window._providerInfoList = this.providerInfoList;
          this.providers = this.providerInfoList.filter(p => p.enabled).map(p => p.name);
        }
        const firstLlm = this.providerInfoList.find(p => p.provider_type === 'llm' && p.enabled);
        if (firstLlm) {
          this.newStep.provider = firstLlm.name;
          this.newStep.model_id = firstLlm.models.length ? firstLlm.models[0].id : '';
        }
        const withSteps = await Promise.all(fighters.map(async f => {
          try {
            const r = await fetch('/battles/' + battleId + '/fighters/' + f.id);
            if (r.ok) return await r.json();
          } catch(_) {}
          return { ...f, steps: [] };
        }));
        this.fighters = withSteps.slice().sort((a, b) => (a.position ?? 0) - (b.position ?? 0));
        this._dispatchCount();
      } catch(e) { this.fightersError = e.message; }
      finally { this.loadingFighters = false; }
    },

    async addFighter(battleId) {
      this.addingFighter = true; this.addFighterError = null;
      try {
        const resp = await fetch('/battles/' + battleId + '/fighters', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: this.newFighter.name, is_manual: this.newFighter.is_manual })
        });
        if (!resp.ok) throw new Error(await resp.text());
        const fighter = await resp.json();
        this.fighters.push({ ...fighter, steps: [] });
        this.newFighter = { name: '', is_manual: false };
        this.showAddFighter = false;
        this._dispatchCount();
      } catch(e) { this.addFighterError = e.message; }
      finally { this.addingFighter = false; }
    },

    toggleAddStep(fighterId) {
      if (this.activeStepFighterId === fighterId) {
        this.activeStepFighterId = null;
      } else {
        this.activeStepFighterId = fighterId;
        const firstLlm = this.providerInfoList.find(p => p.provider_type === 'llm' && p.enabled);
        const defaultProvider = firstLlm ? firstLlm.name : 'openai';
        const defaultModels = firstLlm ? firstLlm.models : [];
        this.newStep = {
          system_prompt: '', provider: defaultProvider,
          model_id: defaultModels.length ? defaultModels[0].id : '',
          model_id_custom: '', provider_config: '{}', selected_tools: [],
        };
        this.addStepError = null;
      }
    },

    async addStep(battleId, fighterId) {
      this.addingStep = true; this.addStepError = null;
      try {
        const fighter = this.fighters.find(f => f.id === fighterId);
        const position = fighter ? (fighter.steps ? fighter.steps.length : 0) : 0;
        const finalModelId = this.newStep.model_id === '' ? this.newStep.model_id_custom : this.newStep.model_id;
        let configObj = {};
        try { configObj = JSON.parse(this.newStep.provider_config || '{}'); } catch(_) {}
        if (this.newStep.selected_tools && this.newStep.selected_tools.length > 0) {
          configObj.tools = this.newStep.selected_tools;
        }
        const resp = await fetch('/battles/' + battleId + '/fighters/' + fighterId + '/steps', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            position, system_prompt: this.newStep.system_prompt || null,
            provider: this.newStep.provider, model_id: finalModelId,
            provider_config: JSON.stringify(configObj),
          })
        });
        if (!resp.ok) throw new Error(await resp.text());
        const step = await resp.json();
        if (fighter) { if (!fighter.steps) fighter.steps = []; fighter.steps.push(step); }
        this.activeStepFighterId = null;
        const firstLlm = this.providerInfoList.find(p => p.provider_type === 'llm' && p.enabled);
        this.newStep = {
          system_prompt: '',
          provider: firstLlm ? firstLlm.name : 'openai',
          model_id: firstLlm && firstLlm.models.length ? firstLlm.models[0].id : '',
          model_id_custom: '', provider_config: '{}', selected_tools: [],
        };
      } catch(e) { this.addStepError = e.message; }
      finally { this.addingStep = false; }
    }
  };
}
