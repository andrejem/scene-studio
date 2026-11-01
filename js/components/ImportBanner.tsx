// Added by andrejem (2026): offers the import from Scene Presets (saved scenes, own presets,
// scene entities with their IDs and areas) when it is installed or its data is still there

import React, {useEffect, useState} from "react";
import {Translate} from "../i18n";

type Status = {available: boolean, scenes: number, new_scenes: number, custom_files: number, scene_presets_loaded: boolean};

export const ImportBanner: React.FunctionComponent<{
    hass: any,
    t: Translate,
    onImported: () => void
}> = ({hass, t, onImported}) => {
    const [status, setStatus] = useState<Status | null>(null);
    const [open, setOpen] = useState(false);
    const [takeOver, setTakeOver] = useState(true);
    const [busy, setBusy] = useState(false);
    const [result, setResult] = useState<string>("");
    const [error, setError] = useState<string>("");
    const [hidden, setHidden] = useState<boolean>(() => {
        try {
            return sessionStorage.getItem("scene_studio_import_later") === "1";
        } catch {
            return false;
        }
    });
    const isAdmin = !!hass?.user?.is_admin;

    useEffect(() => {
        if (!isAdmin) {
            return;
        }
        hass.callWS({type: "scene_studio/import_status"}).then((s: Status) => setStatus(s)).catch(() => setStatus(null));
    }, [isAdmin]); // eslint-disable-line react-hooks/exhaustive-deps

    if (result) {
        return (
            <div className={"sp-notice sp-import"} role={"status"}>
                <span className={"sp-grow"}>{result}</span>
                <button className={"sp-link"} onClick={() => setResult("")}>{t("close")}</button>
            </div>
        );
    }
    if (!isAdmin || !status?.available || hidden) {
        return null;
    }

    const run = () => {
        setBusy(true);
        setError("");
        hass.callWS({type: "scene_studio/import", take_over_entities: takeOver}).then((r: any) => {
            setResult(t("import_done", {scenes: r.scenes, entities: r.entities}));
            setStatus(null);
            setOpen(false);
            onImported();
        }).catch((err: any) => {
            setError(err?.message ?? String(err));
        }).finally(() => setBusy(false));
    };

    return (
        <div className={"sp-notice sp-import"}>
            <div className={"sp-import-head"}>
                <span className={"sp-grow"}>
                    <span className={"sp-strong sp-block"}>{t("import_found")}</span>
                    <span className={"sp-small sp-block"}>
                        {t("import_what", {scenes: status.new_scenes})}
                        {status.custom_files > 0 ? t("import_with_presets") : ""}
                    </span>
                </span>
                {
                    !open &&
                    <>
                        <button className={"sp-btn text"} onClick={() => {
                            setHidden(true);
                            try {
                                sessionStorage.setItem("scene_studio_import_later", "1");
                            } catch {
                                /* only for this session anyway */
                            }
                        }}>{t("later")}</button>
                        <button className={"sp-btn primary import-open"} onClick={() => setOpen(true)}>{t("import")}</button>
                    </>
                }
            </div>
            {
                open &&
                <div className={"sp-import-body"}>
                    <label className={"sp-check"}>
                        <input type={"checkbox"} checked={takeOver} onChange={(e) => setTakeOver(e.target.checked)}/>
                        <span>
                            <span className={"sp-block"}>{t("import_take_over")}</span>
                            <span className={"sp-small sp-secondary sp-block"}>
                                {t(status.scene_presets_loaded ? "import_take_over_help" : "import_take_over_help_off")}
                            </span>
                        </span>
                    </label>
                    {error && <div className={"sp-error"}>{error}</div>}
                    <div className={"sp-actions sp-actions-end"}>
                        <button className={"sp-btn text"} onClick={() => setOpen(false)}>{t("cancel")}</button>
                        <button className={"sp-btn primary import-run"} disabled={busy} onClick={run}>{t("import")}</button>
                    </div>
                </div>
            }
        </div>
    );
};

/** Favorites, chosen lights and settings of the Scene Presets panel (same browser) are taken over once. */
export function importBrowserSettings(): void {
    try {
        if (localStorage.getItem("scene_studio_browser_imported")) {
            return;
        }
        const keys: Array<string> = [];
        for (let i = 0; i < localStorage.length; i++) {
            const key = localStorage.key(i);
            if (key && key.startsWith("scene_presets_")) {
                keys.push(key);
            }
        }
        keys.forEach(key => {
            const newKey = "scene_studio_" + key.slice("scene_presets_".length);
            const value = localStorage.getItem(key);
            if (value !== null && localStorage.getItem(newKey) === null) {
                localStorage.setItem(newKey, value);
            }
        });
        localStorage.setItem("scene_studio_browser_imported", "1");
    } catch {
        /* browser storage not available: nothing to take over */
    }
}
