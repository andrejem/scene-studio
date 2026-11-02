// Added by andrejem (2026): running dynamic scenes at the top of the panel, each with a stop button.
// Music scenes (3.2) run with a preset of their own (music_<scene id>): shown with the scene name
// and the cover that is playing.

import React from "react";
import {Translate} from "../i18n";
import {MUSIC_PRESET_ID, SavedScene, areaName, entityAreaId, presetImage, sceneAreaId} from "../tunables";

export type RunningScene = {
    id: string,
    interval: number,
    parameters: any
};

export const RunningStrip: React.FunctionComponent<{
    hass: any,
    t: Translate,
    running: Array<RunningScene>,
    presetMap: {[id: string]: any},
    savedScenes: Array<SavedScene>,
    onStop: (id: string) => void
}> = ({hass, t, running, presetMap, savedScenes, onStop}) => {
    if (running.length === 0) {
        return null;
    }

    return (
        <div className={"sp-running-list"}>
            {running.map(r => {
                const params = r.parameters ?? {};
                const presetId: string = params.preset_id ?? "";
                const isMusic = presetId.startsWith("music_");
                const musicScene = isMusic ? savedScenes.find(s => "music_" + s.id === presetId) : undefined;
                const player = presetId.startsWith("music_adhoc_") ?
                    presetId.substring("music_adhoc_".length) : musicScene?.music?.media_player;
                const preset = isMusic ? presetMap[MUSIC_PRESET_ID] : presetMap[presetId];
                const areaIds = Array.from(new Set(
                    (params.light_entity_ids ?? []).map((e: string) => entityAreaId(hass, e)).filter((a: any) => !!a)
                )) as Array<string>;
                const rooms = areaIds.map(a => areaName(hass, a));
                const saved = musicScene ?? savedScenes.find(s =>
                    s.dynamic && s.preset_id === params.preset_id &&
                    (areaIds.length === 0 || areaIds.includes(sceneAreaId(hass, s) ?? ""))
                );
                const title = saved?.name ?? preset?.name ?? t("unknown_preset");
                const timing = params.interval_range ?
                    t("every_range", {min: params.interval_range[0], max: params.interval_range[1]}) :
                    t("every_seconds", {s: r.interval});
                const cover = player ? hass?.states?.[player]?.attributes?.entity_picture : undefined;
                const img = cover ?? presetImage(preset);

                return (
                    <div className={"sp-running"} key={"running_" + r.id}>
                        {
                            img ?
                                <img className={"sp-running-thumb"} src={img} alt={""}/> :
                                <span className={"sp-running-thumb"}/>
                        }
                        <div className={"sp-running-text"}>
                            <div className={"sp-running-label"}>{t("running")}</div>
                            <div className={"sp-running-name"}>
                                {title}
                                {rooms.length > 0 && !saved && <span className={"sp-secondary"}> · {rooms.join(", ")}</span>}
                            </div>
                            <div className={"sp-secondary sp-small"}>{timing}</div>
                        </div>
                        <button className={"sp-btn"} onClick={() => onStop(r.id)}>{t("stop")}</button>
                    </div>
                );
            })}
        </div>
    );
};
