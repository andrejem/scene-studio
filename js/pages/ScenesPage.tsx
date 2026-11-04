// Added by andrejem (2026): saved scenes grouped by room (area of the scene entity), tap to activate,
// pencil to edit, "new scene" per room; tiles have the same size as on the presets tab.
// Arrange (admins): drag scenes into place (mouse or finger), optionally the same order for all rooms
// (by the scene name without the room). The order is stored with the scenes (room cards use it too).

import React, {useMemo, useRef, useState} from "react";
import {Translate} from "../i18n";
import {NewTile, PresetTile} from "../components/PresetTile";
import HaIcon from "../components/hass/building_blocks/HaIcon";
import {useLocalStorage} from "../hooks/useLocalStorage";
import {RunningScene} from "../components/RunningStrip";
import {MUSIC_PRESET_ID, SavedScene, areaName, entityAreaId, presetImage, sceneAreaId, sceneEntityId, stripRoomName} from "../tunables";

const NO_ROOM = "__none__";

type Group = {key: string, name: string, scenes: Array<{scene: SavedScene, entityId?: string}>};

export const ScenesPage: React.FunctionComponent<{
    hass: any,
    t: Translate,
    savedScenes: Array<SavedScene> | null,
    presetMap: {[id: string]: any},
    running: Array<RunningScene>,
    onActivate: (id: string) => void,
    onEdit: (scene: SavedScene) => void,
    onNew: (areaId?: string) => void,
    onShowPresets: () => void,
    onReordered?: () => void
}> = ({hass, t, savedScenes, presetMap, running, onActivate, onEdit, onNew, onShowPresets, onReordered}) => {
    const [storedRoom, setRoom] = useLocalStorage<string>("scene_studio_room", "all");
    const isAdmin = !!hass?.user?.is_admin;
    // Arrange mode: the room being arranged and its scene ids in the new order
    const [arranging, setArranging] = useState<string | null>(null);
    const [draft, setDraft] = useState<Array<string>>([]);
    const [saving, setSaving] = useState(false);
    const dragId = useRef<string | null>(null);

    const groups: Array<Group> = useMemo(() => {
        const byKey: {[key: string]: Group} = {};
        (savedScenes ?? []).forEach(scene => {
            const areaId = sceneAreaId(hass, scene);
            const key = areaId ?? NO_ROOM;
            if (!byKey[key]) {
                byKey[key] = {key, name: areaId ? areaName(hass, areaId) : t("no_room"), scenes: []};
            }
            byKey[key].scenes.push({scene, entityId: sceneEntityId(hass, scene.id)});
        });
        return Object.values(byKey).sort((a, b) => {
            if (a.key === NO_ROOM) return 1;
            if (b.key === NO_ROOM) return -1;
            return a.name.localeCompare(b.name);
        });
    }, [savedScenes, hass?.entities, hass?.areas, hass?.states]); // eslint-disable-line react-hooks/exhaustive-deps

    const groupName = (g: Group) => (g.key === NO_ROOM ? "" : g.name);
    const baseName = (g: Group, scene: SavedScene) => stripRoomName(scene.name, groupName(g)).toLowerCase();

    const startArrange = (g: Group) => {
        setArranging(g.key);
        setDraft(g.scenes.map(({scene}) => scene.id));
    };

    const saveOrder = async (orders: {[key: string]: Array<string>}) => {
        setSaving(true);
        try {
            const ids = groups.flatMap(g => orders[g.key] ?? g.scenes.map(({scene}) => scene.id));
            await hass.callWS({type: "scene_studio/set_scene_order", scene_ids: ids});
            onReordered?.();
        } finally {
            setSaving(false);
            setArranging(null);
        }
    };

    const finish = () => arranging && saveOrder({[arranging]: draft});

    // same order in every room: by the scene name without the room, others keep theirs at the end
    const applyToAll = () => {
        const source = groups.find(g => g.key === arranging);
        if (!source) return;
        const byId = Object.fromEntries(source.scenes.map(({scene}) => [scene.id, scene]));
        const template = draft.map(id => baseName(source, byId[id]));
        const orders: {[key: string]: Array<string>} = {[source.key]: draft};
        groups.filter(g => g.key !== source.key).forEach(g => {
            const rank = (scene: SavedScene) => {
                const i = template.indexOf(baseName(g, scene));
                return i < 0 ? 10000 : i;
            };
            orders[g.key] = g.scenes
                .map(({scene}, i) => ({scene, i}))
                .sort((a, b) => rank(a.scene) - rank(b.scene) || a.i - b.i)
                .map(({scene}) => scene.id);
        });
        saveOrder(orders);
    };

    // drag & drop with pointer events (mouse, pen and finger alike)
    const onPointerDown = (e: React.PointerEvent<HTMLDivElement>, id: string) => {
        dragId.current = id;
        e.currentTarget.setPointerCapture(e.pointerId);
    };
    const onPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
        if (!dragId.current) return;
        const root = e.currentTarget.getRootNode() as Document | ShadowRoot;
        const under = (root.elementFromPoint ? root.elementFromPoint(e.clientX, e.clientY) : null)?.closest?.("[data-scene-id]") as HTMLElement | null;
        const target = under?.dataset.sceneId;
        if (!target || target === dragId.current) return;
        setDraft(prev => {
            const from = prev.indexOf(dragId.current!);
            const to = prev.indexOf(target);
            if (from < 0 || to < 0) return prev;
            const next = [...prev];
            next.splice(from, 1);
            next.splice(to, 0, dragId.current!);
            return next;
        });
    };
    const onPointerUp = () => {
        dragId.current = null;
    };

    const arrangeButtons = (g: Group) => {
        if (!isAdmin || g.scenes.length < 2) return null;
        if (arranging !== g.key) {
            return <button className={"sp-btn text sp-arrange"} disabled={!!arranging} onClick={() => startArrange(g)}>
                <HaIcon icon={"mdi:drag-variant"} size={18}/> {t("arrange")}
            </button>;
        }
        return <span className={"sp-arrange-actions"}>
            {groups.length > 1 && <button className={"sp-btn text sp-arrange-all"} disabled={saving} onClick={applyToAll}>{t("arrange_all")}</button>}
            <button className={"sp-btn primary sp-arrange-done"} disabled={saving} onClick={finish}>{t("done")}</button>
        </span>;
    };

    // Active scene per room: the one activated last, while a light of the room is on (or it runs dynamically)
    const activeIds = useMemo(() => {
        const ids = new Set<string>();
        groups.forEach(g => {
            const runningHere = g.scenes.find(({scene}) => scene.dynamic && running.some(r =>
                (r.parameters?.preset_id === scene.preset_id || r.parameters?.preset_id === "music_" + scene.id) &&
                (r.parameters?.light_entity_ids ?? []).some((e: string) => (entityAreaId(hass, e) ?? NO_ROOM) === g.key)
            ));
            if (runningHere) {
                ids.add(runningHere.scene.id);
                return;
            }
            if (g.key === NO_ROOM) {
                return;
            }
            const anyOn = Object.keys(hass?.entities ?? {}).some(e =>
                e.startsWith("light.") && entityAreaId(hass, e) === g.key && hass.states?.[e]?.state === "on"
            );
            if (!anyOn) {
                return;
            }
            let newest: string | undefined;
            let newestTime = 0;
            g.scenes.forEach(({scene, entityId}) => {
                const time = Date.parse(hass?.states?.[entityId ?? ""]?.state ?? "") || 0;
                if (time > newestTime) {
                    newestTime = time;
                    newest = scene.id;
                }
            });
            if (newest) {
                ids.add(newest);
            }
        });
        return ids;
    }, [groups, running, hass?.states]); // eslint-disable-line react-hooks/exhaustive-deps

    const room = groups.some(g => g.key === storedRoom) ? storedRoom : "all";
    const visible = room === "all" ? groups : groups.filter(g => g.key === room);
    const selectedRoom = groups.find(g => g.key === room);
    const total = (savedScenes ?? []).length;
    const count = (n: number) => n === 1 ? t("scene_count_one") : t("scene_count", {n});

    if (savedScenes === null) {
        return <div className={"sp-empty"}/>;
    }

    if (total === 0) {
        return (
            <div className={"sp-empty"}>
                <p>{t("no_scenes")}</p>
                <div className={"sp-actions"}>
                    <button className={"sp-btn primary"} onClick={() => onNew()}>{t("new_scene")}</button>
                    <button className={"sp-btn"} onClick={onShowPresets}>{t("tab_presets")}</button>
                </div>
            </div>
        );
    }

    return (
        <div className={"sp-layout"}>
            <nav className={"sp-roomnav"} aria-label={t("room")}>
                <div className={"sp-secondary sp-small sp-roomnav-title"}>{t("rooms")}</div>
                <button className={"sp-roomnav-item" + (room === "all" ? " active" : "")} onClick={() => setRoom("all")}>
                    <span>{t("all")}</span><span className={"sp-count"}>{total}</span>
                </button>
                {groups.map(g => (
                    <button key={"nav_" + g.key} className={"sp-roomnav-item" + (room === g.key ? " active" : "")} onClick={() => setRoom(g.key)}>
                        <span>{g.name}</span><span className={"sp-count"}>{g.scenes.length}</span>
                    </button>
                ))}
            </nav>

            <div className={"sp-main"}>
                <div className={"sp-chips sp-room-chips"}>
                    <button className={"sp-chip" + (room === "all" ? " active" : "")} onClick={() => setRoom("all")}>{t("all")}</button>
                    {groups.map(g => (
                        <button key={"chip_" + g.key} className={"sp-chip" + (room === g.key ? " active" : "")} onClick={() => setRoom(g.key)}>
                            {g.name}
                        </button>
                    ))}
                </div>

                <div className={"sp-page-head"}>
                    <h2>{selectedRoom ? selectedRoom.name : t("all_scenes")}</h2>
                    {selectedRoom && room !== "all" && arrangeButtons(selectedRoom)}
                    <button
                        className={"sp-btn primary sp-new-scene"}
                        onClick={() => onNew(selectedRoom && selectedRoom.key !== NO_ROOM ? selectedRoom.key : undefined)}
                    >
                        + {t("new_scene")}
                    </button>
                </div>

                {visible.map(g => (
                    <section key={"group_" + g.key} className={"sp-group"}>
                        {
                            room === "all" &&
                            <div className={"sp-section-head"}>
                                <h3>{g.name}</h3>
                                <span className={"sp-section-tools"}>
                                    {arrangeButtons(g)}
                                    {arranging !== g.key && <span className={"sp-secondary sp-small"}>{count(g.scenes.length)}</span>}
                                </span>
                            </div>
                        }
                        {arranging === g.key && <div className={"sp-secondary sp-small sp-hint"}>{t("arrange_hint")}</div>}
                        {
                            arranging === g.key ?
                        <div className={"sp-grid small arranging"}>
                            {draft.map(id => g.scenes.find(({scene}) => scene.id === id)).filter(Boolean).map(entry => {
                                const scene = entry!.scene;
                                return <div
                                    key={"arr_" + scene.id}
                                    data-scene-id={scene.id}
                                    className={"sp-drag" + (dragId.current === scene.id ? " dragging" : "")}
                                    onPointerDown={(e) => onPointerDown(e, scene.id)}
                                    onPointerMove={onPointerMove}
                                    onPointerUp={onPointerUp}
                                    onPointerCancel={onPointerUp}
                                >
                                    <PresetTile
                                        small
                                        id={scene.id}
                                        name={stripRoomName(scene.name, groupName(g))}
                                        imgSrc={presetImage(presetMap[scene.preset_id])}
                                    />
                                </div>;
                            })}
                        </div> :
                        <div className={"sp-grid small"}>
                            {g.scenes.map(({scene}) => (
                                <PresetTile
                                    small
                                    key={"scene_" + scene.id}
                                    id={scene.id}
                                    name={stripRoomName(scene.name, g.key === NO_ROOM ? "" : g.name)}
                                    title={scene.name}
                                    imgSrc={presetImage(presetMap[scene.preset_id])}
                                    onClick={(id) => onActivate(id)}
                                    actionIcon={"mdi:pencil"}
                                    actionLabel={t("edit")}
                                    onActionClick={() => onEdit(scene)}
                                    badge={scene.preset_id === MUSIC_PRESET_ID ? t("music_badge") : (scene.dynamic ? t("badge_dynamic") : undefined)}
                                    badgeIcon={scene.preset_id === MUSIC_PRESET_ID ? "mdi:music-note" : undefined}
                                    active={activeIds.has(scene.id)}
                                />
                            ))}
                            <NewTile
                                small
                                label={t("new_scene")}
                                icon={"mdi:plus"}
                                onClick={() => onNew(g.key === NO_ROOM ? undefined : g.key)}
                            />
                        </div>
                        }
                    </section>
                ))}
                <div className={"sp-secondary sp-small sp-hint"}>{t("scenes_hint")}</div>
            </div>
        </div>
    );
};
