// Added by andrejem (2026): color picker for preset colors with two tabs like the Hue app:
// "Color" (hue and saturation at full brightness) and "White" (color temperature, warm to cool).
// Works on CIE xy, the color space of the presets, so a white tone is stored exactly.

import React, {useEffect, useRef, useState} from "react";
import {Translate} from "../i18n";
import {XY, hsvToRgb, kelvinToXy, rgbToHex, rgbToHsv, rgbToXy, xyToKelvin, xyToRgb} from "../palette";

const KELVIN_MIN = 2000;
const KELVIN_MAX = 6500;
const WHITE_PRESETS = [2200, 2700, 3000, 4000, 5000, 6500];

const hueGradient = "linear-gradient(90deg, #f00, #ff0 17%, #0f0 33%, #0ff 50%, #00f 67%, #f0f 83%, #f00)";
const kelvinGradient = "linear-gradient(90deg, " +
    [2000, 2700, 3500, 4500, 5500, 6500].map(k => rgbToHex(xyToRgb(kelvinToXy(k)))).join(", ") + ")";

export const COLOR_EDITOR_CSS = `
.sp-color-editor input[type=range] {
    -webkit-appearance: none; appearance: none; width: 100%; height: 14px; border-radius: 7px; margin: 10px 0 4px;
    outline: none; cursor: pointer;
}
.sp-color-editor input[type=range]::-webkit-slider-thumb {
    -webkit-appearance: none; appearance: none; width: 24px; height: 24px; border-radius: 50%;
    background: #fff; border: 2px solid rgba(0,0,0,.35); box-shadow: 0 1px 4px rgba(0,0,0,.4);
}
.sp-color-editor input[type=range]::-moz-range-thumb {
    width: 22px; height: 22px; border-radius: 50%; background: #fff; border: 2px solid rgba(0,0,0,.35);
}
`;

type Props = {
    t: Translate,
    value: XY,
    onChange: (xy: XY) => void,
};

export const ColorEditor: React.FunctionComponent<Props> = ({t, value, onChange}): React.JSX.Element => {
    const kelvinOf = xyToKelvin(value);
    const [tab, setTab] = useState<"color" | "white">(kelvinOf !== null ? "white" : "color");
    const [hsv, setHsv] = useState<[number, number, number]>(() => rgbToHsv(xyToRgb(value)));
    const [kelvin, setKelvin] = useState<number>(kelvinOf ?? 2700);
    const emitted = useRef<XY | null>(null);
    const emit = (xy: XY) => {
        emitted.current = xy;
        onChange(xy);
    };

    // another color of the palette was chosen (not a change made here: hue stays when going to white)
    useEffect(() => {
        if (emitted.current && emitted.current.x === value.x && emitted.current.y === value.y) {
            return;
        }
        const k = xyToKelvin(value);
        setHsv(rgbToHsv(xyToRgb(value)));
        if (k !== null) {
            setKelvin(k);
        }
        setTab(k !== null ? "white" : "color");
    }, [value.x, value.y]); // eslint-disable-line react-hooks/exhaustive-deps

    const setColor = (h: number, s: number) => {
        setHsv([h, s, 1]);
        emit(rgbToXy(hsvToRgb([h, s, 1])));
    };
    const setWhite = (k: number) => {
        setKelvin(k);
        emit(kelvinToXy(k));
    };

    const pure = rgbToHex(hsvToRgb([hsv[0], 1, 1]));
    const tabStyle = (active: boolean): React.CSSProperties => ({
        flex: 1, border: "none", padding: "6px 10px", borderRadius: "9px", cursor: "pointer", font: "inherit",
        background: active ? "var(--card-background-color, #fff)" : "transparent",
        color: active ? "var(--primary-text-color)" : "var(--secondary-text-color)",
        boxShadow: active ? "0 1px 3px rgba(0,0,0,.25)" : "none",
    });

    return (
        <div className={"sp-color-editor"} style={{marginTop: "0.75rem"}}>
            <div style={{display: "flex", gap: "4px", padding: "3px", borderRadius: "12px", background: "var(--secondary-background-color, rgba(127,127,127,.15))"}}>
                <button className={"color-tab-color"} style={tabStyle(tab === "color")} onClick={() => {
                    setTab("color");
                    setColor(hsv[0], Math.max(hsv[1], 0.6));
                }}>{t("color_tab")}</button>
                <button className={"color-tab-white"} style={tabStyle(tab === "white")} onClick={() => {
                    setTab("white");
                    setWhite(kelvin);
                }}>{t("white_tab")}</button>
            </div>
            {
                tab === "color" ?
                    <div>
                        <input
                            className={"color-hue"}
                            type={"range"} min={0} max={359} step={1}
                            aria-label={t("hue")}
                            value={Math.round(hsv[0])}
                            onChange={(e) => setColor(Number(e.target.value), hsv[1])}
                            style={{background: hueGradient}}
                        />
                        <input
                            className={"color-saturation"}
                            type={"range"} min={0} max={100} step={1}
                            aria-label={t("saturation")}
                            value={Math.round(hsv[1] * 100)}
                            onChange={(e) => setColor(hsv[0], Number(e.target.value) / 100)}
                            style={{background: `linear-gradient(90deg, #fff, ${pure})`}}
                        />
                    </div> :
                    <div>
                        <input
                            className={"color-kelvin"}
                            type={"range"} min={KELVIN_MIN} max={KELVIN_MAX} step={50}
                            aria-label={t("white_tab")}
                            value={kelvin}
                            onChange={(e) => setWhite(Number(e.target.value))}
                            style={{background: kelvinGradient}}
                        />
                        <div style={{display: "flex", justifyContent: "space-between", fontSize: "0.8rem", opacity: 0.8}}>
                            <span>{t("white_warm")}</span><span>{kelvin} K</span><span>{t("white_cool")}</span>
                        </div>
                        <div style={{display: "flex", gap: "6px", flexWrap: "wrap", marginTop: "0.5rem", marginBottom: "0.75rem"}}>
                            {WHITE_PRESETS.map(k => (
                                <button
                                    key={"k" + k}
                                    className={"color-kelvin-preset"}
                                    onClick={() => setWhite(k)}
                                    style={{
                                        display: "flex", alignItems: "center", gap: "6px", padding: "4px 10px", borderRadius: "999px",
                                        border: k === kelvin ? "1px solid var(--primary-color)" : "1px solid var(--divider-color, #888)",
                                        background: "transparent", color: "var(--primary-text-color)", cursor: "pointer", font: "inherit", fontSize: "0.82rem"
                                    }}
                                >
                                    <span style={{width: "12px", height: "12px", borderRadius: "50%", background: rgbToHex(xyToRgb(kelvinToXy(k)))}}/>
                                    {k} K
                                </button>
                            ))}
                        </div>
                    </div>
            }
        </div>
    );
};
