
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
    user_hidden?: boolean, // hidden by the user in the panel (can be shown again)
    generated?: boolean, // picture made from the colors
    replacedBy?: string,
    music?: boolean
}
