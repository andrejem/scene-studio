// Added by andrejem (2026): styles of the panel. Colors come from the Home Assistant theme variables,
// so the panel follows light and dark themes. Wide screens (≥ 900 px) get a room list on the left
// and the scene editor as a side panel.

export const PANEL_CSS = `
:host {
    --sp-radius: 14px;
    --sp-accent: var(--primary-color, #03a9f4);
    --sp-on-accent: var(--text-primary-color, #fff);
    --sp-text: var(--primary-text-color, #212121);
    --sp-muted: var(--secondary-text-color, #727272);
    --sp-card: var(--card-background-color, var(--ha-card-background, #fff));
    --sp-bg: var(--primary-background-color, #fafafa);
    --sp-line: var(--divider-color, rgba(127, 127, 127, 0.25));
    --sp-soft: var(--secondary-background-color, rgba(127, 127, 127, 0.12));
    --sp-accent-soft: rgba(var(--rgb-primary-color, 3, 169, 244), 0.14);
    --sp-danger: var(--error-color, #db4437);
}
* { box-sizing: border-box; }
button { font: inherit; color: inherit; }

.sp-tabs {
    display: flex;
    position: sticky;
    top: 0;
    z-index: 3;
    background: var(--sp-card);
    border-bottom: 1px solid var(--sp-line);
}
.sp-tab {
    flex: 1 1 0;
    max-width: 240px;
    height: 48px;
    border: none;
    border-bottom: 2px solid transparent;
    background: transparent;
    color: var(--sp-muted);
    font-size: 15px;
    font-weight: 500;
    cursor: pointer;
}
.sp-tab.active { color: var(--sp-accent); border-bottom-color: var(--sp-accent); }

.sp-page {
    max-width: 1280px;
    margin: 0 auto;
    padding: 16px;
    color: var(--sp-text);
    user-select: none;
    display: flex;
    flex-direction: column;
    gap: 16px;
}
.sp-secondary { color: var(--sp-muted); }
.sp-small { font-size: 13px; }
.sp-strong { font-weight: 500; }
.sp-text { color: var(--sp-text); }
.sp-grow { flex: 1 1 auto; min-width: 0; }
.sp-hint { margin-top: -4px; }
.sp-empty { padding: 24px 4px; color: var(--sp-muted); max-width: 560px; }
.sp-error { color: var(--sp-danger); }
.sp-notice {
    padding: 10px 14px;
    border-radius: 12px;
    background: var(--sp-accent-soft);
    color: var(--sp-text);
}

/* buttons */
.sp-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    min-height: 40px;
    padding: 0 16px;
    border-radius: 20px;
    border: 1px solid var(--sp-line);
    background: transparent;
    color: var(--sp-text);
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    white-space: nowrap;
}
.sp-btn.primary { background: var(--sp-accent); border-color: var(--sp-accent); color: var(--sp-on-accent); }
.sp-btn.text { border-color: transparent; color: var(--sp-accent); padding: 0 10px; }
.sp-btn.danger { color: var(--sp-danger); border-color: var(--sp-danger); }
.sp-btn.small { min-height: 32px; padding: 0 12px; font-size: 13px; }
.sp-btn:disabled { opacity: 0.45; cursor: default; }
.sp-link {
    border: none;
    background: none;
    padding: 0 0 0 10px;
    color: var(--sp-accent);
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
}
.sp-icon-btn {
    width: 44px;
    height: 44px;
    border: none;
    background: transparent;
    border-radius: 22px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
}
.sp-actions { display: flex; flex-wrap: wrap; gap: 8px; }

/* chips */
.sp-chips {
    display: flex;
    gap: 8px;
    overflow-x: auto;
    padding-bottom: 2px;
    scrollbar-width: none;
}
.sp-chips::-webkit-scrollbar { display: none; }
.sp-chips.wrap { flex-wrap: wrap; overflow: visible; }
.sp-chip {
    flex: none;
    height: 34px;
    padding: 0 14px;
    border-radius: 17px;
    border: 1px solid var(--sp-line);
    background: transparent;
    color: var(--sp-text);
    font-size: 14px;
    cursor: pointer;
    white-space: nowrap;
}
.sp-chip.active { background: var(--sp-accent); border-color: var(--sp-accent); color: var(--sp-on-accent); font-weight: 500; }
.sp-chip.small { height: 28px; padding: 0 10px; font-size: 12px; border-radius: 14px; }

/* running dynamic scenes */
.sp-running-list { display: flex; flex-direction: column; gap: 8px; }
.sp-running {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 12px;
    border-radius: var(--sp-radius);
    background: var(--sp-accent-soft);
    border: 1px solid rgba(var(--rgb-primary-color, 3, 169, 244), 0.35);
}
.sp-running-thumb { width: 44px; height: 44px; border-radius: 10px; object-fit: cover; flex: none; background: var(--sp-soft); }
.sp-running-text { flex: 1 1 auto; min-width: 0; }
.sp-running-label { font-size: 12px; color: var(--sp-accent); font-weight: 500; }
.sp-running-name { font-size: 15px; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

/* scenes tab */
.sp-layout { display: grid; grid-template-columns: minmax(0, 1fr); gap: 20px; }
.sp-main { display: flex; flex-direction: column; gap: 16px; min-width: 0; }
.sp-roomnav { display: none; flex-direction: column; gap: 2px; }
.sp-roomnav-title { padding: 0 12px 8px; }
.sp-roomnav-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    height: 40px;
    padding: 0 12px;
    border: none;
    border-radius: 20px;
    background: transparent;
    color: var(--sp-text);
    font-size: 14px;
    text-align: left;
    cursor: pointer;
}
.sp-roomnav-item.active { background: var(--sp-accent-soft); color: var(--sp-accent); font-weight: 500; }
.sp-count { font-size: 12px; color: var(--sp-muted); }
.sp-page-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.sp-page-head h2 { margin: 0; font-size: 22px; font-weight: 400; }
.sp-group { display: flex; flex-direction: column; gap: 10px; }
.sp-section-head { display: flex; align-items: baseline; justify-content: space-between; }
.sp-section-head h3 { margin: 0; font-size: 16px; font-weight: 500; }

/* tile grid */
.sp-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
    gap: 10px;
}
.sp-grid.small { grid-template-columns: repeat(auto-fill, minmax(104px, 1fr)); gap: 8px; }

.tile {
    position: relative;
    height: 92px;
    margin: 0;
    padding: 0;
    border-radius: var(--sp-radius);
    cursor: pointer;
    outline: none;
}
.tile.small { height: 84px; border-radius: 12px; }
.tile:focus-visible { box-shadow: 0 0 0 2px var(--sp-accent); }
.tile.active { box-shadow: 0 0 0 3px var(--sp-accent); }
.tile-content {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    border-radius: inherit;
    overflow: hidden;
}
.tile-content:active {
    transition: filter 0.3s;
    filter: brightness(0.7);
}
.tile-bg-img {
    position: absolute;
    top: 0;
    left: 0;
    object-fit: cover;
    width: 100%;
    height: 100%;
}
.tile-bg-no-img {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background:
        linear-gradient(45deg, #000 25%, transparent 25%, transparent 75%, #000 75%, #000),
        linear-gradient(45deg, #000 25%, transparent 25%, transparent 75%, #000 75%, #000),
        #ff00ff;
    background-size: 20px 20px;
    background-position: 0 0, 10px 10px;
}
.tile-text-bg {
    position: absolute;
    left: 0;
    right: 0;
    bottom: 0;
    height: 65%;
    background: linear-gradient(to bottom, rgba(0, 0, 0, 0), rgba(0, 0, 0, 0.6));
}
.tile-text {
    position: absolute;
    bottom: 8px;
    left: 10px;
    right: 30px;
    margin: 0;
    color: #fff;
    font-size: 14px;
    font-weight: 500;
    line-height: 1.2;
    overflow: hidden;
    text-overflow: ellipsis;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
}
.tile.small .tile-text { font-size: 12px; left: 8px; right: 8px; bottom: 6px; }
.tile-check { position: absolute; right: 6px; bottom: 6px; color: #fff; }
.tile-top-icon-container {
    position: absolute;
    top: 0;
    right: 0;
    color: #fff;
    z-index: 1;
    filter: drop-shadow(0 0 2px rgba(0, 0, 0, 0.6));
}
/* with a mouse, pencil and star only show on hover (a favorite keeps its star); touch screens always show them */
@media (hover: hover) {
    .tile .tile-top-icon-container { opacity: 0; transition: opacity 0.15s; }
    .tile:hover .tile-top-icon-container,
    .tile:focus-within .tile-top-icon-container,
    .tile .tile-top-icon-container.keep { opacity: 1; }
}
.tile.muted .tile-bg-img { filter: grayscale(0.7) brightness(0.7); }
.tile-badge {
    position: absolute;
    top: 8px;
    left: 8px;
    z-index: 1;
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 2px 8px 2px 6px;
    border-radius: 10px;
    background: rgba(0, 0, 0, 0.5);
    color: #fff;
    font-size: 11px;
}
.tile-new {
    border: 2px dashed var(--sp-line);
    background: transparent;
    color: var(--sp-muted);
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 4px;
    font-size: 13px;
    font-weight: 500;
}

/* presets tab */
.sp-presets { display: flex; flex-direction: column; gap: 14px; }
.sp-card {
    background: var(--sp-card);
    border: 1px solid var(--sp-line);
    border-radius: 16px;
    padding: 12px;
    display: flex;
    flex-direction: column;
    gap: 12px;
}
.sp-apply-card { max-width: 720px; }
.sp-target-head {
    width: 100%;
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 4px 2px;
    border: none;
    background: transparent;
    text-align: left;
    cursor: pointer;
}
.sp-target-icon {
    width: 40px;
    height: 40px;
    flex: none;
    border-radius: 12px;
    background: var(--sp-accent-soft);
    color: var(--sp-accent);
    display: flex;
    align-items: center;
    justify-content: center;
}
.sp-target-text { flex: 1 1 auto; min-width: 0; display: flex; flex-direction: column; }
.sp-target-summary { font-size: 16px; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.sp-target-summary.empty { color: var(--sp-accent); }
.sp-target-picker { padding: 8px 2px 0; }

.sp-seg {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    border-radius: 12px;
    background: var(--sp-soft);
    padding: 3px;
}
.sp-seg button {
    height: 36px;
    border: none;
    border-radius: 10px;
    background: transparent;
    color: var(--sp-muted);
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
}
.sp-seg button.active { background: var(--sp-card); color: var(--sp-text); box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2); }

.sp-field { display: flex; flex-direction: column; gap: 6px; }
.sp-field-head { display: flex; justify-content: space-between; align-items: center; font-size: 14px; }
.sp-field-label { font-size: 12px; color: var(--sp-muted); }
.sp-range { width: 100%; accent-color: var(--sp-accent); height: 28px; margin: 0; cursor: pointer; }
.sp-range.off { opacity: 0.4; }

.sp-collapsible { border-top: 1px solid var(--sp-line); }
.sp-collapsible-head {
    width: 100%;
    display: flex;
    align-items: center;
    justify-content: space-between;
    min-height: 44px;
    padding: 0 2px;
    border: none;
    background: transparent;
    font-size: 14px;
    text-align: left;
    cursor: pointer;
}
.sp-options { display: flex; flex-direction: column; padding-bottom: 4px; }
.sp-option-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    min-height: 44px;
    font-size: 14px;
}
.sp-option-row.indent { padding-left: 16px; }
.sp-options-foot { display: flex; justify-content: flex-end; padding-top: 4px; }
.sp-num { display: inline-flex; align-items: center; gap: 6px; }
.sp-num input {
    width: 72px;
    height: 36px;
    padding: 0 8px;
    border-radius: 8px;
    border: 1px solid var(--sp-line);
    background: var(--sp-card);
    color: var(--sp-text);
    font-size: 15px;
    text-align: right;
}
.sp-num.small input { width: 56px; height: 32px; font-size: 14px; }
.sp-unit { color: var(--sp-muted); font-size: 13px; min-width: 14px; }

.sp-search {
    display: flex;
    align-items: center;
    gap: 10px;
    height: 44px;
    padding: 0 14px;
    border-radius: 22px;
    background: var(--sp-card);
    border: 1px solid var(--sp-line);
    color: var(--sp-muted);
    max-width: 720px;
}
.sp-search input {
    flex: 1 1 auto;
    min-width: 0;
    border: none;
    background: transparent;
    color: var(--sp-text);
    font-size: 15px;
    outline: none;
}

/* current preset of the presets tab, feedback after tapping */
.sp-block { display: block; }
.sp-current { display: flex; align-items: center; gap: 12px; padding: 2px; border-radius: 12px; }
.sp-current.flash { animation: sp-flash 1.2s ease-out; }
@keyframes sp-flash { from { background: var(--sp-accent-soft); } to { background: transparent; } }
.sp-current-thumb { width: 48px; height: 48px; border-radius: 10px; object-fit: cover; flex: none; background: var(--sp-soft); }
.sp-current-thumb.empty { border: 2px dashed var(--sp-line); background: transparent; }
.sp-applied { color: var(--sp-accent); font-size: 13px; font-weight: 500; white-space: nowrap; }
.sp-toast {
    position: fixed;
    left: 50%;
    bottom: calc(24px + env(safe-area-inset-bottom, 0px));
    transform: translateX(-50%);
    z-index: 8;
    width: max-content;
    max-width: calc(100vw - 32px);
    padding: 12px 18px;
    border-radius: 12px;
    background: var(--sp-text);
    color: var(--sp-card);
    font-size: 14px;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3);
    animation: sp-toast 3s ease forwards;
    pointer-events: none;
}
@keyframes sp-toast {
    0% { opacity: 0; transform: translate(-50%, 8px); }
    8% { opacity: 1; transform: translate(-50%, 0); }
    85% { opacity: 1; }
    100% { opacity: 0; }
}

/* import from Scene Presets */
.sp-import { display: flex; flex-direction: column; gap: 10px; }
.sp-import-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.sp-import-body { display: flex; flex-direction: column; gap: 10px; }
.sp-check { display: flex; gap: 10px; align-items: flex-start; font-size: 14px; cursor: pointer; }
.sp-check input { margin-top: 3px; accent-color: var(--sp-accent); width: 18px; height: 18px; }
.sp-actions-end { justify-content: flex-end; }

/* scene editor */
.sp-overlay {
    position: fixed;
    inset: 0;
    z-index: 10;
    background: rgba(0, 0, 0, 0.45);
    display: flex;
    justify-content: flex-end;
}
.sp-sheet {
    width: 100%;
    height: 100%;
    background: var(--sp-bg);
    color: var(--sp-text);
    display: flex;
    flex-direction: column;
    user-select: none;
}
.sp-sheet-head {
    flex: none;
    /* full screen on phones: keep the buttons below the status bar (iPhone notch, Companion app) */
    box-sizing: content-box;
    height: 56px;
    display: flex;
    align-items: center;
    gap: 4px;
    padding: env(safe-area-inset-top, 0px) calc(8px + env(safe-area-inset-right, 0px)) 0 calc(8px + env(safe-area-inset-left, 0px));
    background: var(--sp-card);
    border-bottom: 1px solid var(--sp-line);
}
.sp-sheet-title { flex: 1 1 auto; font-size: 18px; padding-left: 4px; }
.sp-sheet-body {
    flex: 1 1 auto;
    overflow-y: auto;
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 16px;
}
.sp-sheet-foot {
    flex: none;
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 12px 16px calc(12px + env(safe-area-inset-bottom, 0px));
    background: var(--sp-card);
    border-top: 1px solid var(--sp-line);
}
.sp-input {
    width: 100%;
    height: 48px;
    padding: 0 14px;
    border-radius: 10px;
    border: 1px solid var(--sp-line);
    background: var(--sp-card);
    color: var(--sp-text);
    font-size: 16px;
}
.sp-preset-row {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px;
    border-radius: var(--sp-radius);
    background: var(--sp-card);
    border: 1px solid var(--sp-line);
}
.sp-preset-thumb { width: 56px; height: 56px; border-radius: 10px; object-fit: cover; flex: none; background: var(--sp-soft); }
.sp-sheet .sp-target { padding: 8px 10px; border-radius: var(--sp-radius); background: var(--sp-card); border: 1px solid var(--sp-line); }
.sp-list {
    border-radius: var(--sp-radius);
    background: var(--sp-card);
    border: 1px solid var(--sp-line);
    overflow: hidden;
}
.sp-list-row {
    display: flex;
    flex-direction: column;
    gap: 6px;
    width: 100%;
    padding: 10px 12px;
    border: none;
    border-bottom: 1px solid var(--sp-line);
    background: transparent;
    text-align: left;
}
.sp-list-row:last-child { border-bottom: none; }
.sp-list-row.muted { color: var(--sp-muted); }
.sp-list-more { flex-direction: row; align-items: center; cursor: pointer; color: var(--sp-muted); }
.sp-list-main { display: flex; align-items: center; gap: 10px; font-size: 14px; }
.sp-list-actions { display: flex; flex-wrap: wrap; gap: 6px; }
.sp-automation {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 12px;
    border-radius: 12px;
    background: var(--sp-soft);
    color: var(--sp-text);
}
.sp-entity-id {
    display: block;
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 13px;
    user-select: text;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

@media (min-width: 900px) {
    .sp-layout { grid-template-columns: 200px minmax(0, 1fr); }
    .sp-roomnav { display: flex; position: sticky; top: 64px; align-self: start; }
    .sp-room-chips { display: none; }
    .sp-chips { flex-wrap: wrap; overflow: visible; }
    .sp-grid { grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); gap: 12px; }
    .tile { height: 110px; }
    .sp-grid.small { grid-template-columns: repeat(auto-fill, minmax(130px, 1fr)); }
    .tile.small { height: 90px; }
    .sp-sheet { width: 460px; border-left: 1px solid var(--sp-line); box-shadow: -4px 0 16px rgba(0, 0, 0, 0.25); }
    .sp-tabs { padding-left: 16px; }
}
`;
