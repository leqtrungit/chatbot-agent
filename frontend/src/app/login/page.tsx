"use client";

import { useState } from "react";
import { login } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Loader2Icon } from "lucide-react";
import { EmberMark } from "@/components/ember-mark";

export default function LoginPage() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleLogin() {
    setLoading(true);
    setError(null);
    try {
      await login();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to initiate login";
      setError(message);
      setLoading(false);
    }
  }

  return (
    <div className="relative flex min-h-screen w-full items-center justify-center overflow-hidden p-4">
      <div
        className="pointer-events-none absolute inset-0 -z-10"
        style={{
          background:
            "radial-gradient(560px circle at 50% 18%, color-mix(in oklch, var(--primary) 14%, transparent), transparent 70%)",
        }}
        aria-hidden="true"
      />
      <div className="flex w-full max-w-sm flex-col items-center gap-6">
        <div className="flex animate-fade-up items-center gap-2.5 [animation-delay:0ms]">
          <EmberMark className="size-6" />
          <span className="font-heading text-2xl tracking-tight">Chatbot Agent</span>
        </div>
        <Card className="w-full animate-fade-up border-border/80 shadow-[0_1px_2px_color-mix(in_oklch,var(--foreground)_4%,transparent),0_16px_40px_-12px_color-mix(in_oklch,var(--foreground)_18%,transparent)] [animation-delay:80ms]">
          <CardHeader>
            <CardTitle className="font-heading text-2xl font-normal">
              Welcome back
            </CardTitle>
            <CardDescription>Sign in with Keycloak to continue.</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            {error ? (
              <p className="text-sm text-destructive" role="alert">
                {error}
              </p>
            ) : null}
            <Button onClick={handleLogin} disabled={loading} size="lg" className="w-full">
              {loading ? (
                <>
                  <Loader2Icon className="animate-spin" />
                  Signing in...
                </>
              ) : (
                "Sign in with Keycloak"
              )}
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
