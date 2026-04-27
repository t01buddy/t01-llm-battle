# UI Redesign — Paper Theme + 3-Column Layout

**Version**: 0.1.x (polish release)
**Status**: Draft

## Overview

Redesign the battle app UI from a 2-column text sidebar to a 3-column layout with icon rail, tabbed content, and battle list rail. Upgrade to the new Paper theme with Fraunces serif display font. All existing functionality is preserved — this is a visual/UX overhaul only, no backend changes.

## Layout Mockup

```
┌──────────────────────────────────────────────────────────┐
│ battle-app  theme-paper                                  │
├────────┬─────────────────────────────────┬───────────────┤
│        │ ┌─ Topbar ──────────────────┐   │               │
│  Icon  │ │ Battle Name    run-id     │   │  Right Rail   │
│  Rail  │ └───────────────────────────┘   │               │
│        │ ┌─ Tabs ────────────────────┐   │  BATTLES      │
│  ☰ ←→  │ │ Setup │ Run │ Results    │   │  + New        │
│        │ └───────────────────────────┘   │               │
│  ⚔ bat │                                │  ● Battle A   │
│        │ ┌─ Tab Content ─────────────┐   │    new        │
│  ⚙ prov│ │                           │   │               │
│        │ │  (Sources / Fighters /     │   │  ○ Battle B   │
│  ☵ set │ │   Judge  —  or Run grid   │   │    done       │
│        │ │   — or Results table)      │   │               │
│        │ │                           │   │  ○ Battle C   │
│        │ └───────────────────────────┘   │               │
├────────┴─────────────────────────────────┴───────────────┤
│                (responsive: collapses on <1100px)        │
└──────────────────────────────────────────────────────────┘
```

**Icon rail** (~64px): Collapsible sidebar with icon-only navigation.
**Main content** (flex: 1): Topbar + tab bar + active tab content.
**Right rail** (~320px): Battle list with active highlighting and status tags.

---

## Icon Rail Sidebar

Replaces the current text sidebar. Collapsed by default on narrow viewports.

```
┌────────┐
│  Logo  │  ← brand mark / app icon
│        │
│  ⚔     │  ← Battles (navigates to battle view)
│  ⚙     │  ← Providers (opens providers modal)
│  ☵     │  ← Settings (theme, preferences)
│        │
│  ◀▶    │  ← Collapse toggle
└────────┘
```

- Click "Providers" icon → opens **Providers Modal** (overlay, not inline)
- Click "Battles" icon → shows battle list in right rail (or scrolls to it on mobile)
- Hover shows tooltip with label
- Collapse toggle reduces rail to icon-only (64px) or expands to include labels (~200px)

---

## Tab Bar

Content area uses tabs instead of vertically stacked sections:

| Tab | Content |
|-----|---------|
| **Setup** | Sources upload + Fighters cards + Judge config |
| **Run** | Run progress bar + source × fighter status grid |
| **Results** | Fighter summary leaderboard + per-source breakdown |

- Tab badges: Run tab shows spinner during active run; Results tab shows score count
- Switching tabs preserves state (no re-fetch)

---

## Setup Tab

### Sources Section

```
┌─ 1 Sources ─────────────────────────────────────────┐
│                                                      │
│  ┌──────────────────────────────────┐  + Add Text    │
│  │  Upload files                    │                │
│  │  .txt .md .csv                   │                │
│  │  [Choose Files]                  │                │
│  └──────────────────────────────────┘                │
│                                                      │
│  source-1.txt                              ✕         │
│  source-2.md                               ✕         │
│  cases.csv (50 rows)                       ✕         │
└──────────────────────────────────────────────────────┘
```

### Fighters Section

```
┌─ 2 Fighters ────────────────────── + Add Fighter ────┐
│                                                       │
│  ┌─ Fighter 1 ──────────────────────────────────────┐ │
│  │  ① openai / gpt-4o / temp 0.7     + Add Step    │ │
│  │     System: "Summarize the input..."    ▲ ▼ ✕    │ │
│  │  ② anthropic / claude-sonnet-4-6       ▲ ▼ ✕    │ │
│  │     System: "Refine the summary..."              │ │
│  └──────────────────────────────────────────────────┘ │
│                                                       │
│                    ─── VS ───                         │
│                                                       │
│  ┌─ Fighter 2 ──────────────────────────────────────┐ │
│  │  ① openai / gpt-4o-mini / temp 0.3  + Add Step  │ │
│  │     System: "Summarize..."              ▲ ▼ ✕    │ │
│  └──────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────┘
```

- VS divider between fighters (styled `.ba-vs-mark`)
- Numbered step badges (①②③)
- Step controls: reorder (▲▼), delete (✕)
- Each step shows: provider / model / temperature inline

### Judge Section

```
┌─ 3 Judge ──────────────────────── ○ Disabled ────────┐
│                                                       │
│  Provider: [openai ▼]    Model: [gpt-4o-mini ▼]     │
│                                                       │
│  Rubric:                                             │
│  ┌──────────────────────────────────────────────────┐ │
│  │  Score each response on a scale of 0-10...       │ │
│  │  (EasyMDE editor preserved)                      │ │
│  └──────────────────────────────────────────────────┘ │
│                                                       │
│  [Save]  [Run Battle]                                │
└───────────────────────────────────────────────────────┘
```

---

## Run Tab

```
┌─ Run Progress ──────────────────────────────────────┐
│  ● Running...  62%  ████████████░░░░░░  12/20 steps │
└─────────────────────────────────────────────────────┘

┌─ Status Grid ───────────────────────────────────────┐
│              │ Fighter 1  │ Fighter 2  │ Fighter 3  │
│──────────────┼────────────┼────────────┼────────────│
│  Source 1    │    ● done  │    ● done  │    ◌ run   │
│  Source 2    │    ● done  │    ◌ run   │    ○ wait  │
│  Source 3    │    ◌ run   │    ○ wait  │    ○ wait  │
│  Source 4    │    ○ wait  │    ○ wait  │    ○ wait  │
└─────────────────────────────────────────────────────┘

● done (green)  ◌ running (pulse)  ○ waiting (gray)  ✕ error (red)
```

---

## Results Tab

### Fighter Summary (Leaderboard)

```
┌─ Fighter Summary ───────────────────────────────────────────┐
│  #  │ Fighter    │ Avg Score │ Cost   │ Tokens │ Time │ S/F │
│─────┼────────────┼───────────┼────────┼────────┼──────┼─────│
│  1  │ Fighter 1  │   8.7     │ $0.042 │  2,840 │ 12s  │ 5/0│
│  2  │ Fighter 2  │   7.2     │ $0.018 │  1,200 │  8s  │ 4/1│
│  3  │ Fighter 3  │   6.5     │ $0.065 │  4,100 │ 22s  │ 5/0│
└─────────────────────────────────────────────────────────────┘
```

### Per-Source Breakdown

```
┌─ Source: "input-1.txt" ─────────────────────────────────────┐
│                                                              │
│  Fighter 1          8.5    │  Fighter 2          7.0         │
│  ▶ Show output             │  ▶ Show output                  │
│  1 step · $0.008 · 32/74t │  1 step · $0.003 · 26/45t       │
│                             │                                 │
│  [expanded output here      │                                 │
│   when clicked]             │                                 │
└──────────────────────────────────────────────────────────────┘
```

---

## Providers Modal

Opens as a modal overlay (not inline in sidebar).

```
┌─ Providers ──────────────────────── ✕ ──┐
│                                          │
│  LLM Providers                           │
│  ┌──────────────────────────────────┐    │
│  │ OpenAI     ● key set    [●] ✎   │    │
│  │ Anthropic  ● key set    [●] ✎   │    │
│  │ Google     ○ no key     [○] ✎   │    │
│  │ Groq       ○ no key     [○] ✎   │    │
│  │ OpenRouter ○ no key     [○] ✎   │    │
│  │ Ollama     ● running    [●] ✎   │    │
│  │ LM Studio  ○ offline    [○] ✎   │    │
│  └──────────────────────────────────┘    │
│                                          │
│  Tool Providers                          │
│  ┌──────────────────────────────────┐    │
│  │ Serper     ○ no key     [○] ✎   │    │
│  │ Tavily     ○ no key     [○] ✎   │    │
│  │ Firecrawl  ○ no key     [○] ✎   │    │
│  └──────────────────────────────────┘    │
│                                          │
│  [Refresh Pricing]                       │
└──────────────────────────────────────────┘
```

- Toggle: enable/disable provider
- Edit (✎): opens inline form for API key, display name, server URL
- Key status: "key set" / "no key" / "running" / "offline"
- Refresh Pricing button preserved from current implementation

---

## Paper Theme (Upgraded)

| Token | Value |
|-------|-------|
| `bg.paper` | `#FAF9F6` (warm off-white / parchment) |
| `bg.card` | `#FFFFFF` (white with subtle shadow) |
| Primary accent | `#D4A02A` (warm gold) |
| `text.high` | `#1a1a2e` (dark primary) |
| `text.mid` | `#6b7280` (muted secondary) |
| Borders | `#e5e5e5` (light gray) |
| Display font | `"Fraunces", serif` (headings, battle names, scores) |
| Body font | `"Inter", system-ui, sans-serif` (content, labels) |
| Mono font | `"JetBrains Mono", monospace` (metadata, IDs, costs) |

---

## CSS Architecture

All component classes use `.ba-*` prefix (battle-app). Framework-agnostic — works with Alpine.js directly.

**Key classes**: `.ba-sidebar`, `.ba-rail`, `.ba-main`, `.ba-topbar`, `.ba-tabs`, `.ba-tab`, `.ba-section`, `.ba-card`, `.ba-fighters`, `.ba-fighter`, `.ba-step`, `.ba-vs-mark`, `.ba-btn`, `.ba-toggle`, `.ba-input`, `.ba-select`, `.ba-modal`, `.ba-table`, `.ba-rungrid`, `.ba-status-dot`

**Responsive**: `@media (max-width: 1100px)` collapses sidebar, hides right rail.

---

## Right Rail (Battle List)

```
┌─ BATTLES ──────── + New ─┐
│                           │
│  ● Battle 2026-04-26 ◄── │  ← active (highlighted)
│    new                    │
│                           │
│  ○ Battle 2026-04-23      │
│    done                   │
│                           │
│  ○ My First Battle        │
│    3 runs                 │
└───────────────────────────┘
```

- Active battle highlighted with accent color
- Status tags: "new" (no runs), "done" (has results), run count
- Click to switch battles
- "+ New" button creates new battle

---

## What Stays Unchanged

All existing backend functionality preserved:
- Provider management (enable/disable, API key, server URL, pricing refresh)
- Source upload (text/md files, CSV with column selection)
- Manual fighters (user-entered results)
- Judge rubric (EasyMDE markdown editor)
- Custom model IDs
- Live run polling
- Markdown report generation + download
- All API endpoints unchanged

---

## Design Source Files

The design prototype is in `/Users/charles/Downloads/battle (2).zip`:
- `app.css` — all `.ba-*` component CSS (1,256 lines, framework-agnostic)
- `theme-paper.css` — Paper theme CSS variables
- `battle-app.jsx` — React prototype (translate to Alpine.js)
- `data.js` — mock data structure reference
