// Modified by andrejem (2026): optional action icon (e.g. edit) on tiles, on the left when the tile
// also has the favorite star; badge (e.g. "dynamic"), active state and a dashed "new" tile

import React from "react";
import HaIconButton from "./hass/building_blocks/HaIconButton";
import HaIcon from "./hass/building_blocks/HaIcon";

export const PresetTile :React.FunctionComponent<{
    id: string,
    name: string,
    imgSrc?: string
    onClick?: (name: string) => void

    onFavClick?: (name: string) => void
    isFav?: boolean

    actionIcon?: string
    actionLabel?: string
    onActionClick?: (name: string) => void

    badge?: string,
    badgeIcon?: string
    active?: boolean
    small?: boolean
    title?: string
}> = ({
    id,
    name,
    imgSrc,
    onClick,

    onFavClick,
    isFav,

    actionIcon,
    actionLabel,
    onActionClick,

    badge,
    badgeIcon,
    active,
    small,
    title
}): React.JSX.Element => {
    // These two variables are _somehow_ required because without the change in key, the icon won't change even though we get rerendered ??
    const favedIcon = <HaIconButton
        key={"id_fav"}
        icon={"mdi:star"}
        onClick={() => {
            onFavClick?.(id);
        }}

        size={36}
        iconSize={22}
    />;
    const unFavedIcon = <HaIconButton
        key={"id_unfav"}
        icon={"mdi:star-outline"}
        onClick={() => {
            onFavClick?.(id);
        }}

        size={36}
        iconSize={22}
    />;

    return (
        <div
            className={"tile" + (active ? " active" : "") + (small ? " small" : "")}
            role={"button"}
            tabIndex={0}
            title={title}
            aria-label={name}
            onClick={() => {
                onClick?.(id);
            }}
            onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    onClick?.(id);
                }
            }}
        >
            {
                actionIcon && onActionClick &&
                <div
                    className={"tile-top-icon-container tile-action"}
                    style={onFavClick ? {left: "2px", right: "auto"} : undefined}
                    title={actionLabel}
                >
                    <HaIconButton
                        key={"id_action"}
                        icon={actionIcon}
                        onClick={() => {
                            onActionClick(id);
                        }}

                        size={36}
                        iconSize={20}
                    />
                </div>
            }
            {
                onFavClick &&
                <div
                    className={"tile-top-icon-container"}
                >
                    {
                        isFav ? favedIcon : unFavedIcon
                    }
                </div>
            }
            {
                badge &&
                <span className={"tile-badge"} style={actionIcon && onFavClick ? {left: "40px"} : undefined}>
                    <HaIcon icon={badgeIcon ?? "mdi:motion-play-outline"} size={14}/>
                    {badge}
                </span>
            }

            <div
                className={"tile-content"}
            >
                {
                    imgSrc ?

                        <img
                            src={imgSrc}
                            className={"tile-bg-img"}
                            loading={"lazy"}
                            alt={""}
                        />
                        :
                        <div
                            className={"tile-bg-no-img"}
                        >
                        </div>

                }
                <div
                    className={"tile-text-bg"}
                ></div>
                <p
                    className={"tile-text"}
                >
                    {name}
                </p>
                {
                    active &&
                    <span className={"tile-check"}><HaIcon icon={"mdi:check-circle"} size={20}/></span>
                }
            </div>
        </div>
    );
};

export const NewTile: React.FunctionComponent<{
    label: string,
    icon: string,
    onClick: () => void,
    small?: boolean,
    className?: string
}> = ({label, icon, onClick, small, className}) => {
    return (
        <button className={"tile tile-new" + (small ? " small" : "") + " " + (className ?? "")} onClick={onClick}>
            <HaIcon icon={icon} size={22}/>
            <span>{label}</span>
        </button>
    );
};
