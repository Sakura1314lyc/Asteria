import {
  Activity,
  BookOpenText,
  FolderKanban,
  Menu,
  Plus,
  Settings,
  X
} from "lucide-react";
import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router";
import { PUBLIC_DEMO } from "../deployment";
import { Logo } from "./Logo";

const nav = [
  { to: "/", label: "今日工作", icon: Activity },
  { to: "/projects", label: "研究项目", icon: FolderKanban },
  { to: "/library", label: "文献入口", icon: BookOpenText },
  { to: "/settings", label: "运行环境", icon: Settings }
];

export function AppShell() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const navigate = useNavigate();
  return (
    <div className="app-frame">
      <button
        type="button"
        className="mobile-menu"
        onClick={() => setMobileOpen((value) => !value)}
        aria-label="打开导航"
      >
        {mobileOpen ? <X size={20} /> : <Menu size={20} />}
      </button>
      <aside
        className={`sidebar ${mobileOpen ? "is-open" : ""}`}
        data-color-mode="dark"
        data-dark-theme="dark_dimmed"
      >
        <div className="sidebar__top">
          <Logo />
          <button
            type="button"
            className="new-project"
            disabled={PUBLIC_DEMO}
            title={PUBLIC_DEMO ? "公开观测站为只读样例" : undefined}
            onClick={() => {
              navigate("/projects?new=1", { viewTransition: true });
              setMobileOpen(false);
            }}
          >
            <Plus size={16} />
            新建研究
          </button>
        </div>
        <nav className="sidebar__nav" aria-label="主导航">
          <span className="sidebar__label">研究空间</span>
          {nav.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              viewTransition
              onClick={() => setMobileOpen(false)}
              className={({ isActive }) => (isActive ? "is-active" : "")}
            >
              <Icon size={17} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <footer className="sidebar__footer">
          <span className="local-dot" aria-hidden="true" />
          <span>
            <strong>{PUBLIC_DEMO ? "公开观测站" : "本地工作区"}</strong>
            <small>
            {PUBLIC_DEMO ? "只读研究样例" : "数据留在此设备"} · v0.14.1
            </small>
          </span>
        </footer>
      </aside>
      <main className="main-surface">
        {PUBLIC_DEMO && (
          <div className="public-demo-notice" role="status">
            <span>Public observatory</span>
            <strong>只读研究样例</strong>
            <a
              href="https://github.com/Sakura1314lyc/Asteria"
              target="_blank"
              rel="noreferrer"
            >
              在本地运行完整版本
            </a>
          </div>
        )}
        <Outlet />
      </main>
    </div>
  );
}
