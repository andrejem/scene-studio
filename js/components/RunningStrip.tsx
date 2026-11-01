// Added by andrejem (2026): running dynamic scenes at the top of the panel, each with a stop button

import React from "react";
import {Translate} from "../i18n";
import {SavedScene, areaName, entityAreaId, presetImage, sceneAreaId} from "../tunables";

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
                const preset = presetMap[params.preset_id];
                const areaIds = Array.from(new Set(
                    (params.light_entity_ids ?? []).map((e: string) => entityAreaId(hass, e)).filter((a: any) => !!a)
                )) as Array<string>;
                const rooms = areaIds.map(a => areaName(hass, a));
                const saved = savedScenes.find(s =>
                    s.dynamic && s.preset_id === params.preset_id &&
                    (areaIds.length === 0 || areaIds.includes(sceneAreaId(hass, s) ?? ""))
                );
                const title = saved?.name ?? preset?.name ?? t("unknown_preset");
                const timing = params.interval_range ?
                    t("every_range", {min: params.interval_range[0], max: params.interval_range[1]}) :
                    t("every_seconds", {s: r.interval});
                const img = presetImage(preset);

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
