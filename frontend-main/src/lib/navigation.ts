import {
  BookOpen,
  Bot,
  CalendarDays,
  CheckSquare,
  Gift,
  Home,
  Network,
  NotebookPen,
  Search,
  Settings,
  ShoppingBasket,
  Sparkles,
  Tags,
  Toolbox,
  Vault,
  Waypoints,
} from "lucide-react";

export const navigation = [
  { label: "Home", href: "/", icon: Home },
  { label: "Notes", href: "/notes", icon: NotebookPen },
  { label: "Search", href: "/search", icon: Search },
  { label: "Calendar", href: "/calendar", icon: CalendarDays },
  { label: "Tasks", href: "/tasks", icon: CheckSquare },
  { label: "Chores", href: "/chores", icon: CheckSquare },
  { label: "Meals", href: "/meals", icon: ShoppingBasket },
  { label: "Learning", href: "/learning", icon: BookOpen },
  { label: "Rewards", href: "/rewards", icon: Gift },
  { label: "Vault", href: "/vault", icon: Vault },
  { label: "KB Viewer", href: "/graph", icon: Network },
  { label: "Archify", href: "/archify", icon: Waypoints },
  { label: "Utilities", href: "/utilities", icon: Toolbox },
  { label: "Agents", href: "/agents", icon: Bot },
  { label: "Tag review", href: "/tags/review", icon: Tags },
  { label: "Settings", href: "/settings", icon: Settings },
];

export const panelActions = [
  { label: "Capture", shortcut: "C", key: "capture" },
  { label: "Whiteboard", shortcut: "W", key: "whiteboard" },
  { label: "Hermes", shortcut: "H", key: "hermes" },
] as const;

export type PanelKind = (typeof panelActions)[number]["key"];