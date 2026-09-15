import { create } from "zustand";
import type { KiraState, Message } from "../types";

export type AvatarMode = "auto" | "3d" | "simple" | "hidden";
export type ParticleDensity = "low" | "medium" | "high";

interface AppState {
  messages: Message[];
  conversationId: string | null;
  kiraState: KiraState;
  lastModel: string;
  lastLatencyMs: number;
  serverConnected: boolean;
  researchMode: "off" | "quick" | "deep";
  activeResearchId: string | null;
  avatarMode: AvatarMode;
  particleDensity: ParticleDensity;
  floatingAvatar: boolean;
  addMessage: (m: Message) => void;
  setConversationId: (id: string) => void;
  setKiraState: (s: KiraState) => void;
  setLastModel: (m: string) => void;
  setLastLatencyMs: (n: number) => void;
  setServerConnected: (v: boolean) => void;
  setResearchMode: (m: "off" | "quick" | "deep") => void;
  setActiveResearchId: (id: string | null) => void;
  setAvatarMode: (m: AvatarMode) => void;
  setParticleDensity: (d: ParticleDensity) => void;
  setFloatingAvatar: (v: boolean) => void;
  clear: () => void;
}

export const useAppStore = create<AppState>((set) => ({
  messages: [],
  conversationId: null,
  kiraState: "idle",
  lastModel: "",
  lastLatencyMs: 0,
  serverConnected: false,
  researchMode: "off",
  activeResearchId: null,
  avatarMode: (typeof localStorage !== "undefined" &&
    (localStorage.getItem("kira.avatar_mode") as AvatarMode | null)) || "auto",
  particleDensity: (typeof localStorage !== "undefined" &&
    (localStorage.getItem("kira.particle_density") as ParticleDensity | null)) || "medium",
  floatingAvatar: (typeof localStorage !== "undefined" &&
    localStorage.getItem("kira.floating_avatar") === "1") || false,
  addMessage: (m) => set((s) => ({ messages: [...s.messages, m] })),
  setConversationId: (id) => set({ conversationId: id }),
  setKiraState: (s) => set({ kiraState: s }),
  setLastModel: (m) => set({ lastModel: m }),
  setLastLatencyMs: (n) => set({ lastLatencyMs: n }),
  setServerConnected: (v) => set({ serverConnected: v }),
  setResearchMode: (m) => set({ researchMode: m }),
  setActiveResearchId: (id) => set({ activeResearchId: id }),
  setAvatarMode: (m) => {
    try { localStorage.setItem("kira.avatar_mode", m); } catch { /* ignore */ }
    set({ avatarMode: m });
  },
  setParticleDensity: (d) => {
    try { localStorage.setItem("kira.particle_density", d); } catch { /* ignore */ }
    set({ particleDensity: d });
  },
  setFloatingAvatar: (v) => {
    try { localStorage.setItem("kira.floating_avatar", v ? "1" : "0"); } catch { /* ignore */ }
    set({ floatingAvatar: v });
  },
  clear: () => set({ messages: [], conversationId: null }),
}));
