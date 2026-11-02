// Added by andrejem (2026): scene editor (full screen on phones, side panel on wide screens).
// Holds its own copy of the scene, so editing no longer depends on what the page currently shows.
// Replaces the former "last action" dialog: the scene entity id is shown for automations.
// Music scenes (3.2): with the preset "Music" the colors come from the album cover of a speaker,
// the editor then shows the speaker and when the scene starts by itself.

import React, {useEffect, useMemo, useRef, useState} from "react";
import HaIcon from "./hass/building_blocks/HaIcon";
import {HaTargetSelectorValue} from "./hass/selectors/HaTargetSelector";
import {Translate} from "../i18n";
import {Preset} from "../types";
import {BrightnessField, Collapsible, MoreOptions, Segmented, SwitchRow, TargetField, previewBrightness} from "./Controls";
import {PresetTile} from "./PresetTile";
import {
    DEFAULT_TUNABLES, MUSIC_PRESET_ID, MusicSettings, SavedScene, SetTunable, Tunables, areaName, hasTargets, newId, presetImage,
    sceneEntityId, tunablesToCall
} from "../tunables";

export type SceneDraft = {
    scene?: SavedScene,          // set when an existing scene is edited
    name: string,
    areaId?: string,
    presetId: string,
    targets: HaTargetSelectorValue,
    tun: Tunables,
    exclude: Array<string>,
    keepGroups: Array<string>,
    optional: Array<string>,
    lightBrightness: {[entityId: string]: number},
    music?: MusicSettings
};

type SceneLight = {entity_id: string, name: string, optional: boolean};

const sleep = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));

export const SceneEditor: React.FunctionComponent<{
    hass: any,
    t: Translate,
    draft: SceneDraft | null,
    presets: Array<Preset>,
    favoritePresets: Array<string>,
    onClose: () => void,
    onSaved: () => void
}> = ({hass, t, draft, presets, favoritePresets, onClose, onSaved}) => {
    const hassRef = useRef(hass);
    hassRef.current = hass;
    const isAdmin = !!hass?.user?.is_admin;

    const [name, setName] = useState("");
    const [areaId, setAreaId] = useState<string | undefined>(undefined);
    const [presetId, setPresetId] = useState("");
    const [targets, setTargets] = useState<HaTargetSelectorValue>({});
    const [tun, setTun] = useState<Tunables>({...DEFAULT_TUNABLES});
    const [exclude, setExclude] = useState<Array<string>>([]);
    const [keepGroups, setKeepGroups] = useState<Array<string>>([]);
    const [optional, setOptional] = useState<Array<string>>([]);
    const [lightBrightness, setLightBrightness] = useState<{[entityId: string]: number}>({});
    const [music, setMusic] = useState<MusicSettings>({media_player: "", auto_start: "never", when_on: false});
    const [sceneLights, setSceneLights] = useState<Array<SceneLight>>([]);
    const [moreOpen, setMoreOpen] = useState(false);
    const [showLeftOut, setShowLeftOut] = useState(false);
    const [picker, setPicker] = useState(false);
    const [search, setSearch] = useState("");
    const [error, setError] = useState("");
    const [busy, setBusy] = useState(false);
    const [copied, setCopied] = useState(false);

    const open = draft !== null;
    const editing = draft?.scene;

    // take over the draft each time the editor opens
    useEffect(() => {
        if (!draft) {
            return;
        }
        setName(draft.name);
        setAreaId(draft.areaId);
        setPresetId(draft.presetId);
        setTargets(draft.targets ?? {});
        setTun({...draft.tun});
        setExclude(draft.exclude);
        setKeepGroups(draft.keepGroups);
        setOptional(draft.optional);
        setLightBrightness(draft.lightBrightness);
        setMusic({media_player: "", auto_start: "never", when_on: false, ...(draft.music ?? {})});
        setMoreOpen(false);
        setShowLeftOut(false);
        setPicker(!draft.presetId);
        setSearch("");
        setError("");
        setBusy(false);
        setCopied(false);
    }, [draft]);

    // lights of the scene (resolved by the backend with the same rules as the services)
    useEffect(() => {
        if (!open || !hasTargets(targets)) {
            setSceneLights([]);
            return;
        }
        hass.callWS({
            type: "scene_studio/resolve_targets",
            targets: targets,
            exclude: exclude,
            keep_groups: keepGroups,
            optional: optional
        }).then(result => {
            setSceneLights(result?.lights ?? []);
        }).catch(() => {
            setSceneLights([]);
        });
    }, [open, targets, exclude, keepGroups, optional]); // eslint-disable-line react-hooks/exhaustive-deps

    // close with Escape
    useEffect(() => {
        if (!open) {
            return;
        }
        const onKey = (e: KeyboardEvent) => {
            if (e.key === "Escape") {
                if (picker && presetId) {
                    setPicker(false);
                } else {
                    onClose();
                }
            }
        };
        window.addEventListener("keydown", onKey);
        return () => window.removeEventListener("keydown", onKey);
    }, [open, picker, presetId, onClose]);

    const groupCandidates = useMemo(() => {
        const inScene = new Set(sceneLights.map(l => l.entity_id));
        return Object.values<any>(hass?.states ?? {})
            .filter((st: any) => {
                const members = st?.attributes?.entity_id;
                return st.entity_id.startsWith("light.") && Array.isArray(members) && members.length > 1 &&
                    !keepGroups.includes(st.entity_id) &&
                    members.every((m: string) => inScene.has(m));
            })
            .map((st: any) => ({entity_id: st.entity_id, name: st.attributes?.friendly_name ?? st.entity_id}));
    }, [hass?.states, sceneLights, keepGroups]); // eslint-disable-line react-hooks/exhaustive-deps

    const areas = useMemo(() => {
        return Object.values<any>(hass?.areas ?? {})
            .map(a => ({id: a.area_id, name: a.name}))
            .sort((a, b) => a.name.localeCompare(b.name));
    }, [hass?.areas]);

    // speakers: those of the scene's room first
    const speakers = useMemo(() => {
        const roomOf = (entityId: string) => {
            const entry = hass?.entities?.[entityId];
            return entry?.area_id ?? hass?.devices?.[entry?.device_id]?.area_id;
        };
        return Object.values<any>(hass?.states ?? {})
            .filter((st: any) => st.entity_id.startsWith("media_player."))
            .map((st: any) => ({
                entity_id: st.entity_id,
                name: st.attributes?.friendly_name ?? st.entity_id,
                here: !!areaId && roomOf(st.entity_id) === areaId
            }))
            .sort((a, b) => Number(b.here) - Number(a.here) || a.name.localeCompare(b.name));
    }, [hass?.states, hass?.entities, hass?.devices, areaId]); // eslint-disable-line react-hooks/exhaustive-deps

    const presetMap = useMemo(() => {
        const map: {[id: string]: Preset} = {};
        presets.forEach(p => {
            map[p.id] = p;
        });
        return map;
    }, [presets]);

    const pickerPresets = useMemo(() => {
        const q = search.trim().toLowerCase();
        const visible = presets.filter(p => !p.hidden);
        const list = q ? visible.filter(p => p.name.toLowerCase().includes(q)) : visible;
        const fav = list.filter(p => favoritePresets.includes(p.id));
        return [...fav, ...list.filter(p => !favoritePresets.includes(p.id))];
    }, [presets, search, favoritePresets]);

    if (!open) {
        return null;
    }

    const set: SetTunable = (key, value) => setTun(prev => ({...prev, [key]: value}));
    const toggleIn = (list: Array<string>, setList: (v: Array<string>) => void, entityId: string) => {
        setList(list.includes(entityId) ? list.filter(e => e !== entityId) : [...list, entityId]);
    };
    const stateName = (entityId: string) => hass?.states?.[entityId]?.attributes?.friendly_name ?? entityId;

    const preset = presetMap[presetId];
    const entityId = editing ? sceneEntityId(hass, editing.id) : undefined;
    const musicOn = presetId === MUSIC_PRESET_ID;
    const canSave = !!name.trim() && !!presetId && hasTargets(targets) && !busy;

    const sceneCall = () => {
        const {service, payload} = tunablesToCall(presetId, targets, tun);
        if (exclude.length > 0) {
            payload.exclude = exclude;
        }
        if (keepGroups.length > 0) {
            payload.keep_groups = keepGroups;
        }
        if (optional.length > 0) {
            payload.optional = optional;
        }
        const perLight: {[entityId: string]: number} = {};
        Object.entries(lightBrightness).forEach(([e, value]) => {
            if (!exclude.includes(e) && typeof value === "number" && value >= 0 && value <= 100) {
                perLight[e] = Math.round(value);
            }
        });
        if (Object.keys(perLight).length > 0) {
            payload.light_brightness = perLight;
        }
        return {service, payload};
    };

    const tryOnLights = () => {
        if (!presetId || !hasTargets(targets)) {
            setError(t("need_targets"));
            return;
        }
        setError("");
        const {service, payload} = sceneCall();
        hass.callService("scene_studio", service, payload).catch(err => setError(err?.message ?? String(err)));
    };

    // the scene entity shows up shortly after saving: then put it into the chosen room
    const assignArea = async (sceneId: string) => {
        if (!isAdmin) {
            return;
        }
        for (let i = 0; i < 20; i++) {
            const id = sceneEntityId(hassRef.current, sceneId);
            if (id) {
                const current = hassRef.current?.entities?.[id]?.area_id ?? undefined;
                if (current !== areaId) {
                    await hassRef.current.callWS({type: "config/entity_registry/update", entity_id: id, area_id: areaId ?? null});
                }
                return;
            }
            await sleep(250);
        }
    };

    const save = async (asNew: boolean) => {
        if (!name.trim()) {
            setError(t("name_required"));
            return;
        }
        if (!hasTargets(targets)) {
            setError(t("need_targets"));
            return;
        }
        const {service, payload: call} = sceneCall();
        const sceneId = editing && !asNew ? editing.id : newId();
        const payload: any = {
            ...call,
            id: sceneId,
            name: name.trim(),
            dynamic: service === "start_dynamic_scene"
        };
        if (musicOn) {
            payload.music = {
                auto_start: music.auto_start ?? "never",
                when_on: music.auto_start !== "never" && !!music.when_on
            };
            if (music.media_player) {
                payload.music.media_player = music.media_player;
            }
        }
        setBusy(true);
        setError("");
        try {
            await hass.callService("scene_studio", "save_scene", payload);
            const areaChanged = !editing || asNew || areaId !== draft?.areaId;
            if (areaChanged) {
                await assignArea(sceneId).catch(() => {/* the scene is saved, only the room failed */});
            }
            onSaved();
            onClose();
        } catch (err: any) {
            setError(err?.message ?? String(err));
        } finally {
            setBusy(false);
        }
    };

    const remove = () => {
        if (!editing || !window.confirm(t("delete_confirm", {name: editing.name}))) {
            return;
        }
        hass.callService("scene_studio", "delete_saved_scene", {id: editing.id}).then(() => {
            onSaved();
            onClose();
        }).catch(err => setError(err?.message ?? String(err)));
    };

    const copyEntityId = () => {
        if (!entityId) {
            return;
        }
        const done = () => {
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        };
        if (navigator.clipboard?.writeText) {
            navigator.clipboard.writeText(entityId).then(done).catch(() => {/* shown as text anyway */});
        } else {
            const area = document.createElement("textarea");
            area.value = entityId;
            document.body.appendChild(area);
            area.select();
            try {
                document.execCommand("copy");
                done();
            } finally {
                document.body.removeChild(area);
            }
        }
    };

    const leftOut = exclude;

    return (
        <div className={"sp-overlay"} onClick={(e) => {
            if (e.target === e.currentTarget) {
                onClose();
            }
        }}>
            <div className={"sp-sheet"} role={"dialog"} aria-modal={"true"} aria-label={editing ? t("editor_edit") : t("editor_new")}>
                <div className={"sp-sheet-head"}>
                    {
                        picker && presetId ?
                            <button className={"sp-icon-btn"} aria-label={t("back")} onClick={() => setPicker(false)}>
                                <HaIcon icon={"mdi:arrow-left"} size={24}/>
                            </button> :
                            <button className={"sp-icon-btn"} aria-label={t("close")} onClick={onClose}>
                                <HaIcon icon={"mdi:close"} size={24}/>
                            </button>
                    }
                    <div className={"sp-sheet-title"}>{picker ? t("choose_preset") : (editing ? t("editor_edit") : t("editor_new"))}</div>
                    {!picker && <button className={"sp-btn text"} onClick={tryOnLights}>{t("test")}</button>}
                </div>

                {
                    picker ?
                        <div className={"sp-sheet-body"}>
                            <label className={"sp-search"}>
                                <HaIcon icon={"mdi:magnify"} size={20}/>
                                <input type={"search"} placeholder={t("search")} value={search} onChange={(e) => setSearch(e.target.value)}/>
                            </label>
                            <div className={"sp-grid small"}>
                                {pickerPresets.map(p => (
                                    <PresetTile
                                        key={"pick_" + p.id}
                                        id={p.id}
                                        name={p.name}
                                        small
                                        active={p.id === presetId}
                                        imgSrc={presetImage(p)}
                                        onClick={(id) => {
                                            setPresetId(id);
                                            setPicker(false);
                                        }}
                                    />
                                ))}
                            </div>
                            {pickerPresets.length === 0 && <div className={"sp-secondary"}>{t("no_results")}</div>}
                        </div> :
                        <div className={"sp-sheet-body"}>
                            <label className={"sp-field"}>
                                <span className={"sp-field-label"}>{t("name")}</span>
                                <input
                                    className={"sp-input save-scene-name"}
                                    type={"text"}
                                    value={name}
                                    placeholder={t("name_placeholder")}
                                    onChange={(e) => setName(e.target.value)}
                                    onKeyDown={(e) => {
                                        if (e.key === "Enter" && canSave) {
                                            save(false);
                                        }
                                    }}
                                />
                            </label>

                            <div className={"sp-field"}>
                                <span className={"sp-field-label"}>{t("room")}</span>
                                {
                                    isAdmin ?
                                        <div className={"sp-chips wrap"}>
                                            <button className={"sp-chip" + (!areaId ? " active" : "")} onClick={() => setAreaId(undefined)}>{t("room_none")}</button>
                                            {areas.map(a => (
                                                <button key={"area_" + a.id} className={"sp-chip" + (areaId === a.id ? " active" : "")} onClick={() => setAreaId(a.id)}>
                                                    {a.name}
                                                </button>
                                            ))}
                                        </div> :
                                        <div>{areaId ? areaName(hass, areaId) : t("room_none")}</div>
                                }
                            </div>

                            <div className={"sp-preset-row"}>
                                {
                                    presetImage(preset) ?
                                        <img className={"sp-preset-thumb"} src={presetImage(preset)} alt={""}/> :
                                        <span className={"sp-preset-thumb"}/>
                                }
                                <div className={"sp-grow"}>
                                    <div className={"sp-secondary sp-small"}>{t("preset")}</div>
                                    <div className={"sp-strong"}>{preset?.name ?? t("unknown_preset")}</div>
                                </div>
                                <button className={"sp-btn text save-scene-preset"} onClick={() => setPicker(true)}>{t("change")}</button>
                            </div>

                            <TargetField hass={hass} t={t} value={targets} onChange={setTargets}/>

                            {
                                musicOn &&
                                <div className={"sp-field scene-music"}>
                                    <div className={"sp-secondary sp-small"}>{t("music_help")}</div>
                                    <label className={"sp-field"}>
                                        <span className={"sp-field-label"}>{t("music_player")}</span>
                                        <select
                                            className={"sp-input scene-music-player"}
                                            value={music.media_player ?? ""}
                                            onChange={(e) => setMusic({...music, media_player: e.target.value})}
                                        >
                                            <option value={""}>{t("music_player_auto")}</option>
                                            {speakers.map(sp => (
                                                <option key={"mp_" + sp.entity_id} value={sp.entity_id}>{sp.name}</option>
                                            ))}
                                        </select>
                                    </label>
                                    <span className={"sp-field-label"}>{t("music_auto")}</span>
                                    <Segmented
                                        className={"scene-music-auto"}
                                        options={[
                                            {value: "never", label: t("music_auto_never")},
                                            {value: "follow", label: t("music_auto_follow")},
                                            {value: "always", label: t("music_auto_always")}
                                        ]}
                                        value={music.auto_start ?? "never"}
                                        onChange={(v) => setMusic({...music, auto_start: v as MusicSettings["auto_start"]})}
                                    />
                                    <div className={"sp-secondary sp-small"}>
                                        {t(music.auto_start === "follow" ? "music_auto_help_follow" : music.auto_start === "always" ? "music_auto_help_always" : "music_auto_help_never")}
                                    </div>
                                    {
                                        music.auto_start !== "never" &&
                                        <SwitchRow
                                            label={t("music_when_on")}
                                            value={!!music.when_on}
                                            onChange={(v) => setMusic({...music, when_on: v})}
                                            indent
                                            className={"scene-music-when-on"}
                                        />
                                    }
                                    <div className={"sp-secondary sp-small"}>{t("music_end_help")}</div>
                                </div>
                            }

                            <Segmented
                                options={[{value: "once", label: t("mode_once")}, {value: "dynamic", label: t("mode_dynamic")}]}
                                value={tun.dynamic ? "dynamic" : "once"}
                                onChange={(v) => set("dynamic", v === "dynamic")}
                            />

                            <BrightnessField
                                t={t}
                                enabled={tun.customBrightness}
                                value={tun.customBrightnessValue}
                                presetBri={preset?.bri}
                                onLive={(bri) => previewBrightness(
                                    hass,
                                    sceneLights.map(l => l.entity_id).filter(e => lightBrightness[e] === undefined),
                                    bri
                                )}
                                onChange={(enabled, value) => setTun(prev => ({...prev, customBrightness: enabled, customBrightnessValue: value}))}
                            />

                            <Collapsible
                                label={t("more_options")}
                                hint={tun.dynamic ? t("more_dynamic_hint") : t("more_once_hint")}
                                open={moreOpen}
                                onToggle={() => setMoreOpen(!moreOpen)}
                            >
                                <MoreOptions t={t} tun={tun} set={set}/>
                            </Collapsible>

                            {
                                (sceneLights.length > 0 || leftOut.length > 0) &&
                                <div className={"sp-field save-scene-light-brightness"}>
                                    <div className={"sp-field-head"}>
                                        <span className={"sp-strong"}>{t("lights_heading")}</span>
                                        <span className={"sp-secondary sp-small"}>{t("n_lights", {n: sceneLights.length})}</span>
                                    </div>
                                    <div className={"sp-secondary sp-small"}>{t("lights_help")}</div>
                                    <div className={"sp-list"}>
                                        {sceneLights.map(light => {
                                            const value = lightBrightness[light.entity_id];
                                            const isGroup = keepGroups.includes(light.entity_id);
                                            const isOptional = optional.includes(light.entity_id);
                                            return (
                                                <div key={"lb_" + light.entity_id} className={"sp-list-row scene-light-row"}>
                                                    <div className={"sp-list-main"}>
                                                        <span className={"sp-grow"}>
                                                            {light.name}
                                                            {isGroup && <span className={"sp-secondary sp-small"}> · {t("as_one_light")}</span>}
                                                        </span>
                                                        <span className={"sp-num small"}>
                                                            <input
                                                                type={"number"}
                                                                min={0}
                                                                max={100}
                                                                placeholder={"–"}
                                                                aria-label={t("brightness")}
                                                                value={value === undefined ? "" : value}
                                                                onChange={(e) => {
                                                                    const raw = e.target.value;
                                                                    const next = {...lightBrightness};
                                                                    if (raw === "") {
                                                                        delete next[light.entity_id];
                                                                    } else {
                                                                        next[light.entity_id] = Math.max(0, Math.min(100, Number(raw)));
                                                                    }
                                                                    setLightBrightness(next);
                                                                }}
                                                            />
                                                            <span className={"sp-unit"}>%</span>
                                                        </span>
                                                    </div>
                                                    <div className={"sp-list-actions"}>
                                                        <button
                                                            className={"sp-chip small scene-light-optional" + (isOptional ? " active" : "")}
                                                            title={t("only_if_on_help")}
                                                            aria-pressed={isOptional}
                                                            onClick={() => toggleIn(optional, setOptional, light.entity_id)}
                                                        >
                                                            {t("only_if_on")}
                                                        </button>
                                                        {
                                                            isGroup &&
                                                            <button className={"sp-chip small scene-light-split"} onClick={() => toggleIn(keepGroups, setKeepGroups, light.entity_id)}>
                                                                {t("split_group")}
                                                            </button>
                                                        }
                                                        <button
                                                            className={"sp-chip small scene-light-exclude"}
                                                            onClick={() => {
                                                                setExclude([...exclude, light.entity_id]);
                                                                setOptional(optional.filter(e => e !== light.entity_id));
                                                            }}
                                                        >
                                                            {t("leave_out")}
                                                        </button>
                                                    </div>
                                                </div>
                                            );
                                        })}
                                        {
                                            leftOut.length > 0 &&
                                            <button className={"sp-list-row sp-list-more"} onClick={() => setShowLeftOut(!showLeftOut)}>
                                                <span className={"sp-grow"}>{t("show_left_out", {n: leftOut.length})}</span>
                                                <span className={"sp-link"}>{showLeftOut ? t("hide") : t("show")}</span>
                                            </button>
                                        }
                                        {
                                            showLeftOut && leftOut.map(e => (
                                                <div key={"ex_" + e} className={"sp-list-row muted"}>
                                                    <div className={"sp-list-main"}>
                                                        <span className={"sp-grow"}>{stateName(e)}</span>
                                                        <button className={"sp-chip small scene-light-include"} onClick={() => setExclude(exclude.filter(x => x !== e))}>
                                                            {t("add_back")}
                                                        </button>
                                                    </div>
                                                </div>
                                            ))
                                        }
                                    </div>
                                    {
                                        groupCandidates.length > 0 &&
                                        <div className={"sp-field"}>
                                            <div className={"sp-strong"}>{t("groups_heading")}</div>
                                            <div className={"sp-secondary sp-small"}>{t("as_one_light_help")}</div>
                                            {groupCandidates.map(group => (
                                                <div key={"kg_" + group.entity_id} className={"sp-list-main"}>
                                                    <span className={"sp-grow"}>{group.name}</span>
                                                    <button className={"sp-chip small scene-group-keep"} onClick={() => toggleIn(keepGroups, setKeepGroups, group.entity_id)}>
                                                        {t("as_one_light")}
                                                    </button>
                                                </div>
                                            ))}
                                        </div>
                                    }
                                </div>
                            }

                            <div className={"sp-automation"}>
                                <HaIcon icon={"mdi:robot-outline"} size={20}/>
                                <div className={"sp-grow"}>
                                    <div className={"sp-secondary sp-small"}>{t("use_in_automations")}</div>
                                    {
                                        entityId ?
                                            <code className={"sp-entity-id"}>{entityId}</code> :
                                            <div className={"sp-small"}>{t("entity_after_save")}</div>
                                    }
                                </div>
                                {
                                    entityId &&
                                    <button className={"sp-btn small scene-copy-id"} onClick={copyEntityId}>{copied ? t("copied") : t("copy")}</button>
                                }
                            </div>

                            {error && <div className={"sp-error"}>{error}</div>}
                        </div>
                }

                {
                    !picker &&
                    <div className={"sp-sheet-foot"}>
                        {
                            editing &&
                            <button className={"sp-btn danger save-scene-delete"} onClick={remove}>{t("delete")}</button>
                        }
                        <span className={"sp-grow"}/>
                        {
                            editing &&
                            <button className={"sp-btn text save-scene-as-new"} disabled={!canSave} onClick={() => save(true)}>{t("save_as_new")}</button>
                        }
                        <button className={"sp-btn primary save-scene-confirm"} disabled={!canSave} onClick={() => save(false)}>{t("save")}</button>
                    </div>
                }
            </div>
        </div>
    );
};

/** Draft for a saved scene that is edited. */
export function draftFromScene(scene: SavedScene, tun: Tunables, areaId: string | undefined): SceneDraft {
    return {
        scene,
        name: scene.name,
        areaId,
        presetId: scene.preset_id,
        targets: scene.targets ?? {},
        tun,
        exclude: scene.exclude ?? [],
        keepGroups: scene.keep_groups ?? [],
        optional: scene.optional ?? [],
        lightBrightness: scene.light_brightness ?? {},
        music: scene.music
    };
}
