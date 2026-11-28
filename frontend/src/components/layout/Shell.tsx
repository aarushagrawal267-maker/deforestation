import clsx from "clsx";
import {
  BookOpen,
  Boxes,
  Database,
  FlaskConical,
  GitCompareArrows,
  History,
  LayoutDashboard,
  Map as MapIcon,
  Satellite,
  ScanSearch,
  Target,
  Trees,
} from "lucide-react";
import { useEffect, type ReactNode } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { useAOIs, useExperiments, useJobs, useSettings } from "../../api/hooks";
import { useApp } from "../../stores/app";
import { fmtNum } from "../../lib/format";

const NAV = [
  { to: "/", label: "Overview", icon: LayoutDashboard },
  { to: "/map", label: "Forest map", icon: MapIcon },
  { to: "/explorer", label: "Image explorer", icon: Satellite },
  { to: "/segmentation", label: "Segmentation", icon: Trees },
  { to: "/change", label: "Change detection", icon: GitCompareArrows },
  { to: "/investigate", label: "Investigation", icon: ScanSearch },
  { to: "/datasets", label: "Datasets", icon: Database },
  { to: "/lab", label: "Model lab", icon: FlaskConical },
  { to: "/evaluation", label: "Evaluation", icon: Target },
  { to: "/history", label: "History", icon: History },
  { to: "/docs", label: "Research and docs", icon: BookOpen },
];

function Logo() {
  return (
    <div className="flex items-center gap-3 px-3 pb-6 pt-4">
      <svg viewBox="0 0 32 32" className="h-8 w-8 shrink-0" aria-hidden>
        <rect width="32" height="32" rx="8" fill="#202322" stroke="#3b3f3d" />
        <path d="M16 6c4.6 4.6 6.5 8.3 6.5 11.8a6.5 6.5 0 0 1-13 0C9.5 14.3 11.4 10.6 16 6z" fill="#3faf86" />
        <path d="M16 12.5v13" stroke="#121413" strokeWidth="1.8" strokeLinecap="round" />
        <path d="M16 18l3-2.4M16 21.5l-3-2.4" stroke="#121413" strokeWidth="1.4" strokeLinecap="round" />
      </svg>
      <div className="hidden min-w-0 xl:block">
        <div className="font-display text-[18px] leading-none font-medium">Sylva</div>
        <div className="mt-1 whitespace-nowrap text-[11px] text-muted">Forest change intelligence</div>
      </div>
    </div>
  );
}

function MissionHeader() {
  const { data: aois } = useAOIs();
  const { data: settings } = useSettings();
  const { data: exps } = useExperiments();
  const { data: jobs } = useJobs();
  const { aoiId, setAoiId } = useApp();

  useEffect(() => {
    if (!aois?.length) return;
    if (!aoiId || !aois.some((a) => a.id === aoiId)) setAoiId(settings?.active_aoi_id ?? aois[0].id);
  }, [aois, aoiId, settings, setAoiId]);

  const model = exps?.find((e) => e.id === settings?.active_experiment_id);
  const running = jobs?.filter((j) => j.status === "running" || j.status === "queued") ?? [];
  const aoi = aois?.find((a) => a.id === aoiId);

  return (
    <div className="flex h-12 items-center gap-2 border-b border-line bg-canvas/95 px-4 backdrop-blur">
      <div className="flex min-w-0 items-center gap-2 rounded-lg border border-line bg-surface pl-2.5 pr-1">
        <span className="text-[11px] text-muted">AOI</span>
        <select
          aria-label="Monitoring area"
          className="h-8 min-w-0 max-w-[18rem] truncate bg-transparent text-[13px] text-ink outline-none"
          value={aoiId ?? ""}
          onChange={(e) => setAoiId(e.target.value)}
        >
          {aois?.map((a) => (
            <option key={a.id} value={a.id} className="bg-surface">
              {a.name}
            </option>
          ))}
        </select>
      </div>
      {aoi && <span className="num hidden text-[11px] text-muted md:inline">{fmtNum(aoi.area_km2, 0)} km² · {aoi.grid.crs}</span>}
      <div className="ml-auto flex shrink-0 items-center gap-2">
        {running.length > 0 && (
          <NavLink to="/history" className="flex items-center gap-1.5 rounded-lg border border-gain/40 px-2.5 py-1 text-[11px] text-gain">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-gain" />
            {running.length} job{running.length > 1 ? "s" : ""} · {running[0].type} {Math.round(running[0].progress * 100)}%
          </NavLink>
        )}
        <NavLink
          to="/lab"
          title={model ? `${model.name} · mIoU(val) ${model.best_val_miou?.toFixed(3) ?? "—"}` : undefined}
          className={clsx(
            "flex items-center gap-1.5 whitespace-nowrap rounded-lg border px-2.5 py-1 text-[11px]",
            model ? "border-line text-ink-2" : "border-uncertain/40 text-uncertain",
          )}
        >
          <Boxes className="h-3.5 w-3.5 shrink-0" strokeWidth={1.5} />
          {model ? (
            <>
              <span className="hidden sm:inline">{model.name}</span>
              <span className="num text-muted">
                mIoU<span className="hidden sm:inline">(val)</span>{" "}
                {model.best_val_miou?.toFixed(3) ?? "—"}
              </span>
            </>
          ) : (
            "No model active"
          )}
        </NavLink>
      </div>
    </div>
  );
}

export function Shell({ children }: { children: ReactNode }) {
  const loc = useLocation();
  const fullBleed = loc.pathname === "/map";
  return (
    <div className="flex h-full">
      <nav className="flex w-[64px] shrink-0 flex-col border-r border-line bg-sunken xl:w-[240px]" aria-label="Main">
        <Logo />
        <ul className="flex-1 space-y-0.5 px-2">
          {NAV.map(({ to, label, icon: Icon }) => (
            <li key={to}>
              <NavLink
                to={to}
                end={to === "/"}
                title={label}
                className={({ isActive }) =>
                  clsx(
                    "group flex h-9 items-center gap-3 rounded-lg border px-2.5 text-[13px] transition-colors duration-150",
                    isActive
                      ? "border-line bg-raised text-ink shadow-[inset_0_1px_0_rgba(255,255,255,0.06)]"
                      : "border-transparent text-muted hover:bg-raised/60 hover:text-ink",
                  )
                }
              >
                {({ isActive }) => (
                  <>
                    <Icon className={clsx("h-[18px] w-[18px] shrink-0", isActive ? "text-accent-strong" : "")} strokeWidth={1.5} />
                    <span className="hidden xl:inline">{label}</span>
                  </>
                )}
              </NavLink>
            </li>
          ))}
        </ul>
        <div className="hidden px-4 pb-4 text-[11px] leading-relaxed text-faint xl:block">
          Independent research tool. Detected changes are potential, not verified deforestation.
        </div>
      </nav>
      <div className="flex min-w-0 flex-1 flex-col">
        <MissionHeader />
        <main className={clsx("min-h-0 flex-1", fullBleed ? "overflow-hidden" : "overflow-y-auto")}>
          {fullBleed ? children : <div className="mx-auto max-w-[1440px] px-6 py-7">{children}</div>}
        </main>
      </div>
    </div>
  );
}
