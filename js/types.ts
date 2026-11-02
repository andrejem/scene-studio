
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
    bri: number,
    lights: Array<{x: number, y: number}>,
    custom?: boolean,
    overridden?: boolean,
    hidden?: boolean,
    replacedBy?: string,
    music?: boolean
}
