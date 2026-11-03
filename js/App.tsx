// Modified by andrejem (2026): presets can be reloaded after creating or changing one in the panel;
// tabs "Scenes" / "Presets", running dynamic scenes on top, the scene editor and the import from Scene Presets;
// preset data is loaded with the login of the user
import React, {useEffect, useMemo, useRef, useState} from "react";
import {PresetApplyPage} from "./pages/PresetApplyPage";
import {ScenesPage} from "./pages/ScenesPage";
import {Category, Preset} from "./types";
import {useSessionStorage} from "./hooks/useSessionStorage";
import {useLocalStorage} from "./hooks/useLocalStorage";
import {makeTranslate} from "./i18n";
import {RunningScene, RunningStrip} from "./components/RunningStrip";
import {ImportBanner, importBrowserSettings} from "./components/ImportBanner";
import {SceneDraft, SceneEditor, draftFromScene} from "./components/SceneEditor";
import {DEFAULT_TUNABLES, SavedScene, readLocalStorage, sceneAreaId, sceneToTunables, targetsAreaId} from "./tunables";

declare module "react" {
    namespace JSX {
        interface IntrinsicElements {
            ["ha-app-layout"]: any;
            ["app-header"]: any;
            ["app-toolbar"]: any;
            ["ha-menu-button"]: any;
            ["ha-entity-toggle"]: any;
            ["ha-top-app-bar-fixed"]: any;
            ["ha-selector"]: any;
            ["ha-switch"]: any;
            ["ha-icon"]: any;
            ["ha-icon-button"]: any;
            ["ha-card"]: any;
            ["ha-settings-row"]: any;
            ["ha-dialog"]: any;
            ["mwc-button"]: any;
        }
    }
}

const DYNAMIC_SCENE_REFRESH_INTERVAL = 30 * 1000;

// before the first render, so the settings are read by the components
importBrowserSettings();

export const App : React.FunctionComponent<{
    hass: any,
    narrow: boolean,
}> = ({
    hass,
    narrow,
}): React.JSX.Element => {
    const t = useMemo(() => makeTranslate(hass), [hass?.locale?.language, hass?.language]); // eslint-disable-line react-hooks/exhaustive-deps
    const [categories, setCategories] = useSessionStorage<Array<Category>>("scene_studio_categories",[]);
    const [presets, setPresets] = useSessionStorage<Array<Preset>>("scene_studio_presets",[]);
    const [tab, setTab] = useLocalStorage<string>("scene_studio_tab", "scenes");
    const [savedScenes, setSavedScenes] = useState<Array<SavedScene> | null>(null);
    const [running, setRunning] = useState<Array<RunningScene>>([]);
    const [draft, setDraft] = useState<SceneDraft | null>(null);
    const lastRunningRefresh = useRef(0);

    const fetchData = React.useCallback(async () => {
        try {
            const response = await hass.fetchWithAuth("/assets/scene_studio/scene_studio.json?t=" + Date.now());
            const data = await response.json();

            setCategories(data.categories);
            setPresets(data.presets);
        } catch (error) {
            console.error("Error fetching data:", error);
        }
    }, []); // eslint-disable-line react-hooks/exhaustive-deps

    const fetchSavedScenes = React.useCallback(() => {
        hass.callWS({type: "scene_studio/get_saved_scenes"}).then(result => {
            setSavedScenes(result?.saved_scenes ?? []);
        }).catch(() => {
            setSavedScenes(prev => prev ?? []);
        });
    }, [hass]);

    const fetchRunning = React.useCallback(() => {
        lastRunningRefresh.current = Date.now();
        hass.callWS({type: "scene_studio/get_dynamic_scenes"}).then(result => {
            setRunning(result?.dynamic_scenes ?? []);
        }).catch(() => {
            /* intentional */
        });
    }, [hass]);

    useEffect(() => {
        fetchData().then(() => {
            /* intentional */
        });
        fetchSavedScenes();
    }, []); // eslint-disable-line react-hooks/exhaustive-deps

    // dynamic scenes can also be started or stopped elsewhere: refresh now and then
    useEffect(() => {
        if (Date.now() - lastRunningRefresh.current >= DYNAMIC_SCENE_REFRESH_INTERVAL) {
            fetchRunning();
        }
    }, [hass, fetchRunning]);

    const presetMap = useMemo(() => {
        const map: {[id: string]: Preset} = {};
        presets.forEach(p => {
            map[p.id] = p;
        });
        return map;
    }, [presets]);

    const favorites = (): Array<string> => readLocalStorage<Array<string>>("scene_studio_apply_page_favorite_presets", []);

    const activateScene = (id: string) => {
        hass.callService("scene_studio", "activate_saved_scene", {id: id}).finally(() => fetchRunning());
    };

    const stopRunning = (id: string) => {
        hass.callService("scene_studio", "stop_dynamic_scene", {id: id}).finally(() => fetchRunning());
    };

    const openNewScene = (areaId?: string) => {
        const last = readLocalStorage<string>("scene_studio_last_preset", "");
        const presetId = last && presetMap[last] ? last : (favorites()[0] ?? "");
        setDraft({
            name: "",
            areaId,
            presetId,
            targets: areaId ? {area_id: [areaId]} : {},
            tun: {...DEFAULT_TUNABLES},
            exclude: [],
            keepGroups: [],
            optional: [],
            lightBrightness: {}
        });
    };

    return (
        <ha-top-app-bar-fixed>
            <ha-menu-button
                slot="navigationIcon"
                hass={hass}
                narrow={narrow}
            />
            <div slot="title">Scene Studio</div>

            <div className={"sp-tabs"} role={"tablist"}>
                <button role={"tab"} aria-selected={tab !== "presets"} className={"sp-tab" + (tab !== "presets" ? " active" : "")} onClick={() => setTab("scenes")}>
                    {t("tab_scenes")}
                </button>
                <button role={"tab"} aria-selected={tab === "presets"} className={"sp-tab" + (tab === "presets" ? " active" : "")} onClick={() => setTab("presets")}>
                    {t("tab_presets")}
                </button>
            </div>

            <div className={"sp-page"}>
                <ImportBanner
                    hass={hass}
                    t={t}
                    onImported={() => {
                        fetchData();
                        fetchSavedScenes();
                    }}
                />

                <RunningStrip
                    hass={hass}
                    t={t}
                    running={running}
                    presetMap={presetMap}
                    savedScenes={savedScenes ?? []}
                    onStop={stopRunning}
                />

                {
                    tab === "presets" ?
                        <PresetApplyPage
                            hass={hass}
                            t={t}
                            categories={categories}
                            presets={presets}
                            onPresetsChanged={() => {
                                fetchData();
                            }}
                            onApplied={() => fetchRunning()}
                            onSaveAsScene={(presetId, targets, tun) => {
                                setDraft({
                                    name: "",
                                    areaId: targetsAreaId(hass, targets),
                                    presetId,
                                    targets,
                                    tun: {...tun},
                                    exclude: [],
                                    keepGroups: [],
                                    optional: [],
                                    lightBrightness: {}
                                });
                            }}
                        /> :
                        <ScenesPage
                            hass={hass}
                            t={t}
                            savedScenes={savedScenes}
                            presetMap={presetMap}
                            running={running}
                            onActivate={activateScene}
                            onEdit={(scene) => setDraft(draftFromScene(scene, sceneToTunables(scene), sceneAreaId(hass, scene)))}
                            onNew={openNewScene}
                            onShowPresets={() => setTab("presets")}
                        />
                }
            </div>

            <SceneEditor
                hass={hass}
                t={t}
                draft={draft}
                presets={presets}
                favoritePresets={draft ? favorites() : []}
                onClose={() => setDraft(null)}
                onSaved={() => {
                    fetchSavedScenes();
                    fetchRunning();
                }}
            />
        </ha-top-app-bar-fixed>
    );
};
