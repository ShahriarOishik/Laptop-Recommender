import { useState } from "react";
import { Outlet } from "react-router-dom";
import { Navbar } from "./Navbar";
import { Sidebar } from "./Sidebar";

export function AppLayout() {
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      <Navbar onMenuClick={() => setMobileNavOpen(true)} />
      <div className="flex min-h-0 flex-1 overflow-hidden">
        <aside className="hidden w-64 flex-shrink-0 overflow-y-auto border-r border-[var(--color-border)] bg-[var(--color-surface)] lg:block">
          <Sidebar />
        </aside>

        {mobileNavOpen && (
          <div className="fixed inset-0 z-40 lg:hidden">
            <div
              className="absolute inset-0 bg-black/40"
              onClick={() => setMobileNavOpen(false)}
              aria-hidden="true"
            />
            <div className="absolute left-0 top-0 h-full w-72 bg-[var(--color-surface)] shadow-2xl">
              <Sidebar onNavigate={() => setMobileNavOpen(false)} />
            </div>
          </div>
        )}

        <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
          <main className="min-h-0 flex-1 overflow-y-auto scrollbar-thin">
            <Outlet />
          </main>
        </div>
      </div>
    </div>
  );
}
