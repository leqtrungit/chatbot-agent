"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { encodeCredentials, setAuthToken } from "@/lib/auth";
import { API_BASE_URL } from "@/lib/api";
import { Loader2Icon } from "lucide-react";
import { EmberMark } from "@/components/ember-mark";

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setLoading(true);

    const credentials = encodeCredentials(username, password);

    try {
      const response = await fetch(`${API_BASE_URL}/api/domains`, {
        headers: { Authorization: `Basic ${credentials}` },
      });

      if (response.status === 401) {
        setError("Invalid username or password.");
        return;
      }

      if (!response.ok) {
        setError(`Login failed (status ${response.status}).`);
        return;
      }

      setAuthToken(credentials);
      router.push("/domains");
      router.refresh();
    } catch {
      setError("Could not reach the server. Is the API running?");
    } finally {
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
        <div
          className="flex animate-fade-up items-center gap-2.5 [animation-delay:0ms]"
        >
          <EmberMark className="size-6" />
          <span className="font-heading text-2xl tracking-tight">
            Chatbot Agent
          </span>
        </div>
        <Card className="w-full animate-fade-up border-border/80 shadow-[0_1px_2px_color-mix(in_oklch,var(--foreground)_4%,transparent),0_16px_40px_-12px_color-mix(in_oklch,var(--foreground)_18%,transparent)] [animation-delay:80ms]">
          <CardHeader>
            <CardTitle className="font-heading text-2xl font-normal">
              Welcome back
            </CardTitle>
            <CardDescription>
              Sign in with your admin credentials to continue.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="flex flex-col gap-4">
              <div className="flex flex-col gap-2">
                <Label htmlFor="username">Username</Label>
                <Input
                  id="username"
                  name="username"
                  autoComplete="username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  required
                  autoFocus
                />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="password">Password</Label>
                <Input
                  id="password"
                  name="password"
                  type="password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
              </div>
              {error ? (
                <p className="text-sm text-destructive" role="alert">
                  {error}
                </p>
              ) : null}
              <Button type="submit" disabled={loading} className="mt-2">
                {loading ? (
                  <>
                    <Loader2Icon className="animate-spin" />
                    Signing in...
                  </>
                ) : (
                  "Sign in"
                )}
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
