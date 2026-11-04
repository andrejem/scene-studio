// Added by andrejem (2026): saved scenes grouped by room (area of the scene entity), tap to activate,
// pencil to edit, "new scene" per room; tiles have the same size as on the presets tab

import React, {useMemo} from "react";
import {Translate} from "../i18n";
import {NewTile, PresetTile} from "../components/PresetTile";
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
    onShowPresets: () => void
}> = ({hass, t, savedScenes, presetMap, running, onActivate, onEdit, onNew, onShowPresets}) => {
    const [storedRoom, setRoom] = useLocalStorage<string>("scene_studio_room", "all");

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
                                <span className={"sp-secondary sp-small"}>{count(g.scenes.length)}</span>
                            </div>
                        }
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
                    </section>
                ))}
                <div className={"sp-secondary sp-small sp-hint"}>{t("scenes_hint")}</div>
            </div>
        </div>
    );
};
