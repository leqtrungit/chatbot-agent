"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useSyncExternalStore } from "react";
import { useTheme } from "next-themes";
import {
  BotIcon,
  FolderKanban,
  KeyRound,
  LogOut,
  MoonIcon,
  SunIcon,
  User,
  AlertCircleIcon,
  X,
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
import { logout, isLoggedIn } from "@/lib/auth";
import { cn } from "@/lib/utils";
import { EmberMark } from "@/components/ember-mark";
import { parseToken } from "@/lib/auth";
import { isOperator, getOperatorMessage } from "@/lib/org";

const NAV_ITEMS = [
  { href: "/domains", label: "Knowledge Bases", icon: FolderKanban },
  { href: "/agents", label: "Agents", icon: BotIcon },
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
  const mounted = useMounted();
  const [showOperatorBanner, setShowOperatorBanner] = useState(false);

  useEffect(() => {
    if (!mounted) return;

    // Check if logged in, redirect to login if not
    if (!isLoggedIn()) {
      router.replace("/login");
    }
  }, [mounted, router]);

  useEffect(() => {
    if (!mounted || !isLoggedIn()) return;

    // Check if user is operator
    (async () => {
      const isOperatorUser = await isOperator();
      setShowOperatorBanner(isOperatorUser);
    })();
  }, [mounted]);

  if (!mounted || !isLoggedIn()) {
    return null; // Prevent hydration mismatch and protect route
  }

  // Get username from token
  const payload = parseToken();
  const username = payload?.preferred_username || "User";

  function handleLogout() {
    logout();
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
                <DropdownMenuItem disabled>{username || "User"}</DropdownMenuItem>
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
          {showOperatorBanner && (
            <div className="mb-6 flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 p-4 text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-50">
              <AlertCircleIcon className="mt-0.5 size-5 shrink-0" />
              <div className="flex-1">
                <p className="font-medium">Operator Access</p>
                <p className="mt-1 text-sm">{getOperatorMessage()}</p>
              </div>
              <button
                onClick={() => setShowOperatorBanner(false)}
                className="shrink-0 text-amber-900 hover:text-amber-700 dark:text-amber-50 dark:hover:text-amber-200"
                aria-label="Dismiss message"
              >
                <X className="size-4" />
              </button>
            </div>
          )}
          {children}
        </main>

        <Toaster />
      </div>
    </TooltipProvider>
  );
}
