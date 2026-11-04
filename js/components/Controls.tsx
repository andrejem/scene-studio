// Added by andrejem (2026): small form controls of the panel (mode switch, brightness in percent,
// settings rows, number fields with unit, light picker with a short summary)

import React, {useEffect, useRef, useState} from "react";
import HaSwitch from "./hass/building_blocks/HaSwitch";
import HaIcon from "./hass/building_blocks/HaIcon";
import {HaTargetSelector, HaTargetSelectorValue} from "./hass/selectors/HaTargetSelector";
import {Translate} from "../i18n";
import {DEFAULT_TUNABLES, SetTunable, Tunables, fromPercent, hasTargets, targetSummary, toPercent} from "../tunables";

export const Segmented: React.FunctionComponent<{
    options: Array<{value: string, label: string}>,
    value: string,
    onChange: (value: string) => void,
    className?: string
}> = ({options, value, onChange, className}) => {
    return (
        <div
            className={"sp-seg " + (className ?? "")}
            role={"tablist"}
            style={options.length !== 2 ? {gridTemplateColumns: `repeat(${options.length}, minmax(0, 1fr))`} : undefined}
        >
            {options.map(o => (
                <button
                    key={o.value}
                    role={"tab"}
                    aria-selected={o.value === value}
                    className={o.value === value ? "active" : ""}
                    onClick={() => onChange(o.value)}
                >
                    {o.label}
                </button>
            ))}
        </div>
    );
};

export const SwitchRow: React.FunctionComponent<{
    label: string,
    value: boolean,
    onChange: (value: boolean) => void,
    indent?: boolean,
    className?: string
}> = ({label, value, onChange, indent, className}) => {
    return (
        <label className={"sp-option-row " + (indent ? "indent " : "") + (className ?? "")}>
            <span>{label}</span>
            <HaSwitch value={value} onValueChanged={onChange}/>
        </label>
    );
};

export const NumField: React.FunctionComponent<{
    label: string,
    value: number,
    onChange: (value: number) => void,
    min: number,
    max: number,
    unit?: string,
    indent?: boolean,
    className?: string
}> = ({label, value, onChange, min, max, unit, indent, className}) => {
    const [text, setText] = useState<string>(String(value));
    useEffect(() => {
        setText(String(value));
    }, [value]);

    const commit = (raw: string) => {
        const n = Number(raw);
        if (raw.trim() === "" || isNaN(n)) {
            setText(String(value));
            return;
        }
        const clamped = Math.max(min, Math.min(max, Math.round(n)));
        setText(String(clamped));
        if (clamped !== value) {
            onChange(clamped);
        }
    };

    return (
        <label className={"sp-option-row " + (indent ? "indent " : "") + (className ?? "")}>
            <span>{label}</span>
            <span className={"sp-num"}>
                <input
                    type={"number"}
                    inputMode={"numeric"}
                    min={min}
                    max={max}
                    value={text}
                    onChange={(e) => {
                        setText(e.target.value);
                        const n = Number(e.target.value);
                        if (e.target.value.trim() !== "" && !isNaN(n) && n >= min && n <= max) {
                            onChange(Math.round(n));
                        }
                    }}
                    onBlur={(e) => commit(e.target.value)}
                />
                {unit && <span className={"sp-unit"}>{unit}</span>}
            </span>
        </label>
    );
};

export const BrightnessField: React.FunctionComponent<{
    t: Translate,
    enabled: boolean,
    value: number,
    presetBri?: number,     // brightness of the preset (0-255), shown while "as in preset" is used
    onChange: (enabled: boolean, value: number) => void,
    onLive?: (bri: number) => void   // live preview on the lights while dragging (0-255)
}> = ({t, enabled, value, presetBri, onChange, onLive}) => {
    // at most every 250 ms while dragging, the last value always
    const lastSent = useRef(0);
    const pending = useRef<ReturnType<typeof setTimeout> | null>(null);
    useEffect(() => () => {
        if (pending.current) clearTimeout(pending.current);
    }, []);
    const live = (bri: number) => {
        if (!onLive) {
            return;
        }
        if (pending.current) {
            clearTimeout(pending.current);
            pending.current = null;
        }
        const wait = 250 - (Date.now() - lastSent.current);
        if (wait <= 0) {
            lastSent.current = Date.now();
            onLive(bri);
        } else {
            pending.current = setTimeout(() => {
                lastSent.current = Date.now();
                pending.current = null;
                onLive(bri);
            }, wait);
        }
    };
    const known = presetBri !== undefined && presetBri !== null;
    const pct = toPercent(enabled ? value : (known ? presetBri as number : 255));
    const presetPct = known ? toPercent(presetBri as number) : undefined;
    return (
        <div className={"sp-field sp-brightness"}>
            <div className={"sp-field-head"}>
                <span>{t("brightness")}</span>
                <span className={"sp-secondary"}>
                    {(enabled || known) && <span className={"sp-strong sp-text"}>{pct} %</span>}
                    {
                        enabled ?
                            <button className={"sp-link brightness-reset"} onClick={() => {
                                onChange(false, value);
                                if (known) live(presetBri as number);
                            }}>
                                {known ? t("back_to_preset_pct", {pct: presetPct ?? ""}) : t("back_to_preset")}
                            </button> :
                            <span>{known ? " · " : ""}{t("as_preset")}</span>
                    }
                </span>
            </div>
            <input
                type={"range"}
                className={"sp-range" + (enabled || known ? "" : " off")}
                min={1}
                max={100}
                step={1}
                value={Math.max(1, pct)}
                aria-label={t("brightness")}
                onChange={(e) => {
                    const bri = fromPercent(Number(e.target.value));
                    onChange(true, bri);
                    live(bri);
                }}
            />
        </div>
    );
};

/** Color intensity: -100 paler (towards white) .. 0 as in the preset .. 100 vivid. */
export const SaturationField: React.FunctionComponent<{
    t: Translate,
    value: number,
    onChange: (value: number) => void
}> = ({t, value, onChange}) => {
    const v = Math.round(value || 0);
    return (
        <div className={"sp-field sp-saturation"}>
            <div className={"sp-field-head"}>
                <span>{t("color_intensity")}</span>
                <span className={"sp-secondary"}>
                    {
                        v !== 0 ?
                            <>
                                <span className={"sp-strong sp-text"}>{v > 0 ? "+" : ""}{v} %</span>
                                <button className={"sp-link saturation-reset"} onClick={() => onChange(0)}>{t("back_to_preset")}</button>
                            </> :
                            <span>{t("as_preset")}</span>
                    }
                </span>
            </div>
            <input
                type={"range"}
                className={"sp-range" + (v !== 0 ? "" : " off")}
                min={-100}
                max={100}
                step={5}
                value={v}
                aria-label={t("color_intensity")}
                onChange={(e) => onChange(Number(e.target.value))}
                style={{background: "linear-gradient(90deg, #ddd, #c9a 50%, #f06)"}}
            />
            <div className={"sp-secondary sp-small"} style={{display: "flex", justifyContent: "space-between"}}>
                <span>{t("saturation_pale")}</span><span>{t("saturation_vivid")}</span>
            </div>
        </div>
    );
};

/** Shuffle / transition (once) or interval / transition (dynamic). */
export const MoreOptions: React.FunctionComponent<{
    t: Translate,
    tun: Tunables,
    set: SetTunable,
    onReset?: () => void
}> = ({t, tun, set, onReset}) => {
    const s = t("unit_s");
    return (
        <div className={"sp-options"}>
            {
                !tun.dynamic &&
                <>
                    <SwitchRow label={t("shuffle")} value={tun.shuffle} onChange={v => set("shuffle", v)} className={"opt-shuffle"}/>
                    {
                        tun.shuffle &&
                        <SwitchRow indent label={t("smart_shuffle")} value={tun.smartShuffle} onChange={v => set("smartShuffle", v)}/>
                    }
                    <SwitchRow label={t("custom_transition")} value={tun.customTransition} onChange={v => set("customTransition", v)}/>
                    {
                        tun.customTransition &&
                        <NumField indent label={t("duration")} value={tun.customTransitionValue} onChange={v => set("customTransitionValue", v)} min={0} max={300} unit={s}/>
                    }
                </>
            }
            {
                tun.dynamic &&
                <>
                    <SwitchRow label={t("per_light_timing")} value={tun.dynamicPerLight} onChange={v => set("dynamicPerLight", v)}/>
                    {
                        tun.dynamicPerLight ?
                            <>
                                <NumField label={t("interval_min")} value={tun.dynamicIntervalMin} onChange={v => set("dynamicIntervalMin", v)} min={1} max={600} unit={s}/>
                                <NumField label={t("interval_max")} value={tun.dynamicIntervalMax} onChange={v => set("dynamicIntervalMax", v)} min={1} max={600} unit={s}/>
                                <NumField label={t("transition_min")} value={tun.dynamicTransitionMin} onChange={v => set("dynamicTransitionMin", v)} min={0} max={300} unit={s}/>
                                <NumField label={t("transition_max")} value={tun.dynamicTransitionMax} onChange={v => set("dynamicTransitionMax", v)} min={0} max={300} unit={s}/>
                            </> :
                            <>
                                <NumField label={t("interval")} value={tun.dynamicIntervalValue} onChange={v => set("dynamicIntervalValue", v)} min={0} max={300} unit={s}/>
                                <NumField label={t("transition")} value={tun.dynamicTransitionValue} onChange={v => set("dynamicTransitionValue", v)} min={0} max={300} unit={s}/>
                            </>
                    }
                </>
            }
            {
                onReset &&
                <div className={"sp-options-foot"}>
                    <button className={"sp-link"} onClick={onReset}>{t("reset")}</button>
                </div>
            }
        </div>
    );
};

/** Collapsible "more options" with a one-line hint of what is inside. */
export const Collapsible: React.FunctionComponent<{
    label: string,
    hint?: string,
    open: boolean,
    onToggle: () => void,
    children?: React.ReactNode,
    className?: string
}> = ({label, hint, open, onToggle, children, className}) => {
    return (
        <div className={"sp-collapsible " + (open ? "open " : "") + (className ?? "")}>
            <button className={"sp-collapsible-head"} onClick={onToggle} aria-expanded={open}>
                <span>
                    {label}
                    {hint && !open && <span className={"sp-secondary"}> · {hint}</span>}
                </span>
                <HaIcon icon={open ? "mdi:chevron-up" : "mdi:chevron-down"} size={20}/>
            </button>
            {open && children}
        </div>
    );
};

/** "Apply to: Wohnzimmer" – opens the Home Assistant target picker. */
export const TargetField: React.FunctionComponent<{
    hass: any,
    t: Translate,
    value: HaTargetSelectorValue,
    onChange: (value: HaTargetSelectorValue) => void,
    label?: string,
    defaultOpen?: boolean
}> = ({hass, t, value, onChange, label, defaultOpen}) => {
    const any = hasTargets(value);
    // opens by itself while no lights are chosen, until it is opened or closed by hand
    const [openByHand, setOpen] = useState<boolean | null>(null);
    const open = openByHand ?? (!!defaultOpen || !any);
    const summary = any ? targetSummary(hass, value, n => t("n_lights", {n})) : t("choose_lights");

    return (
        <div className={"sp-target " + (open ? "open" : "")}>
            <button className={"sp-target-head"} onClick={() => setOpen(!open)} aria-expanded={open}>
                <span className={"sp-target-icon"}><HaIcon icon={"mdi:lightbulb-group-outline"} size={22}/></span>
                <span className={"sp-target-text"}>
                    <span className={"sp-secondary sp-small"}>{label ?? t("apply_to")}</span>
                    <span className={"sp-target-summary" + (any ? "" : " empty")}>{summary}</span>
                </span>
                <HaIcon icon={open ? "mdi:chevron-up" : "mdi:chevron-down"} size={20}/>
            </button>
            {
                open &&
                <div className={"sp-target-picker"}>
                    <HaTargetSelector
                        hass={hass}
                        selector={{"target": {"entity": {"domain": ["light", "group"]}}}}
                        value={value}
                        onValueChanged={(v) => onChange(v)}
                    />
                    {
                        any &&
                        <div className={"sp-options-foot"}>
                            <button className={"sp-link"} onClick={() => onChange({})}>{t("clear")}</button>
                        </div>
                    }
                </div>
            }
        </div>
    );
};

export const resetTunables = (set: SetTunable) => {
    (Object.keys(DEFAULT_TUNABLES) as Array<keyof Tunables>).forEach(k => set(k, DEFAULT_TUNABLES[k]));
};

/**
 * Live brightness preview: sets the brightness of the lights that are on right now (colors stay).
 * Lights that are off are not turned on.
 */
export async function previewBrightness(hass: any, lightIds: Array<string>, bri: number): Promise<void> {
    const on = lightIds.filter(e => hass?.states?.[e]?.state === "on");
    if (on.length === 0) {
        return;
    }
    await hass.callService("light", "turn_on", {entity_id: on, brightness: Math.max(1, Math.round(bri)), transition: 0.3});
}

/** Lights of these targets (same rules as the services), cached per targets. */
export function useTargetLights(hass: any, targets: HaTargetSelectorValue, extra: {exclude?: Array<string>, keep_groups?: Array<string>} = {}): Array<string> {
    const [lights, setLights] = useState<Array<string>>([]);
    const key = JSON.stringify([targets, extra.exclude ?? [], extra.keep_groups ?? []]);
    useEffect(() => {
        if (!hasTargets(targets)) {
            setLights([]);
            return;
        }
        hass.callWS({type: "scene_studio/resolve_targets", targets, exclude: extra.exclude ?? [], keep_groups: extra.keep_groups ?? []})
            .then((r: any) => setLights((r?.lights ?? []).map((l: any) => l.entity_id)))
            .catch(() => setLights([]));
    }, [key]); // eslint-disable-line react-hooks/exhaustive-deps
    return lights;
}
