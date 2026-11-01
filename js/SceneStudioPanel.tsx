// Modified by andrejem (2026): styles moved to styles.ts (theme colors, wide-screen layout)
// @ts-nocheck
// noinspection JSUnusedGlobalSymbols

import {Container} from "react-dom";
import {App} from "./App";
import {createRoot, Root} from "react-dom/client";
import {loadConfigDashboard} from "./helpers";
import {PANEL_CSS} from "./styles";

class SceneStudioPanel extends HTMLElement {
    initialized: boolean = false;
    shadow: Container;
    _hass: any;
    private _narrow: boolean = false;
    private root: Root;
    private styleElem: HTMLStyleElement;
    private container: HTMLDivElement;

    constructor() {
        super();
    }

    connectedCallback() {
        this.shadow = this.attachShadow({mode: "open"});

        this.styleElem = document.createElement("style");
        this.container = document.createElement("div");

        this.shadow.append(this.styleElem);
        this.shadow.append(this.container);

        this.styleElem.textContent = PANEL_CSS;

        this.root = createRoot(this.container);

        this.initialize().then(() => {
            console.log("dependencies loaded");

            this.initialized = true;
        });
    }

    set hass(hass) {
        this._hass = hass;

        this.renderElement();
    }

    set narrow(narrow) {
        this._narrow = narrow;

        this.renderElement();
    }

    renderElement() {
        if (this.initialized) {
            this.root.render(
                <App
                    hass={this._hass}
                    narrow={this._narrow}
                />
            );
        } else {
            setTimeout(() => {
                this.renderElement();
            }, 100);
        }
    }

    async initialize() {
        this.prefetchLabels().catch(() => {/* can't happen */}); // Without this, the pickers can get unhappy sometimes

        await loadConfigDashboard();
    }

    private prefetchLabels(): Promise<void> {
        return new Promise((resolve) => {
            // Mimics @lit/context ContextRequestEvent
            const event = new Event("context-request", {
                bubbles: true,
                composed: true,
            }) as any;
            event.context = "labels";
            event.contextTarget = this;
            event.subscribe = false;
            event.callback = () => resolve();

            setTimeout(resolve, 5_000);
            this.dispatchEvent(event);
        });
    }
}

export default SceneStudioPanel;
