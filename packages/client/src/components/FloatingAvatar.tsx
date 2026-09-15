import { useAppStore } from "../stores/appStore";
import { Avatar } from "./Avatar";

/**
 * Mini corner avatar (100x100). Click to hide. `expandOnClick` (from Chat)
 * would ordinarily switch back to the full view — since the full chat is
 * already visible, we just toggle it off here for now.
 */
export function FloatingAvatar() {
  const { floatingAvatar, kiraState, avatarMode, setFloatingAvatar } =
    useAppStore();
  if (!floatingAvatar || avatarMode === "hidden") return null;

  return (
    <button
      onClick={() => setFloatingAvatar(false)}
      className="fixed bottom-24 right-6 z-40 rounded-full overflow-hidden border border-kira-border bg-kira-panel shadow-xl hover:border-kira-accent transition"
      style={{ width: 100, height: 100 }}
      title={`KIRA state: ${kiraState} — click to hide`}
    >
      <Avatar state={kiraState} size={100} />
    </button>
  );
}
