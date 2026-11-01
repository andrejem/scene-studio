// Modified by andrejem (2026): per-light timing controls, saved scenes, English and German texts,
// presets from photos (PhotoPresetDialog). Reworked into the "Presets" tab: lights to apply to with a
// short summary, once / dynamic, brightness in percent, further options folded away, search and
// category chips. Saved scenes and the scene editor moved to their own components; the former
// "last action" dialog was replaced by the scene entity id in the scene editor.

import React, {useEffect, useMemo, useRef, useState} from "react";
import {PresetTile} from "../components/PresetTile";
import {useLocalStorage} from "../hooks/useLocalStorage";
import {HaTargetSelectorValue} from "../components/hass/selectors/HaTargetSelector";
import HaIcon from "../components/hass/building_blocks/HaIcon";
import {Category, Preset} from "../types";
import {Translate} from "../i18n";
import {PhotoPresetDialog} from "../components/PhotoPresetDialog";
import {BrightnessField, Collapsible, MoreOptions, Segmented, TargetField, previewBrightness, resetTunables, useTargetLights} from "../components/Controls";
import {DEFAULT_TUNABLES, SetTunable, Tunables, hasTargets, presetImage, targetSummary, tunablesToCall} from "../tunables";

export const PresetApplyPage: React.FunctionComponent<{
    hass: any,
    t: Translate,
    categories: Array<Category>,
    presets: Array<Preset>,
    onPresetsChanged?: () => void,
    onApplied?: () => void,
    onSaveAsScene: (presetId: string, targets: HaTargetSelectorValue, tun: Tunables) => void,
}> = ({
    hass,
    t,
    categories,
    presets,
    onPresetsChanged,
    onApplied,
    onSaveAsScene
}): React.JSX.Element => {
    const [targets, setTargets] = useLocalStorage<HaTargetSelectorValue>("scene_studio_apply_page_targets", {});

    // same storage keys as before, so the settings people chose stay
    const [shuffle, setShuffle] = useLocalStorage<boolean>("scene_studio_apply_page_shuffle", DEFAULT_TUNABLES.shuffle);
    const [smartShuffle, setSmartShuffle] = useLocalStorage<boolean>("scene_studio_apply_page_smart_shuffle", DEFAULT_TUNABLES.smartShuffle);
    const [customBrightness, setCustomBrightness] = useLocalStorage<boolean>("scene_studio_apply_page_custom_brightness", DEFAULT_TUNABLES.customBrightness);
    const [customBrightnessValue, setCustomBrightnessValue] = useLocalStorage<number>("scene_studio_apply_page_custom_brightness_value", DEFAULT_TUNABLES.customBrightnessValue);
    const [customTransition, setCustomTransition] = useLocalStorage<boolean>("scene_studio_apply_page_custom_transition", DEFAULT_TUNABLES.customTransition);
    const [customTransitionValue, setCustomTransitionValue] = useLocalStorage<number>("scene_studio_apply_page_custom_transition_value", DEFAULT_TUNABLES.customTransitionValue);
    const [dynamic, setDynamic] = useLocalStorage<boolean>("scene_studio_apply_page_dynamic", DEFAULT_TUNABLES.dynamic);
    const [dynamicTransitionValue, setDynamicTransitionValue] = useLocalStorage<number>("scene_studio_apply_page_dynamic_transition_value", DEFAULT_TUNABLES.dynamicTransitionValue);
    const [dynamicIntervalValue, setDynamicIntervalValue] = useLocalStorage<number>("scene_studio_apply_page_dynamic_interval_value", DEFAULT_TUNABLES.dynamicIntervalValue);
    const [dynamicPerLight, setDynamicPerLight] = useLocalStorage<boolean>("scene_studio_apply_page_dynamic_per_light", DEFAULT_TUNABLES.dynamicPerLight);
    const [dynamicIntervalMin, setDynamicIntervalMin] = useLocalStorage<number>("scene_studio_apply_page_dynamic_interval_min", DEFAULT_TUNABLES.dynamicIntervalMin);
    const [dynamicIntervalMax, setDynamicIntervalMax] = useLocalStorage<number>("scene_studio_apply_page_dynamic_interval_max", DEFAULT_TUNABLES.dynamicIntervalMax);
    const [dynamicTransitionMin, setDynamicTransitionMin] = useLocalStorage<number>("scene_studio_apply_page_dynamic_transition_min", DEFAULT_TUNABLES.dynamicTransitionMin);
    const [dynamicTransitionMax, setDynamicTransitionMax] = useLocalStorage<number>("scene_studio_apply_page_dynamic_transition_max", DEFAULT_TUNABLES.dynamicTransitionMax);

    const [favoritePresets, setFavoritePresets] = useLocalStorage<Array<string>>("scene_studio_apply_page_favorite_presets", []);
    const [lastPresetId, setLastPresetId] = useLocalStorage<string>("scene_studio_last_preset", "");
    const [category, setCategory] = useLocalStorage<string>("scene_studio_category", "all");
    const [moreOpen, setMoreOpen] = useLocalStorage<boolean>("scene_studio_more_open", false);
    const [search, setSearch] = useState("");
    const [notice, setNotice] = useState("");
    // feedback after tapping a preset: row on top of the card, outlined tile, short message at the bottom
    const [applied, setApplied] = useState<{id: string, at: number, dynamic: boolean} | null>(null);
    useEffect(() => {
        if (!applied) {
            return;
        }
        const timer = setTimeout(() => setApplied(null), 3000);
        return () => clearTimeout(timer);
    }, [applied]);
    const noticeRef = useRef<HTMLDivElement>(null);
    useEffect(() => {
        if (notice) {
            noticeRef.current?.scrollIntoView({behavior: "smooth", block: "center"});
        }
    }, [notice]);

    const [photoDialogOpen, setPhotoDialogOpen] = useState<boolean>(false);
    const [photoPresetId, setPhotoPresetId] = useState<string | null>(null);
    const isAdmin = !!hass?.user?.is_admin;
    const targetLights = useTargetLights(hass, targets);

    const tun: Tunables = {
        shuffle, smartShuffle, customBrightness, customBrightnessValue, customTransition, customTransitionValue,
        dynamic, dynamicTransitionValue, dynamicIntervalValue, dynamicPerLight,
        dynamicIntervalMin, dynamicIntervalMax, dynamicTransitionMin, dynamicTransitionMax
    };
    const setters: {[K in keyof Tunables]: (v: any) => void} = {
        shuffle: setShuffle, smartShuffle: setSmartShuffle,
        customBrightness: setCustomBrightness, customBrightnessValue: setCustomBrightnessValue,
        customTransition: setCustomTransition, customTransitionValue: setCustomTransitionValue,
        dynamic: setDynamic, dynamicTransitionValue: setDynamicTransitionValue, dynamicIntervalValue: setDynamicIntervalValue,
        dynamicPerLight: setDynamicPerLight, dynamicIntervalMin: setDynamicIntervalMin, dynamicIntervalMax: setDynamicIntervalMax,
        dynamicTransitionMin: setDynamicTransitionMin, dynamicTransitionMax: setDynamicTransitionMax
    };
    const set: SetTunable = (key, value) => setters[key](value);

    const handlePresetTap = (id: string) => {
        if (!hasTargets(targets)) {
            setNotice(t("need_targets"));
            return;
        }
        setNotice("");
        setLastPresetId(id);
        setApplied({id, at: Date.now(), dynamic: tun.dynamic});
        const {service, payload} = tunablesToCall(id, targets, tun);
        hass.callService("scene_studio", service, payload).finally(() => {
            onApplied?.();
        });
    };

    const toggleFavorite = (id: string) => {
        setFavoritePresets(favoritePresets.includes(id) ? favoritePresets.filter(e => e !== id) : [...favoritePresets, id]);
    };

    const sections: Array<{key: string, name: string, presets: Array<Preset>}> = useMemo(() => {
        const q = search.trim().toLowerCase();
        const visible = presets.filter(p => !p.hidden);
        if (q) {
            return [{key: "search", name: "", presets: visible.filter(p => p.name.toLowerCase().includes(q))}];
        }
        const favorites = presets.filter(p => favoritePresets.includes(p.id));
        const all = [
            ...(favorites.length > 0 ? [{key: "favorites", name: t("favorites"), presets: favorites}] : []),
            ...categories.map(c => ({key: c.id, name: c.name, presets: visible.filter(p => p.categoryId === c.id)}))
                .filter(s => s.presets.length > 0)
        ];
        if (category === "all" || !all.some(s => s.key === category)) {
            return all;
        }
        return all.filter(s => s.key === category);
    }, [search, presets, favoritePresets, categories, category, t]);

    const chips = useMemo(() => {
        const list = [{key: "all", name: t("all")}];
        if (favoritePresets.length > 0) {
            list.push({key: "favorites", name: t("favorites")});
        }
        categories.forEach(c => {
            if (presets.some(p => p.categoryId === c.id && !p.hidden)) {
                list.push({key: c.id, name: c.name});
            }
        });
        return list;
    }, [categories, presets, favoritePresets, t]);
    const activeChip = chips.some(c => c.key === category) ? category : "all";

    const tile = (preset: Preset, sectionKey: string) => (
        <PresetTile
            key={sectionKey + "_" + preset.id}
            id={preset.id}
            name={preset.name}
            small
            active={preset.id === lastPresetId}
            imgSrc={presetImage(preset)}
            onClick={(id) => handlePresetTap(id)}
            isFav={favoritePresets.includes(preset.id)}
            onFavClick={(id) => toggleFavorite(id)}
            actionIcon={isAdmin && ((preset as any).custom || (preset as any).overridden) ? "mdi:pencil" : undefined}
            actionLabel={t("edit")}
            onActionClick={isAdmin ? (id) => {
                setPhotoPresetId(id);
                setPhotoDialogOpen(true);
            } : undefined}
        />
    );

    const lastPreset = presets.find(p => p.id === lastPresetId);
    const appliedPreset = applied ? presets.find(p => p.id === applied.id) : undefined;

    const defaultPreset = lastPresetId && presets.some(p => p.id === lastPresetId) ? lastPresetId : (favoritePresets[0] ?? presets[0]?.id ?? "");

    return (
        <div className={"sp-presets"}>
            <div className={"sp-card sp-apply-card"}>
                <div className={"sp-current" + (applied ? " flash" : "")} key={"current_" + (applied?.at ?? 0)}>
                    {
                        presetImage(lastPreset) ?
                            <img className={"sp-current-thumb"} src={presetImage(lastPreset)} alt={""}/> :
                            <span className={"sp-current-thumb empty"}/>
                    }
                    <span className={"sp-grow"}>
                        <span className={"sp-secondary sp-small sp-block"}>{t("preset")}</span>
                        <span className={"sp-strong sp-block"}>{lastPreset ? lastPreset.name : t("tap_a_preset")}</span>
                    </span>
                    {applied && <span className={"sp-applied"}>✓ {t(applied.dynamic ? "started" : "applied")}</span>}
                </div>

                <TargetField hass={hass} t={t} value={targets} onChange={(v) => {
                    setTargets(v);
                    setNotice("");
                }}/>

                <Segmented
                    options={[{value: "once", label: t("mode_once")}, {value: "dynamic", label: t("mode_dynamic")}]}
                    value={dynamic ? "dynamic" : "once"}
                    onChange={(v) => setDynamic(v === "dynamic")}
                />

                <BrightnessField
                    t={t}
                    enabled={customBrightness}
                    value={customBrightnessValue}
                    presetBri={lastPreset?.bri}
                    onLive={(bri) => previewBrightness(hass, targetLights, bri)}
                    onChange={(enabled, value) => {
                        setCustomBrightness(enabled);
                        setCustomBrightnessValue(value);
                    }}
                />

                <Collapsible
                    label={t("more_options")}
                    hint={dynamic ? t("more_dynamic_hint") : t("more_once_hint")}
                    open={moreOpen}
                    onToggle={() => setMoreOpen(!moreOpen)}
                >
                    <MoreOptions t={t} tun={tun} set={set} onReset={() => resetTunables(set)}/>
                </Collapsible>

                <div className={"sp-actions"}>
                    <button
                        className={"sp-btn save-as-scene"}
                        onClick={() => onSaveAsScene(defaultPreset, targets, tun)}
                    >
                        <HaIcon icon={"mdi:content-save-outline"} size={18}/> {t("save_as_scene")}
                    </button>
                    {
                        isAdmin &&
                        <button
                            className={"sp-btn new-from-photo"}
                            onClick={() => {
                                setPhotoPresetId(null);
                                setPhotoDialogOpen(true);
                            }}
                        >
                            <HaIcon icon={"mdi:image-plus"} size={18}/> {t("from_photo")}
                        </button>
                    }
                </div>
            </div>

            {notice && <div className={"sp-notice"} ref={noticeRef} role={"alert"}>{notice}</div>}

            <label className={"sp-search"}>
                <HaIcon icon={"mdi:magnify"} size={20}/>
                <input type={"search"} placeholder={t("search")} value={search} onChange={(e) => setSearch(e.target.value)}/>
            </label>

            {
                !search.trim() &&
                <div className={"sp-chips"}>
                    {chips.map(c => (
                        <button key={"cat_" + c.key} className={"sp-chip" + (activeChip === c.key ? " active" : "")} onClick={() => setCategory(c.key)}>
                            {c.name}
                        </button>
                    ))}
                </div>
            }

            <div className={"sp-secondary sp-small sp-hint"}>{t("tap_hint")}</div>

            {sections.map(s => (
                <section key={"sec_" + s.key} className={"sp-group"}>
                    {s.name && <div className={"sp-section-head"}><h3>{s.name}</h3></div>}
                    <div className={"sp-grid small"}>
                        {s.presets.map(p => tile(p, s.key))}
                    </div>
                    {s.presets.length === 0 && <div className={"sp-secondary"}>{t("no_results")}</div>}
                </section>
            ))}

            {
                applied && appliedPreset &&
                <div className={"sp-toast"} role={"status"} key={"toast_" + applied.at}>
                    {t(applied.dynamic ? "toast_started" : "toast_applied", {
                        name: appliedPreset.name,
                        targets: targetSummary(hass, targets, n => t("n_lights", {n}))
                    })}
                </div>
            }

            <PhotoPresetDialog
                hass={hass}
                t={t}
                open={photoDialogOpen}
                presetId={photoPresetId}
                categories={categories}
                presets={presets}
                targets={targets}
                onSelectPreset={(id) => setPhotoPresetId(id)}
                onClose={() => setPhotoDialogOpen(false)}
                onChanged={() => onPresetsChanged?.()}
            />
        </div>
    );
};
