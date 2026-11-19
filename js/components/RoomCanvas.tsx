// Added by andrejem (2026): room canvas (4.0). The lights of a scene on the plan of their room, over the
// picture of the preset. The places belong to the room (room plans in the backend), so every scene of
// the room uses them; they are saved when a light is dropped.
import React, {useEffect, useRef, useState} from "react";
import {Translate} from "../i18n";
import {areaName, entityAreaId} from "../tunables";

export type Place = {x: number, y: number, x2?: number, y2?: number};
type Plan = {
    key: string, id?: string, name: string, area_id?: string, lights: {[entityId: string]: Place},
    /** width / height of the plan (default landscape) and an own floor plan as background (JPEG data URL) */
    aspect?: number, image?: string | null
};
type CanvasLight = {entity_id: string, name: string};

const DIRECTIONS = [0, 45, 90, 135, 180, 225, 270, 315];
const DEFAULT_ASPECT = 1.6;
const FORMATS: Array<{aspect: number, icon: string, label: "spatial_landscape" | "spatial_square" | "spatial_portrait"}> = [
    {aspect: 1.6, icon: "mdi:crop-landscape", label: "spatial_landscape"},
    {aspect: 1, icon: "mdi:crop-square", label: "spatial_square"},
    {aspect: 0.625, icon: "mdi:crop-portrait", label: "spatial_portrait"}
];

/** An own floor plan: made small enough to be kept with the plan. */
const readFloorPlan = async (file: File): Promise<{image: string, aspect: number}> => {
    const bitmap = await createImageBitmap(file);
    const scale = Math.min(1, 1000 / Math.max(bitmap.width, bitmap.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(bitmap.width * scale));
    canvas.height = Math.max(1, Math.round(bitmap.height * scale));
    const ctx = canvas.getContext("2d")!;
    ctx.fillStyle = "#fff"; // transparent drawings on white
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    return {
        image: canvas.toDataURL("image/jpeg", 0.8),
        aspect: Math.max(0.4, Math.min(2.5, canvas.width / canvas.height))
    };
};
const clamp = (v: number) => Math.round(Math.max(0, Math.min(1, v)) * 1000) / 1000;
const pct = (v: number) => (v * 100) + "%";

export const RoomCanvas: React.FunctionComponent<{
    hass: any,
    t: Translate,
    lights: Array<CanvasLight>,
    areaId?: string,
    image?: string,
    /** dynamic scenes move the picture: show and choose the direction */
    moving: boolean,
    direction: number,
    onDirection: (direction: number) => void,
    /** in a scene: only shows the plan of the room; the plan itself is edited in the room plan dialog */
    preview?: boolean,
    onOpenPlan?: () => void,
    /** changes when the plans were edited elsewhere: load them again */
    version?: number
}> = ({hass, t, lights, areaId, image, moving, direction, onDirection, preview, onOpenPlan, version}) => {
    const canEdit = !!hass?.user?.is_admin && !preview;
    const [plans, setPlansState] = useState<Array<Plan>>([]);
    const plansRef = useRef<Array<Plan>>([]);
    const [selected, setSelected] = useState<string | null>(null);
    const [error, setError] = useState("");
    const box = useRef<HTMLDivElement>(null);
    const drag = useRef<{entity: string, end: boolean, moved: boolean} | null>(null);
    const saving = useRef<Promise<void>>(Promise.resolve());

    const setPlans = (next: Array<Plan>) => {
        plansRef.current = next;
        setPlansState(next);
    };

    useEffect(() => {
        hass.callWS({type: "scene_studio/get_room_plans"}).then(result => {
            setPlans((result?.plans ?? []).map(p => ({...p, key: p.id})));
        }).catch(() => {
            /* intentional: without plans every light is unplaced */
        });
    }, [version]); // eslint-disable-line react-hooks/exhaustive-deps

    const placeOf = (entity: string): Place | undefined => {
        for (const plan of plans) {
            if (plan.lights[entity]) {
                return plan.lights[entity];
            }
        }
        return undefined;
    };

    /** The plan a light belongs to: the one it is on, else the plan of its room (made when needed). */
    const planKeyFor = (entity: string, all: Array<Plan>): {key: string, plans: Array<Plan>} => {
        const own = all.find(p => p.lights[entity]);
        if (own) {
            return {key: own.key, plans: all};
        }
        const area = entityAreaId(hass, entity) ?? areaId;
        const room = all.find(p => (p.area_id ?? undefined) === area);
        if (room) {
            return {key: room.key, plans: all};
        }
        const plan: Plan = {key: "new_" + (area ?? "home"), name: areaName(hass, area) || t("room_plan_home"), area_id: area, lights: {}};
        return {key: plan.key, plans: [...all, plan]};
    };

    const change = (entity: string, place: Place | null): string => {
        const {key, plans: all} = planKeyFor(entity, plansRef.current);
        setPlans(all.map(p => {
            if (p.key !== key) {
                return p;
            }
            const next = {...p.lights};
            if (place) {
                next[entity] = place;
            } else {
                delete next[entity];
            }
            return {...p, lights: next};
        }));
        return key;
    };

    /** One save after the other, always with the latest places (a new plan gets its id from the first). */
    const save = (key: string) => {
        saving.current = saving.current.then(async () => {
            const plan = plansRef.current.find(p => p.key === key);
            if (!plan) {
                return;
            }
            try {
                const result = await hass.callWS({
                    type: "scene_studio/save_room_plan",
                    plan_id: plan.id,
                    name: plan.name,
                    area_id: plan.area_id ?? null,
                    lights: plan.lights,
                    aspect: plan.aspect ?? null,
                    image: plan.image ?? null
                });
                if (!plan.id && result?.plan?.id) {
                    setPlans(plansRef.current.map(p => p.key === key ? {...p, id: result.plan.id} : p));
                }
                setError("");
            } catch (err: any) {
                setError(err?.message ?? String(err));
            }
        });
    };

    const pointerPos = (e: React.PointerEvent): {x: number, y: number} | null => {
        const rect = box.current?.getBoundingClientRect();
        if (!rect || !rect.width) {
            return null;
        }
        return {x: clamp((e.clientX - rect.left) / rect.width), y: clamp((e.clientY - rect.top) / rect.height)};
    };

    const startDrag = (e: React.PointerEvent, entity: string, end: boolean) => {
        setSelected(entity);
        if (!canEdit) {
            return;
        }
        (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
        drag.current = {entity, end, moved: false};
    };

    const moveDrag = (e: React.PointerEvent) => {
        const d = drag.current;
        const pos = pointerPos(e);
        if (!d || !pos) {
            return;
        }
        const place = plansRef.current.map(p => p.lights[d.entity]).find(Boolean);
        if (!place) {
            return;
        }
        d.moved = true;
        if (d.end) {
            change(d.entity, {...place, x2: pos.x, y2: pos.y});
        } else if (place.x2 !== undefined && place.y2 !== undefined) {
            // the whole strip moves with its start
            change(d.entity, {x: pos.x, y: pos.y, x2: clamp(place.x2 + pos.x - place.x), y2: clamp(place.y2 + pos.y - place.y)});
        } else {
            change(d.entity, {x: pos.x, y: pos.y});
        }
    };

    const endDrag = () => {
        const d = drag.current;
        drag.current = null;
        if (d?.moved) {
            const plan = plansRef.current.find(p => p.lights[d.entity]);
            if (plan) {
                save(plan.key);
            }
        }
    };

    const placeNew = (entity: string) => {
        // in rows with room for the names, so a new light never hides another one
        const n = lights.filter(l => placeOf(l.entity_id)).length;
        save(change(entity, {x: clamp(0.14 + (n % 4) * 0.24), y: clamp(0.28 + (Math.floor(n / 4) % 3) * 0.24)}));
        setSelected(entity);
    };

    /** The plan the format and the floor plan belong to: the one of the room, else the one with most lights. */
    const mainPlan = (all: Array<Plan>): Plan | undefined => {
        const room = all.find(p => areaId !== undefined && p.area_id === areaId);
        if (room) {
            return room;
        }
        const count = (p: Plan) => lights.filter(l => p.lights[l.entity_id]).length;
        const best = [...all].sort((a, b) => count(b) - count(a))[0];
        return best && count(best) > 0 ? best : all.find(p => (p.area_id ?? undefined) === areaId);
    };

    const changePlan = (values: {aspect?: number, image?: string | null}) => {
        let all = plansRef.current;
        let plan = mainPlan(all);
        if (!plan) {
            plan = {key: "new_" + (areaId ?? "home"), name: areaName(hass, areaId) || t("room_plan_home"), area_id: areaId, lights: {}};
            all = [...all, plan];
        }
        const key = plan.key;
        setPlans(all.map(p => p.key === key ? {...p, ...values} : p));
        save(key);
    };

    const upload = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        e.target.value = "";
        if (!file) {
            return;
        }
        try {
            changePlan(await readFloorPlan(file));
        } catch (err: any) {
            setError(t("spatial_image_error"));
        }
    };

    const main = mainPlan(plans);
    const aspect = main?.aspect ?? DEFAULT_ASPECT;
    const placed = lights.filter(l => placeOf(l.entity_id));
    const unplaced = lights.filter(l => !placeOf(l.entity_id));
    const current = selected ? lights.find(l => l.entity_id === selected) : undefined;
    const currentPlace = current ? placeOf(current.entity_id) : undefined;

    return (
        <div className={"sp-field sp-room-field"}>
            {
                canEdit &&
                <div className={"sp-room-tools"}>
                    {FORMATS.map(f => (
                        <button
                            key={f.label}
                            type={"button"}
                            className={"sp-icon-btn sp-room-format" + (Math.abs(aspect - f.aspect) < 0.01 ? " active" : "")}
                            title={t(f.label)}
                            aria-pressed={Math.abs(aspect - f.aspect) < 0.01}
                            onClick={() => changePlan({aspect: f.aspect})}
                        >
                            <ha-icon icon={f.icon}/>
                        </button>
                    ))}
                    <span className={"sp-grow"}/>
                    <label className={"sp-icon-btn sp-room-upload"} title={t("spatial_image")}>
                        <ha-icon icon={"mdi:floor-plan"}/>
                        <input type={"file"} accept={"image/*"} hidden onChange={upload}/>
                    </label>
                    {
                        main?.image &&
                        <button
                            type={"button"}
                            className={"sp-icon-btn sp-room-image-remove"}
                            title={t("spatial_image_remove")}
                            onClick={() => changePlan({image: null})}
                        >
                            <ha-icon icon={"mdi:image-off-outline"}/>
                        </button>
                    }
                </div>
            }
            <div
                className={"sp-room"}
                ref={box}
                style={{aspectRatio: String(aspect), maxWidth: aspect < 1.2 ? Math.round(aspect * 440) + "px" : undefined}}
            >
                {image && <div className={"sp-room-img"} style={{backgroundImage: `url("${image}")`}}/>}
                {main?.image && <div className={"sp-room-plan"} style={{backgroundImage: `url("${main.image}")`}}/>}
                {!image && <div className={"sp-room-note sp-secondary sp-small"}>{t("spatial_music")}</div>}
                <svg className={"sp-room-lines"} viewBox={"0 0 100 100"} preserveAspectRatio={"none"}>
                    {placed.map(l => {
                        const p = placeOf(l.entity_id)!;
                        return p.x2 === undefined || p.y2 === undefined ? null :
                            <line key={l.entity_id} x1={p.x * 100} y1={p.y * 100} x2={p.x2 * 100} y2={p.y2 * 100} vectorEffect={"non-scaling-stroke"}/>;
                    })}
                </svg>
                {
                    moving &&
                    <ha-icon class={"sp-room-arrow"} icon={"mdi:arrow-right-thin"} style={{transform: `rotate(${direction}deg)`}}/>
                }
                {placed.map(l => {
                    const p = placeOf(l.entity_id)!;
                    const active = l.entity_id === selected;
                    return (
                        <React.Fragment key={l.entity_id}>
                            <button
                                type={"button"}
                                className={"sp-room-light" + (active ? " active" : "")}
                                style={{left: pct(p.x), top: pct(p.y)}}
                                title={l.name}
                                onPointerDown={(e) => startDrag(e, l.entity_id, false)}
                                onPointerMove={moveDrag}
                                onPointerUp={endDrag}
                                onPointerCancel={endDrag}
                            >
                                <span className={"sp-room-label"}>{l.name}</span>
                            </button>
                            {
                                p.x2 !== undefined && p.y2 !== undefined &&
                                <button
                                    type={"button"}
                                    className={"sp-room-light end" + (active ? " active" : "")}
                                    style={{left: pct(p.x2), top: pct(p.y2)}}
                                    title={l.name}
                                    onPointerDown={(e) => startDrag(e, l.entity_id, true)}
                                    onPointerMove={moveDrag}
                                    onPointerUp={endDrag}
                                    onPointerCancel={endDrag}
                                />
                            }
                        </React.Fragment>
                    );
                })}
            </div>

            {
                current && currentPlace && canEdit &&
                <div className={"sp-room-bar"}>
                    <span className={"sp-grow sp-small"}>{current.name}</span>
                    <button
                        type={"button"}
                        className={"sp-icon-btn sp-room-strip" + (currentPlace.x2 !== undefined ? " active" : "")}
                        title={t("spatial_strip")}
                        aria-pressed={currentPlace.x2 !== undefined}
                        onClick={() => {
                            const p = currentPlace;
                            save(change(current.entity_id, p.x2 !== undefined ?
                                {x: p.x, y: p.y} :
                                {x: p.x, y: p.y, x2: clamp(p.x + (p.x > 0.75 ? -0.2 : 0.2)), y2: p.y}));
                        }}
                    >
                        <ha-icon icon={"mdi:led-strip-variant"}/>
                    </button>
                    <button
                        type={"button"}
                        className={"sp-icon-btn sp-room-remove"}
                        title={t("spatial_remove")}
                        onClick={() => {
                            save(change(current.entity_id, null));
                            setSelected(null);
                        }}
                    >
                        <ha-icon icon={"mdi:close"}/>
                    </button>
                </div>
            }

            {
                preview &&
                <div className={"sp-room-bar"}>
                    {
                        unplaced.length > 0 &&
                        <button type={"button"} className={"sp-chip small sp-room-missing"} onClick={onOpenPlan}>
                            {t("spatial_unplaced_count", {count: unplaced.length})}
                        </button>
                    }
                    <span className={"sp-grow"}/>
                    <button type={"button"} className={"sp-icon-btn sp-room-open"} title={t("room_plan")} onClick={onOpenPlan}>
                        <ha-icon icon={"mdi:floor-plan"}/>
                    </button>
                </div>
            }

            {
                !preview && unplaced.length > 0 &&
                <>
                    <span className={"sp-field-label"}>{t("spatial_unplaced")}</span>
                    <div className={"sp-chips wrap"}>
                        {unplaced.map(l => (
                            <button
                                key={l.entity_id}
                                type={"button"}
                                className={"sp-chip small sp-room-add"}
                                disabled={!canEdit}
                                onClick={() => placeNew(l.entity_id)}
                            >
                                {l.name}
                            </button>
                        ))}
                    </div>
                </>
            }

            {
                moving &&
                <>
                    <span className={"sp-field-label"}>{t("spatial_direction")}</span>
                    <div className={"sp-chips wrap sp-room-directions"}>
                        {DIRECTIONS.map(d => (
                            <button
                                key={d}
                                type={"button"}
                                className={"sp-chip small" + (d === direction ? " active" : "")}
                                aria-pressed={d === direction}
                                aria-label={d + "°"}
                                onClick={() => onDirection(d)}
                            >
                                <ha-icon icon={"mdi:arrow-right-thin"} style={{transform: `rotate(${d}deg)`}}/>
                            </button>
                        ))}
                    </div>
                </>
            }
            {error && <div className={"sp-error"}>{error}</div>}
        </div>
    );
};


/** The plan of a room: all its lights, the format and the floor plan. Set up once, used by every scene of the room. */
export const RoomPlanDialog: React.FunctionComponent<{
    hass: any,
    t: Translate,
    areaId?: string,
    /** lights that are not in the room but belong on this plan (lights of the scene the dialog was opened from) */
    lights?: Array<CanvasLight>,
    image?: string,
    onClose: () => void
}> = ({hass, t, areaId, lights, image, onClose}) => {
    const [roomLights, setRoomLights] = useState<Array<CanvasLight>>([]);

    useEffect(() => {
        if (!areaId) {
            return;
        }
        hass.callWS({type: "scene_studio/resolve_targets", targets: {area_id: [areaId]}}).then(result => {
            setRoomLights(result?.lights ?? []);
        }).catch(() => {
            /* intentional: then only the lights of the scene are shown */
        });
    }, [areaId]); // eslint-disable-line react-hooks/exhaustive-deps

    useEffect(() => {
        const onKey = (e: KeyboardEvent) => {
            if (e.key === "Escape") {
                e.stopPropagation();
                onClose();
            }
        };
        window.addEventListener("keydown", onKey, true);
        return () => window.removeEventListener("keydown", onKey, true);
    }, []); // eslint-disable-line react-hooks/exhaustive-deps

    const all = [...roomLights];
    (lights ?? []).forEach(l => {
        if (!all.some(r => r.entity_id === l.entity_id)) {
            all.push(l);
        }
    });
    const title = t("room_plan") + " · " + (areaName(hass, areaId) || t("room_plan_home"));

    return (
        <div className={"sp-overlay sp-room-overlay"} onClick={(e) => {
            if (e.target === e.currentTarget) {
                onClose();
            }
        }}>
            <div className={"sp-sheet sp-room-plan-dialog"} role={"dialog"} aria-modal={"true"} aria-label={title}>
                <div className={"sp-sheet-head"}>
                    <button className={"sp-icon-btn"} aria-label={t("close")} onClick={onClose}>
                        <ha-icon icon={"mdi:close"}/>
                    </button>
                    <div className={"sp-sheet-title"}>{title}</div>
                </div>
                <div className={"sp-sheet-body"}>
                    <RoomCanvas
                        hass={hass}
                        t={t}
                        lights={all}
                        areaId={areaId}
                        image={image}
                        moving={false}
                        direction={0}
                        onDirection={() => undefined}
                    />
                </div>
            </div>
        </div>
    );
};
