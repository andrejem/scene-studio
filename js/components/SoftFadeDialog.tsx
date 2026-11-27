// Added by andrejem (2026): soft fade (3.8). The lights Scene Studio fades itself, set once for all scenes:
// a switch per light and its steps per second (3.10: a slider 1-20, before three levels), the smoothness
// (how fine one step may be) once for all lights. Lights that report no transition of their own come
// first; the others may still jump to a new color (e.g. Govee), only a look at the lamp tells.
import React, {useEffect, useMemo, useRef, useState} from "react";
import {Translate} from "../i18n";
import {areaName, entityAreaId} from "../tunables";
import HaIcon from "./hass/building_blocks/HaIcon";
import HaSwitch from "./hass/building_blocks/HaSwitch";

const SMOOTHNESS: Array<{key: string, label: "soft_fade_coarse" | "soft_fade_normal" | "soft_fade_fine"}> = [
    {key: "coarse", label: "soft_fade_coarse"},
    {key: "normal", label: "soft_fade_normal"},
    {key: "fine", label: "soft_fade_fine"}
];
const MIN_RATE = 1;
const MAX_RATE = 20;
const DEFAULT_RATE = 2;
const COLOR_MODES = ["xy", "hs", "rgb", "rgbw", "rgbww", "color_temp"];
const TRANSITION = 32; // LightEntityFeature.TRANSITION
const SEGMENT = /_segment_\d+$/;

type Row = {entity_id: string, name: string, area: string, native: boolean};

export const SoftFadeDialog: React.FunctionComponent<{
    hass: any,
    t: Translate,
    onClose: () => void
}> = ({hass, t, onClose}) => {
    const [levels, setLevels] = useState<{[entityId: string]: number}>({});
    const [smoothness, setSmoothness] = useState("normal");
    const timers = useRef<{[entityId: string]: any}>({});
    const [search, setSearch] = useState("");
    const [error, setError] = useState("");

    useEffect(() => {
        hass.callWS({type: "scene_studio/get_soft_fade"}).then(r => {
            setLevels(r?.lights ?? {});
            setSmoothness(r?.smoothness ?? "normal");
        }).catch(err => setError(err?.message ?? String(err)));
        const onKey = (e: KeyboardEvent) => {
            if (e.key === "Escape") {
                e.stopPropagation();
                onClose();
            }
        };
        window.addEventListener("keydown", onKey, true);
        return () => window.removeEventListener("keydown", onKey, true);
    }, []); // eslint-disable-line react-hooks/exhaustive-deps

    // color lights, without groups (their members are faded one by one) and segment lights of a strip
    const rows: Array<Row> = useMemo(() => Object.values(hass?.states ?? {})
        .filter((s: any) => s.entity_id.startsWith("light.") && !s.attributes?.entity_id && !SEGMENT.test(s.entity_id)
            && (s.attributes?.supported_color_modes ?? []).some((m: string) => COLOR_MODES.includes(m)))
        .map((s: any) => ({
            entity_id: s.entity_id,
            name: s.attributes?.friendly_name ?? s.entity_id,
            area: areaName(hass, entityAreaId(hass, s.entity_id)) || "",
            native: ((s.attributes?.supported_features ?? 0) & TRANSITION) !== 0
        })), [hass?.states]); // eslint-disable-line react-hooks/exhaustive-deps

    const query = search.trim().toLowerCase();
    const shown = rows
        .filter(r => !query || r.name.toLowerCase().includes(query) || r.area.toLowerCase().includes(query) || r.entity_id.includes(query))
        .sort((a, b) => (Number(!!levels[b.entity_id]) - Number(!!levels[a.entity_id]))
            || (Number(a.native) - Number(b.native))
            || a.area.localeCompare(b.area) || a.name.localeCompare(b.name));

    /** Steps per second of a light (null: not faded). The slider saves once it rests for a moment. */
    const set = (entityId: string, rate: number | null, wait = 0) => {
        setLevels(prev => {
            const next = {...prev};
            if (rate) {
                next[entityId] = rate;
            } else {
                delete next[entityId];
            }
            return next;
        });
        clearTimeout(timers.current[entityId]);
        timers.current[entityId] = setTimeout(() => {
            hass.callWS({type: "scene_studio/set_soft_fade", entity_id: entityId, rate}).then(r => {
                setLevels(r?.lights ?? {});
                setError("");
            }).catch(err => setError(err?.message ?? String(err)));
        }, wait);
    };

    const changeSmoothness = (value: string) => {
        const before = smoothness;
        setSmoothness(value);
        hass.callWS({type: "scene_studio/set_soft_fade_smoothness", smoothness: value}).then(() => setError("")).catch(err => {
            setSmoothness(before);
            setError(err?.message ?? String(err));
        });
    };

    return (
        <div className={"sp-overlay"} onClick={(e) => {
            if (e.target === e.currentTarget) {
                onClose();
            }
        }}>
            <div className={"sp-sheet sp-soft-fade"} role={"dialog"} aria-modal={"true"} aria-label={t("soft_fade")}>
                <div className={"sp-sheet-head"}>
                    <button className={"sp-icon-btn"} aria-label={t("close")} onClick={onClose}>
                        <HaIcon icon={"mdi:close"} size={24}/>
                    </button>
                    <div className={"sp-sheet-title"}>{t("soft_fade")}</div>
                </div>
                <div className={"sp-sheet-body"}>
                    <div className={"sp-secondary sp-small"}>{t("soft_fade_help")}</div>
                    <div className={"sp-option-row soft-fade-smoothness"}>
                        <span>{t("soft_fade_smoothness")}</span>
                        <span className={"sp-chips"} role={"radiogroup"} aria-label={t("soft_fade_smoothness")}>
                            {SMOOTHNESS.map(l => (
                                <button
                                    key={l.key}
                                    type={"button"}
                                    role={"radio"}
                                    aria-checked={smoothness === l.key}
                                    className={"sp-chip small soft-fade-smooth-" + l.key + (smoothness === l.key ? " active" : "")}
                                    onClick={() => changeSmoothness(l.key)}
                                >
                                    {t(l.label)}
                                </button>
                            ))}
                        </span>
                    </div>
                    <label className={"sp-search"}>
                        <HaIcon icon={"mdi:magnify"} size={20}/>
                        <input type={"search"} placeholder={t("soft_fade_search")} value={search} onChange={(e) => setSearch(e.target.value)}/>
                    </label>
                    <div className={"sp-list"}>
                        {shown.map(r => {
                            const level = levels[r.entity_id];
                            return (
                                <div key={r.entity_id} className={"sp-list-row soft-fade-row"}>
                                    <div className={"sp-list-main"}>
                                        <span className={"sp-grow"}>
                                            {r.name}
                                            <span className={"sp-secondary sp-small"}>
                                                {r.area ? " · " + r.area : ""}{r.native ? "" : " · " + t("soft_fade_no_transition")}
                                            </span>
                                        </span>
                                        {
                                            level &&
                                            <span className={"soft-fade-levels"}>
                                                <input
                                                    type={"range"}
                                                    className={"sp-range soft-fade-rate"}
                                                    min={MIN_RATE}
                                                    max={MAX_RATE}
                                                    step={1}
                                                    value={level}
                                                    aria-label={t("soft_fade_level")}
                                                    onChange={(e) => set(r.entity_id, Number(e.target.value), 500)}
                                                />
                                                <span className={"soft-fade-rate-value"}>{t("soft_fade_rate", {count: level})}</span>
                                            </span>
                                        }
                                        <span className={"soft-fade-switch"}>
                                            <HaSwitch value={!!level} onValueChanged={(on) => set(r.entity_id, on ? (level ?? DEFAULT_RATE) : null)}/>
                                        </span>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                    {error && <div className={"sp-error"}>{error}</div>}
                </div>
            </div>
        </div>
    );
};
