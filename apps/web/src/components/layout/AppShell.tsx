import type { ReactNode } from "react";

interface AppShellProps {
  topBar: ReactNode;
  navigation: ReactNode;
  children: ReactNode;
}

export function AppShell({ topBar, navigation, children }: AppShellProps) {
  return (
    <div className="app-shell app-shell-workbench">
      <header className="top-region">{topBar}</header>
      <nav className="nav-region" aria-label="Console views">
        {navigation}
      </nav>
      <main className="workspace-region">{children}</main>
    </div>
  );
}
