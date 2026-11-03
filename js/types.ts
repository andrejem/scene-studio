
export type Category = {
    id: string,
    name: string,
    custom?: boolean
}

export type Preset = {
    id: string,
    categoryId: string,
    name: string,
    img?: string,
    img_url?: string, // signed URL for pictures of the user's own presets
    bri: number,
    lights: Array<{x: number, y: number}>,
    custom?: boolean,
    overridden?: boolean,
    hidden?: boolean,
    replacedBy?: string,
    music?: boolean
}
