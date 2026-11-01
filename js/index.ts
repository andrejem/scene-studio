import SceneStudioPanel from "./SceneStudioPanel";

const ELEMENT_NAME = "scene-studio-panel";

if (!window.customElements.get(ELEMENT_NAME)) {
    window.customElements.define(ELEMENT_NAME, SceneStudioPanel);
}
