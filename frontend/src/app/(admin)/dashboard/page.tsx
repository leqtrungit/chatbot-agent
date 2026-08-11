"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  ActivityIcon,
  AlertOctagonIcon,
  ClockIcon,
  CoinsIcon,
  LayoutDashboard,
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  XAxis,
  YAxis,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  ChartLegend,
  ChartLegendContent,
  type ChartConfig,
} from "@/components/ui/chart";
import { ApiError, getBreakdown, getTimeseries, getUsageSummary } from "@/lib/api";
import type {
  AnalyticsRange,
  BreakdownBy,
  BreakdownRow,
  TimeseriesPoint,
  UsageSummary,
} from "@/lib/types";

const RANGE_LABELS: Record<AnalyticsRange, string> = {
  "24h": "Last 24 hours",
  "7d": "Last 7 days",
  "30d": "Last 30 days",
};

const REQUESTS_CHART_CONFIG = {
  success: { label: "Success", color: "var(--primary)" },
  error: { label: "Error", color: "var(--destructive)" },
} satisfies ChartConfig;

const TOKENS_CHART_CONFIG = {
  total_tokens: { label: "Tokens", color: "var(--primary)" },
} satisfies ChartConfig;

const BREAKDOWN_CHART_CONFIG = {
  requests: { label: "Requests", color: "var(--primary)" },
} satisfies ChartConfig;

const BREAKDOWN_TABS: { by: BreakdownBy; label: string }[] = [
  { by: "api_key", label: "By API Key" },
  { by: "agent", label: "By Agent" },
  { by: "model", label: "By Model" },
];

function formatBucket(bucket: string, range: AnalyticsRange): string {
  const date = new Date(bucket);
  if (range === "24h") {
    return date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  }
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function formatNumber(value: number): string {
  return value.toLocaleString();
}

export default function DashboardPage() {
  const [range, setRange] = useState<AnalyticsRange>("7d");
  const [loading, setLoading] = useState(true);
  const [summary, setSummary] = useState<UsageSummary | null>(null);
  const [timeseries, setTimeseries] = useState<TimeseriesPoint[]>([]);
  const [breakdowns, setBreakdowns] = useState<Record<BreakdownBy, BreakdownRow[]>>({
    api_key: [],
    agent: [],
    model: [],
    status: [],
  });

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const [summaryData, timeseriesData, apiKeyRows, agentRows, modelRows] =
          await Promise.all([
            getUsageSummary(range),
            getTimeseries(range),
            getBreakdown("api_key", range),
            getBreakdown("agent", range),
            getBreakdown("model", range),
          ]);
        if (cancelled) return;
        setSummary(summaryData);
        setTimeseries(timeseriesData);
        setBreakdowns({
          api_key: apiKeyRows,
          agent: agentRows,
          model: modelRows,
          status: [],
        });
      } catch (err) {
        if (!cancelled && err instanceof ApiError && err.status !== 401) {
          toast.error("Failed to load dashboard data", { description: err.message });
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [range]);

  const requestsData = timeseries.map((point) => ({
    bucket: formatBucket(point.bucket, range),
    success: point.requests - point.error_count,
    error: point.error_count,
  }));

  const tokensData = timeseries.map((point) => ({
    bucket: formatBucket(point.bucket, range),
    total_tokens: point.total_tokens,
  }));

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-heading text-3xl tracking-tight">Dashboard</h1>
          <p className="text-sm text-muted-foreground">
            Token usage and request insights across every API key, agent, and model.
          </p>
        </div>
        <Select value={range} onValueChange={(value) => setRange(value as AnalyticsRange)}>
          <SelectTrigger className="w-44">
            <SelectValue placeholder="Time range">
              {(value) => RANGE_LABELS[value as AnalyticsRange] ?? value}
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="24h">{RANGE_LABELS["24h"]}</SelectItem>
            <SelectItem value="7d">{RANGE_LABELS["7d"]}</SelectItem>
            <SelectItem value="30d">{RANGE_LABELS["30d"]}</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatTile
          icon={ActivityIcon}
          label="Total requests"
          value={summary ? formatNumber(summary.total_requests) : "—"}
          loading={loading}
        />
        <StatTile
          icon={CoinsIcon}
          label="Total tokens"
          value={summary ? formatNumber(summary.total_tokens) : "—"}
          loading={loading}
        />
        <StatTile
          icon={AlertOctagonIcon}
          label="Error rate"
          value={summary ? `${(summary.error_rate * 100).toFixed(1)}%` : "—"}
          loading={loading}
        />
        <StatTile
          icon={ClockIcon}
          label="Avg latency"
          value={summary ? `${Math.round(summary.avg_latency_ms)} ms` : "—"}
          loading={loading}
        />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Requests over time
            </CardTitle>
          </CardHeader>
          <CardContent>
            {!loading && requestsData.length === 0 ? (
              <EmptyChartState />
            ) : (
              <ChartContainer config={REQUESTS_CHART_CONFIG} className="h-[240px] w-full">
                <BarChart data={requestsData}>
                  <CartesianGrid vertical={false} />
                  <XAxis dataKey="bucket" tickLine={false} axisLine={false} tickMargin={8} />
                  <YAxis tickLine={false} axisLine={false} width={32} />
                  <ChartTooltip content={<ChartTooltipContent />} />
                  <ChartLegend content={<ChartLegendContent />} />
                  <Bar dataKey="success" stackId="requests" fill="var(--color-success)" />
                  <Bar
                    dataKey="error"
                    stackId="requests"
                    fill="var(--color-error)"
                    radius={[4, 4, 0, 0]}
                  />
                </BarChart>
              </ChartContainer>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Tokens over time
            </CardTitle>
          </CardHeader>
          <CardContent>
            {!loading && tokensData.length === 0 ? (
              <EmptyChartState />
            ) : (
              <ChartContainer config={TOKENS_CHART_CONFIG} className="h-[240px] w-full">
                <BarChart data={tokensData}>
                  <CartesianGrid vertical={false} />
                  <XAxis dataKey="bucket" tickLine={false} axisLine={false} tickMargin={8} />
                  <YAxis tickLine={false} axisLine={false} width={40} />
                  <ChartTooltip content={<ChartTooltipContent />} />
                  <Bar dataKey="total_tokens" fill="var(--color-total_tokens)" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ChartContainer>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {BREAKDOWN_TABS.map(({ by, label }) => (
          <BreakdownCard
            key={by}
            label={label}
            rows={breakdowns[by]}
            loading={loading}
          />
        ))}
      </div>
    </div>
  );
}

function StatTile({
  icon: Icon,
  label,
  value,
  loading,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string;
  loading: boolean;
}) {
  return (
    <Card>
      <CardContent className="flex items-center gap-3 py-2">
        <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
          <Icon className="size-4" />
        </div>
        <div className="flex flex-col">
          <span className="text-xs text-muted-foreground">{label}</span>
          <span className="text-xl font-semibold tabular-nums">
            {loading ? "…" : value}
          </span>
        </div>
      </CardContent>
    </Card>
  );
}

function BreakdownCard({
  label,
  rows,
  loading,
}: {
  label: string;
  rows: BreakdownRow[];
  loading: boolean;
}) {
  const top = [...rows].sort((a, b) => b.requests - a.requests).slice(0, 10);
  const data = top.map((row) => ({ key: row.key, requests: row.requests }));

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-medium text-muted-foreground">{label}</CardTitle>
      </CardHeader>
      <CardContent>
        {!loading && data.length === 0 ? (
          <EmptyChartState />
        ) : (
          <ChartContainer config={BREAKDOWN_CHART_CONFIG} className="h-[240px] w-full">
            <BarChart data={data} layout="vertical" margin={{ left: 8 }}>
              <CartesianGrid horizontal={false} />
              <XAxis type="number" tickLine={false} axisLine={false} />
              <YAxis
                dataKey="key"
                type="category"
                tickLine={false}
                axisLine={false}
                width={96}
                tickFormatter={(value: string) =>
                  value.length > 14 ? `${value.slice(0, 14)}…` : value
                }
              />
              <ChartTooltip content={<ChartTooltipContent />} />
              <Bar dataKey="requests" fill="var(--color-requests)" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ChartContainer>
        )}
      </CardContent>
    </Card>
  );
}

function EmptyChartState() {
  return (
    <div className="flex h-[240px] flex-col items-center justify-center gap-2 text-muted-foreground">
      <LayoutDashboard className="size-6 opacity-50" />
      <p className="text-sm">No data for this range yet.</p>
    </div>
  );
}
