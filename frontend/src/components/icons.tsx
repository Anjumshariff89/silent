// Small inline stroke icons (no icon library dependency). Decorative: aria-hidden by default.
import { useId, type SVGProps } from "react";

type P = SVGProps<SVGSVGElement> & { size?: number };

function Svg({ size = 18, children, ...rest }: P & { children: React.ReactNode }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8}
      strokeLinecap="round" strokeLinejoin="round" aria-hidden {...rest}>{children}</svg>
  );
}

export const IconShield = (p: P) => <Svg {...p}><path d="M12 3l7 3v5c0 4.5-3 8.3-7 10-4-1.7-7-5.5-7-10V6l7-3z" /></Svg>;
export const IconShieldCheck = (p: P) => <Svg {...p}><path d="M12 3l7 3v5c0 4.5-3 8.3-7 10-4-1.7-7-5.5-7-10V6l7-3z" /><path d="M9 12l2 2 4-4" /></Svg>;
export const IconHome = (p: P) => <Svg {...p}><path d="M4 11l8-7 8 7" /><path d="M6 10v10h12V10" /></Svg>;
export const IconGrid = (p: P) => <Svg {...p}><rect x="4" y="4" width="7" height="7" rx="1.5" /><rect x="13" y="4" width="7" height="7" rx="1.5" /><rect x="4" y="13" width="7" height="7" rx="1.5" /><rect x="13" y="13" width="7" height="7" rx="1.5" /></Svg>;
export const IconCheckCircle = (p: P) => <Svg {...p}><circle cx="12" cy="12" r="8.5" /><path d="M8.5 12l2.5 2.5 4.5-5" /></Svg>;
export const IconAnchor = (p: P) => <Svg {...p}><circle cx="12" cy="5.5" r="2" /><path d="M12 7.5V20" /><path d="M5 13a7 7 0 0014 0" /><path d="M8.5 11h7" /></Svg>;
export const IconList = (p: P) => <Svg {...p}><path d="M9 6h11M9 12h11M9 18h11" /><circle cx="4.5" cy="6" r="1" /><circle cx="4.5" cy="12" r="1" /><circle cx="4.5" cy="18" r="1" /></Svg>;
export const IconCpu = (p: P) => <Svg {...p}><rect x="6" y="6" width="12" height="12" rx="2" /><path d="M9.5 9.5h5v5h-5zM9 2.5v3M15 2.5v3M9 18.5v3M15 18.5v3M2.5 9h3M2.5 15h3M18.5 9h3M18.5 15h3" /></Svg>;
export const IconLink = (p: P) => <Svg {...p}><path d="M10 14a4 4 0 005.66 0l3-3a4 4 0 00-5.66-5.66l-1 1" /><path d="M14 10a4 4 0 00-5.66 0l-3 3a4 4 0 005.66 5.66l1-1" /></Svg>;
export const IconBell = (p: P) => <Svg {...p}><path d="M6 16V11a6 6 0 1112 0v5l1.5 2h-15L6 16z" /><path d="M10 20a2 2 0 004 0" /></Svg>;
export const IconTree = (p: P) => <Svg {...p}><rect x="9.5" y="3" width="5" height="4" rx="1" /><rect x="3" y="17" width="5" height="4" rx="1" /><rect x="16" y="17" width="5" height="4" rx="1" /><path d="M12 7v4M5.5 17v-3h13v3M12 11v3" /></Svg>;
export const IconCube = (p: P) => <Svg {...p}><path d="M12 3l8 4.5v9L12 21l-8-4.5v-9L12 3z" /><path d="M12 12l8-4.5M12 12L4 7.5M12 12v9" /></Svg>;
export const IconClock = (p: P) => <Svg {...p}><circle cx="12" cy="12" r="8.5" /><path d="M12 7.5V12l3 2" /></Svg>;
export const IconFile = (p: P) => <Svg {...p}><path d="M14 3H7a2 2 0 00-2 2v14a2 2 0 002 2h10a2 2 0 002-2V8l-5-5z" /><path d="M14 3v5h5M9 13h6M9 17h4" /></Svg>;
export const IconLogout = (p: P) => <Svg {...p}><path d="M15 4h3a2 2 0 012 2v12a2 2 0 01-2 2h-3" /><path d="M10 16l-4-4 4-4M6 12h10" /></Svg>;
export const IconMenu = (p: P) => <Svg {...p}><path d="M4 7h16M4 12h16M4 17h16" /></Svg>;
export const IconX = (p: P) => <Svg {...p}><path d="M6 6l12 12M18 6L6 18" /></Svg>;
export const IconCopy = (p: P) => <Svg {...p}><rect x="9" y="9" width="11" height="11" rx="2" /><path d="M5 15V6a2 2 0 012-2h9" /></Svg>;
export const IconCheck = (p: P) => <Svg {...p}><path d="M5 12.5l4.5 4.5L19 7.5" /></Svg>;
export const IconAlert = (p: P) => <Svg {...p}><path d="M12 4l9 16H3l9-16z" /><path d="M12 10v4M12 17.5v.5" /></Svg>;
export const IconInbox = (p: P) => <Svg {...p}><path d="M4 13l2.5-7h11L20 13v6H4v-6z" /><path d="M4 13h5l1 2h4l1-2h5" /></Svg>;
export const IconUser = (p: P) => <Svg {...p}><circle cx="12" cy="8.5" r="3.5" /><path d="M5 20a7 7 0 0114 0" /></Svg>;
export const IconHash = (p: P) => <Svg {...p}><path d="M5 9h14M5 15h14M10 4L8 20M16 4l-2 16" /></Svg>;
export const IconActivity = (p: P) => <Svg {...p}><path d="M3 12h4l3-7 4 14 3-7h4" /></Svg>;

/** Brand mark: a shield made of linked blocks (hash chain). */
export function Logo({ size = 32 }: { size?: number }) {
  // Unique gradient id per instance: with a shared id, a copy inside a hidden element (display:none) would leave
  // the visible copy without its gradient.
  const gid = `lg-shield-${useId().replace(/:/g, "")}`;
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden>
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#38bdf8" /><stop offset="1" stopColor="#10b981" />
        </linearGradient>
      </defs>
      <path d="M16 2.5l11 4.5v7.5c0 7-4.7 12.6-11 15-6.3-2.4-11-8-11-15V7l11-4.5z" fill={`url(#${gid})`} opacity="0.18" />
      <path d="M16 2.5l11 4.5v7.5c0 7-4.7 12.6-11 15-6.3-2.4-11-8-11-15V7l11-4.5z" fill="none" stroke={`url(#${gid})`} strokeWidth="1.6" />
      <rect x="10" y="9.5" width="5" height="5" rx="1.2" fill="#38bdf8" />
      <rect x="17" y="13.5" width="5" height="5" rx="1.2" fill="#22d3ee" />
      <rect x="10" y="17.5" width="5" height="5" rx="1.2" fill="#10b981" />
      <path d="M15 12h2.5v1.5M17 18.5h-2" stroke="#e2e8f0" strokeWidth="1.2" fill="none" strokeLinecap="round" />
    </svg>
  );
}
