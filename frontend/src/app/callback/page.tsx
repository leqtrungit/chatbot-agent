"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { handleCallback } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmberMark } from "@/components/ember-mark";
import { Loader2Icon } from "lucide-react";

function CallbackContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function processCallback() {
      try {
        const code = searchParams.get("code");
        const state = searchParams.get("state");

        if (!code || !state) {
          setError("Missing authorization code or state parameter");
          return;
        }

        await handleCallback(code, state);
        router.replace("/");
      } catch (err) {
        const message = err instanceof Error ? err.message : "Failed to authenticate";
        setError(message);
      }
    }

    processCallback();
  }, [searchParams, router]);

  if (error) {
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
              <CardTitle className="font-heading text-2xl font-normal">Sign in failed</CardTitle>
              <CardDescription>There was a problem authenticating your account.</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              <p className="text-sm text-destructive">{error}</p>
              <Button onClick={() => (window.location.href = "/login")} className="w-full">
                Try signing in again
              </Button>
            </CardContent>
          </Card>
        </div>
      </div>
    );
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
            <CardTitle className="font-heading text-2xl font-normal">Signing you in</CardTitle>
            <CardDescription>Completing authentication...</CardDescription>
          </CardHeader>
          <CardContent className="flex justify-center py-8">
            <Loader2Icon className="size-6 animate-spin text-primary" />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

export default function CallbackPage() {
  return (
    <Suspense fallback={<div className="flex min-h-screen items-center justify-center" />}>
      <CallbackContent />
    </Suspense>
  );
}
