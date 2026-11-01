// Added by andrejem (2026): picks the dominant colors of a photo for a light preset and converts
// between sRGB and CIE xy (the color space the presets use).

export type RGB = [number, number, number];
export type XY = {x: number, y: number};

type Lab = [number, number, number];

const toLinear = (c: number) => {
    const v = c / 255;
    return v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
};
const fromLinear = (v: number) => {
    const c = v <= 0.0031308 ? 12.92 * v : 1.055 * Math.pow(v, 1 / 2.4) - 0.055;
    return Math.max(0, Math.min(255, Math.round(c * 255)));
};

function rgbToXyz([r, g, b]: RGB): [number, number, number] {
    const R = toLinear(r), G = toLinear(g), B = toLinear(b);
    return [
        R * 0.4124 + G * 0.3576 + B * 0.1805,
        R * 0.2126 + G * 0.7152 + B * 0.0722,
        R * 0.0193 + G * 0.1192 + B * 0.9505
    ];
}

function rgbToLab(rgb: RGB): Lab {
    const [X, Y, Z] = rgbToXyz(rgb);
    const f = (t: number) => t > 0.008856 ? Math.cbrt(t) : 7.787 * t + 16 / 116;
    const fx = f(X / 0.95047), fy = f(Y), fz = f(Z / 1.08883);
    return [116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)];
}

function labToRgb([L, a, b]: Lab): RGB {
    const fy = (L + 16) / 116, fx = fy + a / 500, fz = fy - b / 200;
    const inv = (t: number) => t * t * t > 0.008856 ? t * t * t : (t - 16 / 116) / 7.787;
    const X = inv(fx) * 0.95047, Y = inv(fy), Z = inv(fz) * 1.08883;
    const R = X * 3.2406 + Y * -1.5372 + Z * -0.4986;
    const G = X * -0.9689 + Y * 1.8758 + Z * 0.0415;
    const B = X * 0.0557 + Y * -0.2040 + Z * 1.0570;
    return [fromLinear(R), fromLinear(G), fromLinear(B)];
}

export function rgbToXy(rgb: RGB): XY {
    const [X, Y, Z] = rgbToXyz(rgb);
    const sum = X + Y + Z;
    if (sum <= 0) {
        return {x: 0.3127, y: 0.329}; // white point
    }
    return {x: Math.round(X / sum * 10000) / 10000, y: Math.round(Y / sum * 10000) / 10000};
}

/** Color of an xy point at full brightness, for showing a preset color on screen. */
export function xyToRgb({x, y}: XY): RGB {
    const Y = 1;
    const X = (Y / y) * x;
    const Z = (Y / y) * (1 - x - y);
    let R = X * 3.2406 - Y * 1.5372 - Z * 0.4986;
    let G = -X * 0.9689 + Y * 1.8758 + Z * 0.0415;
    let B = X * 0.0557 - Y * 0.2040 + Z * 1.0570;
    R = Math.max(0, R); G = Math.max(0, G); B = Math.max(0, B);
    const max = Math.max(R, G, B, 1e-6);
    return [fromLinear(R / max), fromLinear(G / max), fromLinear(B / max)];
}

export function rgbToHex([r, g, b]: RGB): string {
    return "#" + [r, g, b].map(v => v.toString(16).padStart(2, "0")).join("");
}

export function hexToRgb(hex: string): RGB {
    const v = parseInt(hex.replace("#", ""), 16);
    return [(v >> 16) & 255, (v >> 8) & 255, v & 255];
}

function rgbToHsv([r, g, b]: RGB): [number, number, number] {
    const R = r / 255, G = g / 255, B = b / 255;
    const max = Math.max(R, G, B), min = Math.min(R, G, B), d = max - min;
    let h = 0;
    if (d > 0) {
        if (max === R) h = ((G - B) / d) % 6;
        else if (max === G) h = (B - R) / d + 2;
        else h = (R - G) / d + 4;
        h *= 60;
        if (h < 0) h += 360;
    }
    return [h, max === 0 ? 0 : d / max, max];
}

function hsvToRgb([h, s, v]: [number, number, number]): RGB {
    const c = v * s, x = c * (1 - Math.abs(((h / 60) % 2) - 1)), m = v - c;
    const [r, g, b] =
        h < 60 ? [c, x, 0] : h < 120 ? [x, c, 0] : h < 180 ? [0, c, x] :
            h < 240 ? [0, x, c] : h < 300 ? [x, 0, c] : [c, 0, x];
    return [Math.round((r + m) * 255), Math.round((g + m) * 255), Math.round((b + m) * 255)];
}

/** Lights show colors at their own brightness: full value, pale colors a bit more saturated. */
function forLight(rgb: RGB): RGB {
    const [h, s] = rgbToHsv(rgb);
    // near white stays white (warm/cool white photos), everything else gets clearly colored
    const sat = s < 0.12 ? s : Math.min(1, Math.max(s * 1.35, 0.6));
    return hsvToRgb([h, sat, 1]);
}

const dist2 = (a: Lab, b: Lab) => (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2;

function kmeans(points: Array<Lab>, k: number): Array<{center: Lab, size: number}> {
    // deterministic k-means++ (same photo = same palette)
    let seed = points.length * 9301 + 49297;
    const rand = () => {
        seed = (seed * 9301 + 49297) % 233280;
        return seed / 233280;
    };
    const centers: Array<Lab> = [points[Math.floor(rand() * points.length)]];
    while (centers.length < k) {
        const d = points.map(p => Math.min(...centers.map(c => dist2(p, c))));
        const total = d.reduce((a, v) => a + v, 0);
        if (total === 0) break;
        let r = rand() * total, i = 0;
        while (r > d[i] && i < d.length - 1) {
            r -= d[i];
            i++;
        }
        centers.push(points[i]);
    }
    const assign = new Array(points.length).fill(0);
    for (let iter = 0; iter < 12; iter++) {
        let moved = false;
        points.forEach((p, i) => {
            let best = 0, bestD = Infinity;
            centers.forEach((c, j) => {
                const dd = dist2(p, c);
                if (dd < bestD) {
                    bestD = dd;
                    best = j;
                }
            });
            if (assign[i] !== best) {
                assign[i] = best;
                moved = true;
            }
        });
        const sums = centers.map(() => [0, 0, 0, 0]);
        points.forEach((p, i) => {
            const s = sums[assign[i]];
            s[0] += p[0]; s[1] += p[1]; s[2] += p[2]; s[3]++;
        });
        sums.forEach((s, j) => {
            if (s[3] > 0) centers[j] = [s[0] / s[3], s[1] / s[3], s[2] / s[3]];
        });
        if (!moved && iter > 0) break;
    }
    const sizes = centers.map(() => 0);
    assign.forEach(a => sizes[a]++);
    return centers.map((center, j) => ({center, size: sizes[j]})).filter(c => c.size > 0);
}

/**
 * Dominant colors of an image for lights: no greys, no near black or near white, distinct colors,
 * colorful areas preferred over large dull ones. `pixels` is RGBA data (e.g. from a canvas).
 */
export function extractPalette(pixels: Uint8ClampedArray | Uint8Array, count: number): Array<RGB> {
    const all: Array<Lab> = [];
    const step = Math.max(1, Math.floor(pixels.length / 4 / 6000));
    for (let i = 0; i < pixels.length; i += 4 * step) {
        if (pixels[i + 3] < 128) continue;
        all.push(rgbToLab([pixels[i], pixels[i + 1], pixels[i + 2]]));
    }
    const chroma = (p: Lab) => Math.hypot(p[1], p[2]);
    let points = all.filter(p => p[0] > 12 && p[0] < 94 && chroma(p) > 14);
    if (points.length < 60) {
        points = all.filter(p => p[0] > 6 && p[0] < 97 && chroma(p) > 5);
    }
    if (points.length < 10) {
        points = all;
    }
    if (points.length === 0) {
        return [];
    }
    const clusters = kmeans(points, Math.min(12, Math.max(count * 2, 6)))
        .map(c => ({...c, score: c.size * (0.4 + Math.min(chroma(c.center), 80) / 50)}))
        .sort((a, b) => b.score - a.score);

    const picked: Array<Lab> = [];
    // rather fewer colors than near duplicates (one-colored photo = one or two colors)
    for (const minDist of [24, 16]) {
        for (const c of clusters) {
            if (picked.length >= count) break;
            if (picked.some(p => Math.sqrt(dist2(p, c.center)) < minDist)) continue;
            picked.push(c.center);
        }
        if (picked.length >= count) break;
    }
    return picked.map(lab => forLight(labToRgb(lab)));
}
