import { useState } from "react";
import { AvatarSettings } from "./components/AvatarSettings";
import { Chat } from "./components/Chat";
import { ConversationList } from "./components/ConversationList";
import { DocumentsPanel } from "./components/DocumentsPanel";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { FloatingAvatar } from "./components/FloatingAvatar";
import { GoogleConnect } from "./components/GoogleConnect";
import { MemoryViewer } from "./components/MemoryViewer";
import { PhoneConnect } from "./components/PhoneConnect";
import { ScheduledTasksPanel } from "./components/ScheduledTasksPanel";
import { SettingsPage } from "./components/SettingsPage";
import { StatusBar } from "./components/StatusBar";
import { SystemStatus } from "./components/SystemStatus";
import { TodayDashboard } from "./components/TodayDashboard";
import { ToastHost, toast } from "./components/Toast";
import { ToolsPanel } from "./components/ToolsPanel";
import { useAppStore } from "./stores/appStore";
import { useShortcuts } from "./hooks/useShortcuts";

type View = "chat" | "today" | "scheduler" | "settings";

export default function App() {
  const [showMemory, setShowMemory] = useState(true);
  const [view, setView] = useState<View>("chat");
  const [showAvatarSettings, setShowAvatarSettings] = useState(false);
  const { clear } = useAppStore();

  useShortcuts({
    "mod+k": () => {
      const el = document.querySelector<HTMLTextAreaElement>(
        "textarea[placeholder]"
      );
      el?.focus();
    },
    "mod+n": () => {
      clear();
      setView("chat");
      toast.info("New conversation");
    },
    "mod+/": () => {
      // Trigger the mic button click programmatically.
      const btn = document.querySelector<HTMLButtonElement>('button[title*="voice" i]');
      btn?.click();
    },
    "mod+shift+,": () => setView("settings"),
  });

  return (
    <div className="h-full flex flex-col bg-kira-bg text-kira-text">
      <div className="flex-1 grid grid-cols-1 md:grid-cols-[220px_1fr] xl:grid-cols-[220px_1fr_360px] min-h-0">
        <aside className="border-r border-kira-border bg-kira-panel flex flex-col">
          <div className="p-4 border-b border-kira-border">
            <div className="text-lg font-medium text-kira-accent">KIRA</div>
            <div className="text-[11px] text-kira-muted">v0.1.0 · Phase 11</div>
          </div>
          <nav className="p-2 border-b border-kira-border">
            <ViewButton current={view} value="chat" onClick={() => setView("chat")}>
              Chat
            </ViewButton>
            <ViewButton current={view} value="today" onClick={() => setView("today")}>
              Today
            </ViewButton>
            <ViewButton
              current={view}
              value="scheduler"
              onClick={() => setView("scheduler")}
            >
              Scheduler
            </ViewButton>
            <ViewButton
              current={view}
              value="settings"
              onClick={() => setView("settings")}
            >
              Settings
            </ViewButton>
          </nav>
          <nav className="flex-1 p-2 overflow-y-auto kira-scroll">
            <ConversationList />
            <button
              onClick={() => setShowMemory(!showMemory)}
              className="w-full text-left px-3 py-2 text-sm rounded hover:bg-kira-bg text-kira-text mt-2"
            >
              {showMemory ? "Hide" : "Show"} memory panel
            </button>
            <button
              onClick={() => setShowAvatarSettings(true)}
              className="w-full text-left px-3 py-2 text-sm rounded hover:bg-kira-bg text-kira-text"
            >
              Avatar settings…
            </button>
            <div className="mt-3 px-2">
              <GoogleConnect />
            </div>
            <SystemStatus />
            <DocumentsPanel />
            <ToolsPanel />
          </nav>
          <PhoneConnect />
        </aside>

        <main className="min-w-0 overflow-y-auto kira-scroll">
          <ErrorBoundary>
            {view === "chat" && <Chat />}
            {view === "today" && <TodayDashboard />}
            {view === "scheduler" && (
              <div className="p-4">
                <ScheduledTasksPanel />
              </div>
            )}
            {view === "settings" && <SettingsPage />}
          </ErrorBoundary>
        </main>

        <div className="hidden xl:block">
          {showMemory ? (
            <ErrorBoundary>
              <MemoryViewer />
            </ErrorBoundary>
          ) : (
            <div className="border-l border-kira-border bg-kira-panel h-full" />
          )}
        </div>
      </div>
      <StatusBar />
      <FloatingAvatar />
      <ToastHost />
      {showAvatarSettings && (
        <AvatarSettings onClose={() => setShowAvatarSettings(false)} />
      )}
    </div>
  );
}

function ViewButton({
  current,
  value,
  onClick,
  children,
}: {
  current: string;
  value: string;
  onClick: () => void;
  children: React.ReactNode;
}) {
  const active = current === value;
  return (
    <button
      onClick={onClick}
      className={`w-full text-left px-3 py-2 text-sm rounded ${
        active ? "bg-kira-bg text-kira-accent" : "text-kira-text hover:bg-kira-bg"
      }`}
    >
      {children}
    </button>
  );
}
