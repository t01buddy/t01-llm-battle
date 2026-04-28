// ── App (router) ─────────────────────────────────────────
function app() {
  return {
    route: 'battles',
    params: {},
    hasActiveProvider: true,
    sidebarOpen: false,
    railExpanded: true,
    activeTab: 'setup',

    async checkKeys() {
      try {
        const resp = await fetch('/keys');
        const keys = await resp.json();
        this.hasActiveProvider = keys.some(k => k.source === 'env' || k.source === 'db');
      } catch(_) { this.hasActiveProvider = true; }
    },

    async init() {
      this.parseRoute();
      await this.checkKeys();
      window.addEventListener('hashchange', () => {
        this.parseRoute();
      });
      window.addEventListener('set-active-tab', e => { this.activeTab = e.detail; });
      const h = window.location.hash;
      if (!h || h === '#/' || h === '#/battles' || h === '#/battles/new') {
        try {
          const resp = await fetch('/battles');
          const battles = (await resp.json()).filter(b => b && b.id);
          if (battles.length > 0) {
            const sorted = battles.sort((a, b) => b.created_at > a.created_at ? 1 : -1);
            window.location.hash = '/battles/' + sorted[0].id;
          } else {
            window.location.hash = '/battles';
          }
        } catch(_) { window.location.hash = '/battles'; }
      }
    },

    parseRoute() {
      const raw = window.location.hash.replace(/^#\//, '').trim();
      const hash = raw || 'battles';
      const parts = hash.split('/');

      if (hash === 'battles' || hash === '' || (parts[0] === 'battles' && parts[1] === 'new')) {
        this.route = 'battles'; this.params = {};
      } else if (parts[0] === 'battles' && parts[1]) {
        this.route = 'battles/detail'; this.params = { id: parts[1] };
      } else if (parts[0] === 'runs' && parts[1]) {
        this.route = 'runs/detail'; this.params = { id: parts[1] };
      } else if (parts[0] === 'results' && parts[1]) {
        this.route = 'results/detail'; this.params = { id: parts[1] };
      } else if (parts[0] === 'news-boards' && parts[1] === 'sources') {
        this.route = 'news-sources'; this.params = {};
      } else if (parts[0] === 'news-boards') {
        this.route = 'news-boards'; this.params = {};
      } else if (parts[0] === 'news-sources') {
        window.location.hash = '#/news-boards/sources';
        return;
      } else {
        this.route = 'not-found'; this.params = {};
      }
    },

    navigate(hash) {
      window.location.hash = hash;
    }
  };
}
