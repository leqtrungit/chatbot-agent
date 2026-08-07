"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState, useSyncExternalStore } from "react";
import { useTheme } from "next-themes";
import {
  BotIcon,
  FolderKanban,
  KeyRound,
  LogOut,
  MessageSquare,
  MoonIcon,
  PlugZap,
  SunIcon,
  User,
} from "lucide-react";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { clearAuthToken } from "@/lib/auth";
import { cn } from "@/lib/utils";
import { EmberMark } from "@/components/ember-mark";
import { PlaygroundDrawer } from "@/components/playground-drawer";

const NAV_ITEMS = [
  { href: "/domains", label: "Domains", icon: FolderKanban },
  { href: "/agents", label: "Agents", icon: BotIcon },
  { href: "/mcp-servers", label: "MCP Servers", icon: PlugZap },
  { href: "/api-keys", label: "API Keys", icon: KeyRound },
];

const navItemClass = (active: boolean) =>
  cn(
    "flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
    active
      ? "bg-primary/12 text-primary"
      : "text-muted-foreground hover:bg-muted hover:text-foreground"
  );

const subscribeNoop = () => () => {};

function useMounted() {
  return useSyncExternalStore(
    subscribeNoop,
    () => true,
    () => false
  );
}

function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  const mounted = useMounted();

  const isDark = mounted && resolvedTheme === "dark";

  return (
    <Button
      variant="ghost"
      size="icon"
      aria-label={isDark ? "Switch to light theme" : "Switch to dark theme"}
      onClick={() => setTheme(isDark ? "light" : "dark")}
    >
      {mounted ? (
        isDark ? (
          <SunIcon className="size-4" />
        ) : (
          <MoonIcon className="size-4" />
        )
      ) : (
        <span className="size-4" />
      )}
    </Button>
  );
}

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const [playgroundOpen, setPlaygroundOpen] = useState(false);

  function handleLogout() {
    clearAuthToken();
    router.push("/login");
    router.refresh();
  }

  return (
    <TooltipProvider>
      <div className="flex min-h-screen">
        <aside className="flex w-56 shrink-0 flex-col border-r border-border/70 bg-background/60">
          <Link
            href="/domains"
            className="flex items-center gap-2.5 px-5 py-5 font-heading text-lg tracking-tight"
          >
            <EmberMark />
            Chatbot Agent
          </Link>

          <nav className="flex flex-1 flex-col gap-1 px-3">
            {NAV_ITEMS.map((item) => {
              const active =
                pathname === item.href || pathname.startsWith(`${item.href}/`);
              return (
                <Link key={item.href} href={item.href} className={navItemClass(active)}>
                  <item.icon className="size-4" />
                  {item.label}
                </Link>
              );
            })}
            <button
              type="button"
              onClick={() => setPlaygroundOpen(true)}
              className={navItemClass(playgroundOpen)}
            >
              <MessageSquare className="size-4" />
              Playground
            </button>
          </nav>

          <div className="flex items-center justify-between gap-1 border-t border-border/70 px-3 py-3">
            <ThemeToggle />
            <DropdownMenu>
              <DropdownMenuTrigger
                render={
                  <Button variant="ghost" size="icon" aria-label="Account menu">
                    <User className="size-4" />
                  </Button>
                }
              />
              <DropdownMenuContent align="end">
                <DropdownMenuItem disabled>admin</DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem variant="destructive" onClick={handleLogout}>
                  <LogOut className="size-4" />
                  Log out
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </aside>

        <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col px-6 py-8">
          {children}
        </main>

        <PlaygroundDrawer open={playgroundOpen} onOpenChange={setPlaygroundOpen} />
        <Toaster />
      </div>
    </TooltipProvider>
  );
}
