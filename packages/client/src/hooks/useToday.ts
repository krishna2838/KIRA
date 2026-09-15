import { useEffect, useState } from "react";
import { apiFetch } from "../lib/api";

interface CalendarEvent {
  id?: string;
  title: string;
  start?: string;
  end?: string;
  location?: string;
  hangout_link?: string;
}

interface Task {
  id: string;
  title: string;
  due?: string;
  status?: string;
}

interface Notification {
  id: string;
  app_name: string;
  title: string;
  body: string;
  sender?: string;
  timestamp: string;
  read: boolean;
}

interface Deadline {
  id: string;
  name: string;
  due: string;
  notes?: string;
  completed?: boolean;
}

export interface TodayBrief {
  generated_at: string;
  google:
    | {
        connected: true;
        today_events: CalendarEvent[];
        open_tasks: Task[];
        unread_email: number | null;
      }
    | { connected: false; hint: string };
  notifications: { recent: Notification[]; unread: number };
  deadlines: Deadline[];
}

export function useToday() {
  const [data, setData] = useState<TodayBrief | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = async () => {
    try {
      const r = await apiFetch<TodayBrief>("/api/today");
      setData(r);
      setErr(null);
    } catch (e) {
      setErr((e as Error).message);
    }
  };

  useEffect(() => {
    load();
    const id = setInterval(load, 5 * 60 * 1000);
    return () => clearInterval(id);
  }, []);

  return { data, err, reload: load };
}
