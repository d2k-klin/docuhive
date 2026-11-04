import {
  FileText,
  House,
  Search,
  Upload,
  Camera,
  Settings,
  ShieldAlert,
  Tags,
  BookOpen,
  KeyRound,
  Bookmark,
  Copy,
  HardDrive,
  ListPlus,
} from "lucide-react";
import {
  BarChart3,
  Bell,
  CalendarClock,
  Inbox,
  Mail,
  MessageSquare,
  Sparkles,
} from "lucide-react"; // CL
import type { LucideIcon } from "lucide-react";

export type NavItem = {
  href: string;
  label: string;
  icon: LucideIcon;
  section: "core" | "intel";
  adminOnly?: boolean;
};
export const nav: NavItem[] = [
  { href: "/", label: "Dashboard", icon: House, section: "core" },
  { href: "/documents", label: "Documents", icon: FileText, section: "core" },
  { href: "/search", label: "Search", icon: Search, section: "core" },
  { href: "/upload", label: "Upload", icon: Upload, section: "core" },
  { href: "/capture", label: "Capture", icon: Camera, section: "core" },
  {
    href: "/knowledge",
    label: "Knowledge bases",
    icon: BookOpen,
    section: "core",
  },
  { href: "/views", label: "Saved views", icon: Bookmark, section: "core" },
  {
    href: "/duplicates",
    label: "Duplicates",
    icon: Copy,
    section: "core",
  },
  {
    href: "/settings/fields",
    label: "Custom fields",
    icon: ListPlus,
    section: "core",
  },
  {
    href: "/settings/storage",
    label: "Storage health",
    icon: HardDrive,
    section: "core",
    adminOnly: true,
  },
  {
    href: "/settings/tokens",
    label: "API tokens",
    icon: KeyRound,
    section: "core",
  },
  {
    href: "/quarantine",
    label: "Quarantine",
    icon: ShieldAlert,
    section: "core",
    adminOnly: true,
  },
  { href: "/vocabulary", label: "Vocabulary", icon: Tags, section: "core" },
  {
    href: "/settings/account",
    label: "Settings",
    icon: Settings,
    section: "core",
  },
  // CL appends Review, Ask, Analyses, Sources, Reminders, AI and Notifications as pages ship.
  { href: "/review", label: "Review", icon: Inbox, section: "intel" },
  { href: "/ask", label: "Ask", icon: MessageSquare, section: "intel" },
  { href: "/analyses", label: "Analyses", icon: BarChart3, section: "intel" },
  {
    href: "/reminders",
    label: "Reminders",
    icon: CalendarClock,
    section: "intel",
  },
  { href: "/sources", label: "Sources", icon: Mail, section: "intel" },
  { href: "/settings/ai", label: "AI", icon: Sparkles, section: "intel" },
  {
    href: "/settings/notifications",
    label: "Notifications",
    icon: Bell,
    section: "intel",
  },
];

export function visibleNav(role: "admin" | "member"): NavItem[] {
  return nav.filter((item) => !item.adminOnly || role === "admin");
}
