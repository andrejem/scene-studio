// Added by andrejem (2026): room canvas (4.0). The lights of a scene on the plan of their room, over the
// picture of the preset. The places belong to the room (room plans in the backend), so every scene of
// the room uses them; they are saved when a light is dropped.
import React, {useEffect, useRef, useState} from "react";
import {Translate} from "../i18n";
import {areaName, entityAreaId} from "../tunables";

export type Place = {x: number, y: number, x2?: number, y2?: number};
type Plan = {key: string, id?: string, name: string, area_id?: string, lights: {[entityId: string]: Place}};
type CanvasLight = {entity_id: string, name: string};

const DIRECTIONS = [0, 45, 90, 135, 180, 225, 270, 315];
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
    onDirection: (direction: number) => void
}> = ({hass, t, lights, areaId, image, moving, direction, onDirection}) => {
    const canEdit = !!hass?.user?.is_admin;
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
    }, []); // eslint-disable-line react-hooks/exhaustive-deps

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
                    lights: plan.lights
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
        // next to each other in the middle, so a new light never hides another one
        const n = lights.filter(l => placeOf(l.entity_id)).length;
        save(change(entity, {x: clamp(0.2 + (n % 5) * 0.15), y: clamp(0.5 + (Math.floor(n / 5) % 3) * 0.14)}));
        setSelected(entity);
    };

    const placed = lights.filter(l => placeOf(l.entity_id));
    const unplaced = lights.filter(l => !placeOf(l.entity_id));
    const current = selected ? lights.find(l => l.entity_id === selected) : undefined;
    const currentPlace = current ? placeOf(current.entity_id) : undefined;

    return (
        <div className={"sp-field sp-room-field"}>
            <div className={"sp-room"} ref={box}>
                {image && <div className={"sp-room-img"} style={{backgroundImage: `url("${image}")`}}/>}
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
                unplaced.length > 0 &&
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
