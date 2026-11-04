// Added by andrejem (2026): presets of the user - create a preset from a photo or from chosen colors
// (the picture is then the gradient of the colors), edit and delete own presets, change the colors and
// default brightness of built-in presets (the original can be restored; their picture stays) or hide them.
// Colors are picked in two tabs like the Hue app (color / white tones, ColorEditor).
// Pictures of own presets are shown through their signed URL.

import React, {useEffect, useRef, useState} from "react";
import HaDialog from "./hass/building_blocks/HaDialog";
import {Category, Preset} from "../types";
import {Translate} from "../i18n";
import {presetImage} from "../tunables";
import {extractPalette, rgbToHex, rgbToXy, XY, xyToRgb} from "../palette";
import {COLOR_EDITOR_CSS, ColorEditor} from "./ColorEditor";

const BUTTON: React.CSSProperties = {
    padding: "0.5rem 1rem",
    fontSize: "0.95rem",
    fontWeight: 500,
    borderRadius: "18px",
    border: "none",
    cursor: "pointer",
    background: "transparent",
    color: "var(--primary-color, #03a9f4)"
};

const INPUT: React.CSSProperties = {
    width: "100%",
    boxSizing: "border-box",
    padding: "0.65rem",
    fontSize: "1rem",
    borderRadius: "4px",
    border: "1px solid var(--divider-color, #888)",
    background: "var(--card-background-color, transparent)",
    color: "var(--primary-text-color, inherit)"
};

const LABEL: React.CSSProperties = {fontWeight: 500, marginTop: "1rem", marginBottom: "0.35rem"};
const HINT: React.CSSProperties = {fontSize: "0.85rem", opacity: 0.8};
const NEW_CATEGORY = "__new__";
const COLOR_MODES = ["xy", "hs", "rgb", "rgbw", "rgbww"];
const MAX_COLORS = 6;
// first colors of a preset made from colors: amber, rose, violet
const START_COLORS: Array<XY> = [{x: 0.5614, y: 0.4072}, {x: 0.4859, y: 0.2786}, {x: 0.2697, y: 0.1361}];

type Source = "colors" | "photo";

type Props = {
    hass: any,
    t: Translate,
    open: boolean,
    presetId: string | null,
    categories: Array<Category>,
    presets: Array<Preset & {custom?: boolean, overridden?: boolean, generated?: boolean}>,
    targets: any,
    onClose: () => void,
    onChanged: () => void,
};

/** Photo -> JPEG for storing (max 1024 px) and pixels for the color analysis (max 96 px). */
async function readPhoto(file: File): Promise<{dataUrl: string, pixels: Uint8ClampedArray}> {
    const bitmap = await createImageBitmap(file);
    const draw = (max: number) => {
        const scale = Math.min(1, max / Math.max(bitmap.width, bitmap.height));
        const canvas = document.createElement("canvas");
        canvas.width = Math.max(1, Math.round(bitmap.width * scale));
        canvas.height = Math.max(1, Math.round(bitmap.height * scale));
        const ctx = canvas.getContext("2d")!;
        ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
        return {canvas, ctx};
    };
    const big = draw(1024);
    const small = draw(96);
    const pixels = small.ctx.getImageData(0, 0, small.canvas.width, small.canvas.height).data;
    return {dataUrl: big.canvas.toDataURL("image/jpeg", 0.85), pixels};
}

/** Picture of a preset made from colors: the colors as a soft diagonal gradient. */
export function gradientPicture(colors: Array<XY>, width = 1024, height = 640): string {
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext("2d")!;
    const hex = colors.map(c => rgbToHex(xyToRgb(c)));
    const list = hex.length === 1 ? [hex[0], hex[0]] : hex;
    const gradient = ctx.createLinearGradient(0, 0, width, height * 0.6);
    list.forEach((c, i) => gradient.addColorStop(i / (list.length - 1), c));
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, width, height);
    // a little depth: lighter top, darker bottom
    const shade = ctx.createLinearGradient(0, 0, 0, height);
    shade.addColorStop(0, "rgba(255,255,255,0.10)");
    shade.addColorStop(1, "rgba(0,0,0,0.22)");
    ctx.fillStyle = shade;
    ctx.fillRect(0, 0, width, height);
    return canvas.toDataURL("image/jpeg", 0.9);
}

export const PhotoPresetDialog: React.FunctionComponent<Props> = ({
    hass, t, open, presetId, categories, presets, targets, onClose, onChanged
}): React.JSX.Element => {
    const preset = presetId ? presets.find(p => p.id === presetId) : undefined;
    const isBuiltin = !!preset && !preset.custom;

    const [source, setSource] = useState<Source>("colors");
    const [image, setImage] = useState<string | null>(null);
    const [colors, setColors] = useState<Array<XY>>([]);
    const [selected, setSelected] = useState<number>(0);
    const [count, setCount] = useState<number>(5);
    const [name, setName] = useState<string>("");
    const [categoryId, setCategoryId] = useState<string>("");
    const [newCategory, setNewCategory] = useState<string>("");
    const [brightness, setBrightness] = useState<number>(80);
    const [briChanged, setBriChanged] = useState<boolean>(false);
    const [busy, setBusy] = useState<boolean>(false);
    const [error, setError] = useState<string>("");
    const [info, setInfo] = useState<string>("");
    const [colorsChanged, setColorsChanged] = useState<boolean>(false);
    const pixels = useRef<Uint8ClampedArray | null>(null);
    const fileInput = useRef<HTMLInputElement | null>(null);

    // load the preset (or start a new one) whenever the dialog opens
    useEffect(() => {
        if (!open) {
            return;
        }
        setImage(null);
        pixels.current = null;
        setError("");
        setInfo("");
        setColorsChanged(false);
        setBriChanged(false);
        setNewCategory("");
        setSelected(0);
        if (preset) {
            setSource(preset.generated ? "colors" : "photo");
            setName(preset.name);
            setCategoryId(preset.categoryId);
            setColors(preset.lights.map(l => ({x: l.x, y: l.y})));
            setCount(Math.max(1, Math.min(MAX_COLORS, preset.lights.length)));
            setBrightness(Math.max(1, Math.round((preset.bri ?? 255) * 100 / 255)));
        } else {
            setSource("colors");
            setName("");
            setCategoryId("");
            setColors(START_COLORS);
            setCount(5);
            setBrightness(80);
        }
    }, [open, presetId]); // eslint-disable-line react-hooks/exhaustive-deps

    const changeColors = (next: Array<XY>) => {
        setColors(next);
        setColorsChanged(true);
    };

    const takeColors = (n: number) => {
        if (pixels.current) {
            changeColors(extractPalette(pixels.current, n).map(rgbToXy));
            setSelected(0);
        }
    };

    const onFile = async (file?: File) => {
        if (!file) {
            return;
        }
        setError("");
        try {
            const photo = await readPhoto(file);
            setImage(photo.dataUrl);
            setSource("photo");
            pixels.current = photo.pixels;
            // a new preset takes its colors from the photo; an existing one keeps them until asked
            if (!preset) {
                changeColors(extractPalette(photo.pixels, count).map(rgbToXy));
                setSelected(0);
            }
        } catch (e) {
            setError(t("photo_unreadable"));
        }
    };

    const preview = async () => {
        setError("");
        setInfo("");
        const hasTargets = Object.values(targets ?? {}).some((v: any) => Array.isArray(v) ? v.length > 0 : !!v);
        if (!hasTargets) {
            setInfo(t("preview_no_targets"));
            return;
        }
        const result = await hass.callWS({type: "scene_studio/resolve_targets", targets: targets});
        const lights = (result?.lights ?? [])
            .map((l: any) => l.entity_id)
            .filter((id: string) => (hass.states[id]?.attributes?.supported_color_modes ?? []).some((m: string) => COLOR_MODES.includes(m)));
        if (lights.length === 0 || colors.length === 0) {
            setInfo(t("preview_no_color_lights"));
            return;
        }
        await Promise.all(lights.map((id: string, i: number) => {
            const xy = colors[i % colors.length];
            return hass.callService("light", "turn_on", {entity_id: id, xy_color: [xy.x, xy.y], brightness_pct: brightness, transition: 1})
                .catch(() => undefined);
        }));
        setInfo(t("preview_done", {n: lights.length}));
    };

    const run = async (job: () => Promise<any>) => {
        setBusy(true);
        setError("");
        try {
            await job();
            onChanged();
            onClose();
        } catch (e: any) {
            setError(e?.message ?? String(e));
        } finally {
            setBusy(false);
        }
    };

    // a picture made from the colors: for presets made from colors, renewed when the colors change
    const fromColors = source === "colors" && !image;

    const save = () => run(async () => {
        const lights = colors.map(c => ({x: c.x, y: c.y}));
        const bri = Math.max(1, Math.min(255, Math.round(brightness * 2.55)));
        if (isBuiltin) {
            const msg: any = {type: "scene_studio/set_preset_image", preset_id: preset!.id};
            if (colorsChanged) msg.lights = lights;
            if (briChanged) msg.bri = bri;
            await hass.callWS(msg);
            return;
        }
        const msg: any = {
            type: "scene_studio/save_custom_preset",
            name: name.trim(),
            bri: bri,
            lights: lights,
            default_category_name: t("my_presets")
        };
        if (preset) msg.preset_id = preset.id;
        if (image) {
            msg.image = image;
            msg.generated = false;
        } else if (fromColors && (!preset || colorsChanged || !preset.generated)) {
            msg.image = gradientPicture(colors);
            msg.generated = true;
        }
        if (categoryId === NEW_CATEGORY) {
            msg.new_category = newCategory.trim();
        } else if (categoryId) {
            msg.category_id = categoryId;
        }
        await hass.callWS(msg);
    });

    const remove = () => {
        if (!preset || !window.confirm(t("preset_delete_confirm", {name: preset.name}))) {
            return;
        }
        run(() => hass.callWS({type: "scene_studio/delete_custom_preset", preset_id: preset.id}));
    };

    const hide = () => run(() => hass.callWS({type: "scene_studio/set_preset_hidden", preset_id: preset!.id, hidden: true}));

    const reset = () => {
        if (!preset || !window.confirm(t("preset_reset_confirm", {name: preset.name}))) {
            return;
        }
        run(() => hass.callWS({type: "scene_studio/reset_preset", preset_id: preset.id}));
    };

    const imageSrc = image ?? (fromColors && (colorsChanged || !preset) ? null : presetImage(preset) ?? null);
    const gradientPreview = colors.length > 0 ?
        `linear-gradient(120deg, ${(colors.length === 1 ? [colors[0], colors[0]] : colors).map(c => rgbToHex(xyToRgb(c))).join(", ")})` : undefined;
    const canSave = !busy && colors.length > 0 && (isBuiltin
        ? (colorsChanged || briChanged)
        : (!!name.trim() && (!!image || !!preset || source === "colors") && (categoryId !== NEW_CATEGORY || !!newCategory.trim())));

    const sourceTab = (value: Source, label: string, icon: string) => (
        <button
            className={"preset-source-" + value}
            onClick={() => {
                setSource(value);
                if (value === "photo" && !image && !preset) {
                    fileInput.current?.click();
                }
                if (value === "colors") {
                    setImage(null);
                    pixels.current = null;
                }
            }}
            style={{
                flex: 1, display: "flex", alignItems: "center", justifyContent: "center", gap: "6px", border: "none",
                padding: "8px 10px", borderRadius: "10px", cursor: "pointer", font: "inherit",
                background: source === value ? "var(--card-background-color, #fff)" : "transparent",
                color: source === value ? "var(--primary-text-color)" : "var(--secondary-text-color)",
                boxShadow: source === value ? "0 1px 3px rgba(0,0,0,.25)" : "none",
            }}
        >
            <ha-icon icon={icon} style={{"--mdc-icon-size": "18px"}}/>{label}
        </button>
    );

    return (
        <HaDialog
            open={open}
            onClose={onClose}
            heading={preset ? t("preset_edit_heading", {name: preset.name}) : t("preset_new_heading")}
        >
            <style>{COLOR_EDITOR_CSS}</style>
            <div className={"photo-preset-dialog"} style={{minWidth: "min(80vw, 520px)"}}>
                <div style={HINT}>{isBuiltin ? t("photo_intro_builtin") : (source === "colors" ? t("colors_intro") : t("photo_intro"))}</div>

                {
                    !isBuiltin &&
                    <div style={{display: "flex", gap: "4px", padding: "3px", marginTop: "0.75rem", borderRadius: "12px", background: "var(--secondary-background-color, rgba(127,127,127,.15))"}}>
                        {sourceTab("colors", t("source_colors"), "mdi:palette")}
                        {sourceTab("photo", t("source_photo"), "mdi:image")}
                    </div>
                }

                {
                    !isBuiltin &&
                <div style={{display: "flex", gap: "1rem", alignItems: "center", marginTop: "1rem", flexWrap: "wrap"}}>
                    <div
                        className={"preset-picture"}
                        onClick={() => (source === "photo" || isBuiltin) && fileInput.current?.click()}
                        style={{
                            width: "160px", height: "100px", borderRadius: "12px", flex: "none",
                            cursor: source === "photo" || isBuiltin ? "pointer" : "default",
                            background: imageSrc ? `center / cover no-repeat url("${imageSrc}")` :
                                (fromColors && gradientPreview ? gradientPreview : "var(--secondary-background-color, rgba(127,127,127,0.15))"),
                            display: "flex", alignItems: "center", justifyContent: "center"
                        }}
                    >
                        {!imageSrc && !(fromColors && gradientPreview) && <ha-icon icon={"mdi:image-plus"} style={{"--mdc-icon-size": "36px", opacity: 0.6}}/>}
                    </div>
                    <div style={{display: "flex", flexDirection: "column", gap: "0.25rem", alignItems: "flex-start"}}>
                        {
                            source === "colors" && !isBuiltin ?
                                <div style={HINT}>{t("colors_picture_hint")}</div> :
                                <button className={"photo-choose"} style={BUTTON} onClick={() => fileInput.current?.click()}>
                                    {imageSrc ? t("photo_change") : t("photo_choose")}
                                </button>
                        }
                        {
                            preset && image &&
                            <button className={"photo-take-colors"} style={BUTTON} onClick={() => takeColors(count)}>
                                {t("photo_take_colors")}
                            </button>
                        }
                    </div>
                    <input
                        ref={fileInput}
                        className={"photo-file"}
                        type={"file"}
                        accept={"image/*"}
                        style={{display: "none"}}
                        onChange={(e) => onFile(e.target.files?.[0])}
                    />
                </div>
                }

                <div style={LABEL}>{t("palette_heading")}</div>
                <div style={{display: "flex", flexWrap: "wrap", gap: "0.6rem", alignItems: "center"}}>
                    {
                        colors.map((c, i) => (
                            <div key={"c" + i} style={{position: "relative"}}>
                                <button
                                    className={"palette-color"}
                                    title={t("palette_change")}
                                    aria-pressed={i === selected}
                                    onClick={() => setSelected(i)}
                                    style={{
                                        display: "block", width: "44px", height: "44px", borderRadius: "50%", cursor: "pointer", border: "none", padding: 0,
                                        background: rgbToHex(xyToRgb(c)),
                                        boxShadow: i === selected
                                            ? "0 0 0 2px var(--card-background-color, #fff), 0 0 0 4px var(--primary-color, #03a9f4)"
                                            : "0 0 0 2px var(--card-background-color, #fff), 0 0 0 3px var(--divider-color, #888)"
                                    }}
                                />
                                {
                                    colors.length > 1 &&
                                    <button
                                        className={"palette-remove"}
                                        title={t("palette_remove")}
                                        onClick={() => {
                                            changeColors(colors.filter((_, j) => j !== i));
                                            setSelected(Math.max(0, Math.min(selected, colors.length - 2)));
                                        }}
                                        style={{
                                            position: "absolute", top: "-6px", right: "-6px", width: "20px", height: "20px",
                                            borderRadius: "50%", border: "none", cursor: "pointer", fontSize: "13px", lineHeight: "20px", padding: 0,
                                            background: "var(--secondary-background-color, #555)", color: "var(--primary-text-color, #fff)"
                                        }}
                                    >×</button>
                                }
                            </div>
                        ))
                    }
                    {
                        colors.length < MAX_COLORS &&
                        <button
                            className={"palette-add"}
                            title={t("palette_add")}
                            onClick={() => {
                                const last = colors[colors.length - 1] ?? START_COLORS[0];
                                changeColors([...colors, {...last}]);
                                setSelected(colors.length);
                            }}
                            style={{
                                width: "44px", height: "44px", borderRadius: "50%", cursor: "pointer", fontSize: "22px",
                                border: "2px dashed var(--divider-color, #888)", background: "transparent", color: "var(--secondary-text-color, #aaa)"
                            }}
                        >+</button>
                    }
                </div>
                {
                    colors[selected] &&
                    <ColorEditor
                        t={t}
                        value={colors[selected]}
                        onChange={(xy) => {
                            const next = [...colors];
                            next[selected] = xy;
                            changeColors(next);
                        }}
                    />
                }
                {
                    pixels.current &&
                    <div style={{display: "flex", alignItems: "center", gap: "0.5rem", marginTop: "0.5rem", ...HINT}}>
                        {t("palette_count")}
                        {
                            [3, 4, 5, 6].map(n => (
                                <button
                                    key={"n" + n}
                                    className={"palette-count"}
                                    style={{...BUTTON, padding: "0.2rem 0.6rem", border: n === count ? "1px solid var(--primary-color)" : "1px solid transparent"}}
                                    onClick={() => {
                                        setCount(n);
                                        takeColors(n);
                                    }}
                                >{n}</button>
                            ))
                        }
                    </div>
                }
                <div style={{...HINT, marginTop: "0.35rem"}}>{t("palette_hint")}</div>

                {
                    !isBuiltin &&
                    <>
                        <div style={LABEL}>{t("name")}</div>
                        <input
                            className={"photo-name"}
                            type={"text"}
                            value={name}
                            onChange={(e) => setName(e.target.value)}
                            style={INPUT}
                        />
                        <div style={LABEL}>{t("category")}</div>
                        <select
                            className={"photo-category"}
                            value={categoryId}
                            onChange={(e) => setCategoryId(e.target.value)}
                            style={INPUT}
                        >
                            {!categories.some(c => c.name === t("my_presets")) && <option value={""}>{t("my_presets")}</option>}
                            {
                                categories
                                    .filter(c => c.custom || presets.some(p => p.categoryId === c.id && !p.hidden))
                                    .map(c => <option key={"cat_" + c.id} value={c.id}>{c.name}</option>)
                            }
                            <option value={NEW_CATEGORY}>{t("category_new")}</option>
                        </select>
                        {
                            categoryId === NEW_CATEGORY &&
                            <input
                                className={"photo-new-category"}
                                type={"text"}
                                placeholder={t("category_new_name")}
                                value={newCategory}
                                onChange={(e) => setNewCategory(e.target.value)}
                                style={{...INPUT, marginTop: "0.5rem"}}
                            />
                        }
                    </>
                }
                <div style={LABEL}>{t("preset_brightness")}: {brightness} %</div>
                <input
                    className={"photo-brightness"}
                    type={"range"}
                    min={1}
                    max={100}
                    value={brightness}
                    onChange={(e) => {
                        setBrightness(Number(e.target.value));
                        setBriChanged(true);
                    }}
                    style={{width: "100%"}}
                />

                {info && <div style={{marginTop: "0.75rem", ...HINT}}>{info}</div>}
                {error && <div style={{marginTop: "0.75rem", color: "var(--error-color, #db4437)"}}>{error}</div>}

                <div style={{display: "flex", flexWrap: "wrap", justifyContent: "flex-end", gap: "0.5rem", marginTop: "1.5rem"}}>
                    {
                        preset && !isBuiltin &&
                        <button className={"photo-delete"} style={{...BUTTON, color: "var(--error-color, #db4437)", marginRight: "auto"}} onClick={remove}>
                            {t("delete")}
                        </button>
                    }
                    {
                        isBuiltin &&
                        <button className={"preset-hide"} style={{...BUTTON, marginRight: preset?.overridden ? undefined : "auto"}} onClick={hide}>
                            {t("hide_preset")}
                        </button>
                    }
                    {
                        isBuiltin && preset?.overridden &&
                        <button className={"photo-reset"} style={{...BUTTON, marginRight: "auto"}} onClick={reset}>
                            {t("preset_reset")}
                        </button>
                    }
                    <button className={"photo-preview"} style={BUTTON} disabled={colors.length === 0} onClick={preview}>
                        {t("preview")}
                    </button>
                    <button className={"photo-cancel"} style={BUTTON} onClick={onClose}>
                        {t("cancel")}
                    </button>
                    <button
                        className={"photo-save"}
                        disabled={!canSave}
                        style={{
                            ...BUTTON,
                            background: "var(--primary-color, #03a9f4)",
                            color: "var(--text-primary-color, #fff)",
                            opacity: canSave ? 1 : 0.5
                        }}
                        onClick={save}
                    >
                        {t("save")}
                    </button>
                </div>
            </div>
        </HaDialog>
    );
};
