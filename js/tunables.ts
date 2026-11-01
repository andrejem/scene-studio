// Added by andrejem (2026): settings of a preset application (once or dynamic) and their conversion
// to the apply_preset / start_dynamic_scene service calls and from saved scenes

import {HaTargetSelectorValue} from "./components/hass/selectors/HaTargetSelector";

export const DEFAULT_TUNABLES = {
    shuffle: false,
    smartShuffle: false,
    customBrightness: false,
    customBrightnessValue: 128,
    customTransition: false,
    customTransitionValue: 60,

    dynamic: false,
    dynamicTransitionValue: 45,
    dynamicIntervalValue: 60,
    dynamicPerLight: false,
    dynamicIntervalMin: 20,
    dynamicIntervalMax: 60,
    dynamicTransitionMin: 5,
    dynamicTransitionMax: 15,
};

export type Tunables = typeof DEFAULT_TUNABLES;
export type TunableKey = keyof Tunables;
export type SetTunable = <K extends TunableKey>(key: K, value: Tunables[K]) => void;

export type SavedScene = {
    id: string,
    name: string,
    preset_id: string,
    targets: HaTargetSelectorValue,
    dynamic: boolean,
    [key: string]: any
};

export const toList = (value: any): Array<string> => {
    if (value === undefined || value === null || value === "") {
        return [];
    }
    return Array.isArray(value) ? value : [value];
};

export const hasTargets = (targets: HaTargetSelectorValue | undefined): boolean => {
    return Object.values(targets ?? {}).some((v: any) => Array.isArray(v) ? v.length > 0 : !!v);
};

/** Service and payload that apply a preset with these settings (same as the panel always did). */
export function tunablesToCall(presetId: string, targets: HaTargetSelectorValue, tun: Tunables): {service: string, payload: any} {
    let payload: any = {
        preset_id: presetId,
        targets: targets,
        brightness: tun.customBrightness ? tun.customBrightnessValue : undefined,
    };
    let service: string;

    if (tun.dynamic) {
        if (tun.dynamicPerLight) {
            payload = {
                ...payload,
                interval_min: Math.min(tun.dynamicIntervalMin, tun.dynamicIntervalMax),
                interval_max: Math.max(tun.dynamicIntervalMin, tun.dynamicIntervalMax),
                transition_min: Math.min(tun.dynamicTransitionMin, tun.dynamicTransitionMax),
                transition_max: Math.max(tun.dynamicTransitionMin, tun.dynamicTransitionMax)
            };
        } else {
            payload = {
                ...payload,
                transition: tun.dynamicTransitionValue,
                interval: tun.dynamicIntervalValue
            };
        }
        service = "start_dynamic_scene";
    } else {
        payload = {
            ...payload,
            shuffle: tun.shuffle,
            smart_shuffle: tun.smartShuffle,
            transition: tun.customTransition ? tun.customTransitionValue : undefined,
        };
        service = "apply_preset";
    }

    Object.keys(payload).forEach(k => payload[k] === undefined && delete payload[k]);
    return {service, payload};
}

/** Settings of a saved scene, for the scene editor. */
export function sceneToTunables(scene: SavedScene): Tunables {
    const tun: Tunables = {...DEFAULT_TUNABLES};
    const has = (key: string) => scene[key] !== undefined && scene[key] !== null;

    tun.customBrightness = has("brightness");
    if (has("brightness")) {
        tun.customBrightnessValue = scene.brightness;
    }
    tun.dynamic = !!scene.dynamic;
    if (scene.dynamic) {
        tun.dynamicPerLight = ["interval_min", "interval_max", "transition_min", "transition_max"].some(has);
        if (tun.dynamicPerLight) {
            tun.dynamicIntervalMin = scene.interval_min ?? DEFAULT_TUNABLES.dynamicIntervalMin;
            tun.dynamicIntervalMax = scene.interval_max ?? DEFAULT_TUNABLES.dynamicIntervalMax;
            tun.dynamicTransitionMin = scene.transition_min ?? DEFAULT_TUNABLES.dynamicTransitionMin;
            tun.dynamicTransitionMax = scene.transition_max ?? DEFAULT_TUNABLES.dynamicTransitionMax;
        } else {
            tun.dynamicIntervalValue = scene.interval ?? DEFAULT_TUNABLES.dynamicIntervalValue;
            tun.dynamicTransitionValue = scene.transition ?? DEFAULT_TUNABLES.dynamicTransitionValue;
        }
    } else {
        tun.shuffle = !!scene.shuffle;
        tun.smartShuffle = !!scene.smart_shuffle;
        tun.customTransition = has("transition");
        if (has("transition")) {
            tun.customTransitionValue = scene.transition;
        }
    }
    return tun;
}

export const toPercent = (bri: number) => Math.round(bri * 100 / 255);
export const fromPercent = (pct: number) => Math.round(pct * 255 / 100);

export function readLocalStorage<T>(key: string, fallback: T): T {
    try {
        const item = window.localStorage.getItem(key);
        return item ? JSON.parse(item) : fallback;
    } catch {
        return fallback;
    }
}

export function newId(): string {
    try {
        if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
            return crypto.randomUUID();
        }
    } catch {
        /* not available without https */
    }
    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, c => {
        const r = Math.random() * 16 | 0;
        return (c === "x" ? r : (r & 0x3 | 0x8)).toString(16);
    });
}

// ---- Home Assistant lookups ----

export function entityAreaId(hass: any, entityId: string | undefined): string | undefined {
    if (!entityId) {
        return undefined;
    }
    const entry = hass?.entities?.[entityId];
    if (!entry) {
        return undefined;
    }
    if (entry.area_id) {
        return entry.area_id;
    }
    return entry.device_id ? hass?.devices?.[entry.device_id]?.area_id ?? undefined : undefined;
}

export function sceneEntityId(hass: any, sceneId: string): string | undefined {
    for (const [entityId, state] of Object.entries<any>(hass?.states ?? {})) {
        if (entityId.startsWith("scene.") && state?.attributes?.saved_scene_id === sceneId) {
            return entityId;
        }
    }
    return undefined;
}

/** Room of a saved scene: area of its scene entity, else the one area its targets point to. */
export function sceneAreaId(hass: any, scene: SavedScene): string | undefined {
    const fromEntity = entityAreaId(hass, sceneEntityId(hass, scene.id));
    if (fromEntity) {
        return fromEntity;
    }
    return targetsAreaId(hass, scene.targets);
}

export function targetsAreaId(hass: any, targets: HaTargetSelectorValue | undefined): string | undefined {
    const areas = toList(targets?.area_id);
    if (areas.length === 1) {
        return areas[0];
    }
    if (areas.length > 1) {
        return undefined;
    }
    const entityAreas = new Set(toList(targets?.entity_id).map(e => entityAreaId(hass, e)));
    if (entityAreas.size === 1) {
        const [only] = Array.from(entityAreas);
        return only ?? undefined;
    }
    return undefined;
}

export const areaName = (hass: any, areaId: string | undefined): string => {
    if (!areaId) {
        return "";
    }
    return hass?.areas?.[areaId]?.name ?? areaId;
};

/** "Wohnzimmer Standard" shown as "Standard" below the heading "Wohnzimmer". */
export function stripRoomName(name: string, room: string): string {
    if (!room) {
        return name;
    }
    const lower = name.toLowerCase();
    const prefix = room.toLowerCase();
    if (lower.startsWith(prefix) && /^[\s\-–:·]/.test(name.slice(room.length))) {
        const rest = name.slice(room.length).replace(/^[\s\-–:·]+/, "");
        if (rest) {
            return rest;
        }
    }
    return name;
}

/** Short text for the chosen targets: "Wohnzimmer", "Küche, 2 lights" … */
export function targetSummary(hass: any, targets: HaTargetSelectorValue | undefined, nLights: (n: number) => string): string {
    const parts: Array<string> = [];
    toList((targets as any)?.floor_id).forEach(id => parts.push(hass?.floors?.[id]?.name ?? id));
    toList(targets?.area_id).forEach(id => parts.push(areaName(hass, id)));
    toList(targets?.device_id).forEach(id => {
        const dev = hass?.devices?.[id];
        parts.push(dev?.name_by_user ?? dev?.name ?? id);
    });
    toList((targets as any)?.label_id).forEach(id => parts.push(id));
    const entities = toList(targets?.entity_id);
    if (entities.length > 0 && entities.length <= 2) {
        entities.forEach(e => parts.push(hass?.states?.[e]?.attributes?.friendly_name ?? e));
    } else if (entities.length > 2) {
        parts.push(nLights(entities.length));
    }
    return parts.join(", ");
}

export const presetImage = (preset: any): string | undefined => {
    return preset?.img ? "/assets/scene_studio/" + preset.img : undefined;
};
