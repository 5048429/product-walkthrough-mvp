import type { ReactNode } from "react";

interface AppShellProps {
  topBar: ReactNode;
  left: ReactNode;
  main: ReactNode;
  right: ReactNode;
  bottom: ReactNode;
}

export function AppShell({ topBar, left, main, right, bottom }: AppShellProps) {
  return (
    <div className="app-shell">
      <header className="top-region">{topBar}</header>
      <aside className="left-region">{left}</aside>
      <main className="main-region">{main}</main>
      <aside className="right-region">{right}</aside>
      <section className="bottom-region">{bottom}</section>
    </div>
  );
}
