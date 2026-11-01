// Modified by andrejem (2026): heading also as headerTitle (ha-dialog of Home Assistant 2026.x)
import React, {Component, ReactNode} from "react";

interface HaDialogProps {
    open: boolean;
    onClose: () => void
    heading?: string,
    children?: ReactNode;
}

class HaDialog extends Component<HaDialogProps> {
    private elementRef: React.RefObject<HTMLInputElement | null>;

    constructor(props: HaDialogProps) {
        super(props);

        this.elementRef = React.createRef();
    }

    handleClosed = () => {
        this.props.onClose();
    };

    componentDidMount() {
        this.elementRef.current!.addEventListener("closed", this.handleClosed);
    }

    componentWillUnmount() {
        this.elementRef.current!.removeEventListener("closed", this.handleClosed);
    }

    render() {
        return (
            <ha-dialog
                ref={this.elementRef}
                open={this.props.open}
                heading={this.props.heading}
                headerTitle={this.props.heading}
            >
                {this.props.children}
            </ha-dialog>
        );
    }

}

export default HaDialog;
