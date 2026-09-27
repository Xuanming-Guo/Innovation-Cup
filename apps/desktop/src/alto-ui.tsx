import { useEffect, useRef, type ReactNode } from "react";
import altoLogo from "../../../docs/design/LOGO.jpeg";
export type IconName = "home" | "projects" | "calendar" | "people" | "connections" | "bell" | "settings" | "document" | "mic" | "send" | "close" | "left" | "right" | "collapse" | "expand" | "search" | "check" | "clock" | "lock" | "info" | "flag" | "plus" | "minus" | "fit" | "simulation" | "logout";
const paths: Record<IconName, ReactNode> = {
    home: <>
<path d="m3 10 9-7 9 7v11h-6v-7H9v7H3Z"/>
</>,
    projects: <path d="M3 6V4h6l3 3h9v14H3Z"/>,
    calendar: <>
<rect x="3" y="5" width="18" height="16" rx="2"/>
<path d="M7 3v5m10-5v5M3 11h18"/>
</>,
    people: <>
<circle cx="12" cy="7" r="4"/>
<path d="M4 21v-3a8 5 0 0 1 16 0v3Z"/>
</>,
    connections: <>
<circle cx="12" cy="5" r="3"/>
<circle cx="5" cy="19" r="3"/>
<circle cx="19" cy="19" r="3"/>
<path d="m10.5 8-4 8m7-8 4 8"/>
</>,
    bell: <>
<path d="M5 17h14l-2-4V9a5 5 0 0 0-10 0v4ZM10 21h4"/>
</>,
    settings: <>
<path d="m9 3-1 3-3 1 1 3-2 2 2 2-1 3 3 1 1 3h5l1-3 3-1-1-3 2-2-2-2 1-3-3-1-1-3Z"/>
<circle cx="11.5" cy="12" r="3"/>
</>,
    document: <>
<path d="M5 3h9l5 5v13H5Zm9 0v6h5M8 13h8m-8 4h6"/>
</>,
    mic: <>
<rect x="9" y="3" width="6" height="12" rx="3"/>
<path d="M5 10v2a7 7 0 0 0 14 0v-2M12 19v3m-4 0h8"/>
</>,
    send: <path d="m4 3 17 9-17 9 4-9Zm4 9h13"/>,
    close: <path d="m6 6 12 12M6 18 18 6"/>,
    left: <path d="m15 5-7 7 7 7"/>, right: <path d="m9 5 7 7-7 7"/>,
    collapse: <path d="m13 6-6 6 6 6m6-12-6 6 6 6"/>, expand: <path d="m5 6 6 6-6 6m6-12 6 6-6 6"/>,
    search: <>
<circle cx="10" cy="10" r="7"/>
<path d="m15 15 6 6"/>
</>,
    check: <path d="m5 12 5 5L20 6"/>, clock: <>
<circle cx="12" cy="12" r="9"/>
<path d="M12 6v6l4 3"/>
</>,
    lock: <>
<rect x="5" y="10" width="14" height="11" rx="2"/>
<path d="M8 10V7a4 4 0 0 1 8 0v3m-4 4v3"/>
</>,
    info: <>
<circle cx="12" cy="12" r="9"/>
<path d="M12 11v6m0-10v1"/>
</>,
    flag: <path d="M5 22V3l7 2 7-2v11l-7 2-7-2"/>,
    plus: <path d="M12 5v14M5 12h14"/>, minus: <path d="M5 12h14"/>,
    fit: <path d="M9 3H3v6m12-6h6v6M3 15v6h6m12-6v6h-6"/>,
    simulation: <>
<path d="M8 3h8m-6 0v7L4 20h16l-6-10V3M7 16h10"/>
</>,
    logout: <>
<path d="M10 3H3v18h7m4-14 5 5-5 5m-7-5h12"/>
</>,
};
export function Icon({ name, size = 24 }: {
    name: IconName;
    size?: number;
}) { return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>; }
export function AltoLogo({ compact = false }: {
    compact?: boolean;
}) { return <span className={`alto-logo ${compact ? "compact" : ""}`} role="img" aria-label="ALTO"><svg viewBox="70 500 1110 290" aria-hidden="true" style={{ overflow: "hidden", mixBlendMode: "multiply" }}><image href={altoLogo} width="1280" height="1280" /></svg>
</span>; }
export function IconButton({ icon, label, onClick, disabled = false, className = "" }: {
    icon: IconName;
    label: string;
    onClick: () => void;
    disabled?: boolean;
    className?: string;
}) { return <button type="button" className={`alto-icon-button ${className}`} onClick={onClick} title={label} aria-label={label} disabled={disabled}>
<Icon name={icon}/>
</button>; }
export function Badge({ children, tone = "neutral" }: {
    children: ReactNode;
    tone?: string;
}) { return <span className={`alto-badge ${tone}`}>{children}</span>; }
export function EmptyState({ title, children, action }: {
    title: string;
    children?: ReactNode;
    action?: ReactNode;
}) { return <section className="alto-empty">
<Icon name="document" size={30}/>
<h3>{title}</h3>{children && <p>{children}</p>}{action}</section>; }
export function ErrorNotice({ error, retry }: {
    error: string | null;
    retry?: () => void;
}) { return error ? <div className="alto-error" role="alert">
<Icon name="info" size={18}/>
<span>{error}</span>{retry && <button onClick={retry}>Try again</button>}</div> : null; }
export function Loading({ label = "Loading your workspace…" }: {
    label?: string;
}) { return <div className="alto-loading" role="status">
<span />{label}</div>; }
export function PageHeading({ eyebrow, title, subtitle, actions }: {
    eyebrow?: ReactNode;
    title: ReactNode;
    subtitle?: ReactNode;
    actions?: ReactNode;
}) { return <header className="alto-page-heading">
<div>{eyebrow && <div className="alto-eyebrow">{eyebrow}</div>}<h1>{title}</h1>{subtitle && <p>{subtitle}</p>}</div>{actions && <div className="alto-heading-actions">{actions}</div>}</header>; }
export function Modal({ title, children, onClose, wide = false }: {
    title: string;
    children: ReactNode;
    onClose: () => void;
    wide?: boolean;
}) {
    const container = useRef<HTMLDivElement>(null);
    const closeRef = useRef(onClose);
    useEffect(() => { closeRef.current = onClose; }, [onClose]);
    useEffect(() => {
        const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
        const node = container.current;
        node?.focus();
        const key = (event: KeyboardEvent) => {
            if (event.key === "Escape") {
                event.preventDefault();
                closeRef.current();
            }
            if (event.key !== "Tab" || !node)
                return;
            const elements = Array.from(node.querySelectorAll<HTMLElement>("button:not(:disabled),a[href],input:not(:disabled),textarea:not(:disabled),select:not(:disabled),[tabindex='0']"));
            const first = elements[0], last = elements.at(-1);
            if (!first) {
                event.preventDefault();
                return;
            }
            if (event.shiftKey && (document.activeElement === first || document.activeElement === node)) {
                event.preventDefault();
                last?.focus();
            }
            else if (!event.shiftKey && document.activeElement === last) {
                event.preventDefault();
                first.focus();
            }
        };
        document.addEventListener("keydown", key);
        return () => { document.removeEventListener("keydown", key); previous?.focus(); };
    }, []);
    return <div className="alto-modal-backdrop">
<div ref={container} role="dialog" aria-modal="true" aria-label={title} tabIndex={-1} className={`alto-modal ${wide ? "wide" : ""}`}>
<header>
<h2>{title}</h2>
<IconButton icon="close" label="Close dialog" onClick={onClose}/>
</header>{children}</div>
</div>;
}
