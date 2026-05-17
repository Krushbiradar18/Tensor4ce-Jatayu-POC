import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchLogs, fetchLogStats, LogEntry } from "@/lib/api";
import { 
  AlertCircle, CheckCircle2, Clock, Filter, Search, ChevronDown, ChevronUp, 
  Activity, X, Server, BrainCircuit, Cpu, ArrowRight, ShieldAlert, FileText, Database
} from "lucide-react";
import { Input } from "@/components/ui/input";
import { useToast } from "@/hooks/use-toast";

const LOG_LEVEL_COLORS: Record<string, string> = {
  ERROR: "bg-red-500/10 text-red-500 border-red-500/20",
  WARN: "bg-orange-500/10 text-orange-500 border-orange-500/20",
  INFO: "bg-blue-500/10 text-blue-500 border-blue-500/20",
  DEBUG: "bg-slate-500/10 text-slate-500 border-slate-500/20"
};

const CATEGORY_ICONS: Record<string, React.ReactNode> = {
  agent: <BrainCircuit className="w-3 h-3" />,
  llm: <Cpu className="w-3 h-3" />,
  system: <Server className="w-3 h-3" />,
  tool: <Activity className="w-3 h-3" />,
  integration: <Database className="w-3 h-3" />
};

export default function AdminLoggingPage() {
  const { toast } = useToast();
  const [filters, setFilters] = useState({
    search: "",
    log_level: "",
    log_category: "",
    agent_name: "",
    application_id: "",
    page: 1,
    limit: 30
  });
  
  const [selectedLog, setSelectedLog] = useState<LogEntry | null>(null);

  const { data: logsData, isLoading, refetch } = useQuery({
    queryKey: ["logs", filters],
    queryFn: () => fetchLogs(filters),
    refetchInterval: 5000, // 5s polling
  });

  const { data: statsData } = useQuery({
    queryKey: ["logStats", filters.agent_name, filters.application_id],
    queryFn: () => fetchLogStats({
      agent_name: filters.agent_name,
      application_id: filters.application_id
    }),
    refetchInterval: 10000,
  });

  // Separate unfiltered query — used only to populate the Agent Name dropdown
  // so it always lists ALL agents regardless of active filters
  const { data: allAgentsStats } = useQuery({
    queryKey: ["logStatsAllAgents"],
    queryFn: () => fetchLogStats({}),
    refetchInterval: 30000,
    staleTime: 15000,
  });

  const handleFilterChange = (key: string, value: string | number) => {
    setFilters(prev => ({
      ...prev,
      [key]: value,
      // Only reset to page 1 when a real filter changes, not when paginating
      ...(key !== "page" ? { page: 1 } : {}),
    }));
  };

  const resetFilters = () => {
    setFilters({
      search: "",
      log_level: "",
      log_category: "",
      agent_name: "",
      application_id: "",
      page: 1,
      limit: 50
    });
  };

  const logs = logsData?.items || [];
  const totalLogs = logsData?.total || 0;
  const totalPages = Math.ceil(totalLogs / filters.limit) || 1;

  const formatDate = (dateString: string) => {
    const d = new Date(dateString);
    return new Intl.DateTimeFormat("en-US", {
      month: "short", day: "2-digit",
      hour: "2-digit", minute: "2-digit", second: "2-digit",
      fractionalSecondDigits: 3, hour12: false
    }).format(d);
  };

  return (
    <div className="space-y-6 max-w-[1600px] mx-auto pb-10">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-display font-bold tracking-tight text-foreground flex items-center gap-2">
            <FileText className="w-8 h-8 text-primary" />
            System Logs
          </h1>
          <p className="text-muted-foreground mt-1 text-sm">
            Real-time observability for agents, LLMs, and system events.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {isLoading && <span className="text-sm text-muted-foreground animate-pulse">Fetching...</span>}
          <div className="bg-primary/10 text-primary border border-primary/20 px-3 py-1.5 rounded-full text-xs font-medium flex items-center gap-2">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-primary"></span>
            </span>
            Live Polling (5s)
          </div>
        </div>
      </div>

      {/* Stats Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard 
          title="Total Logs" 
          value={statsData?.total?.toLocaleString() || "0"} 
          icon={<Database className="h-5 w-5 text-blue-500" />} 
        />
        <StatCard 
          title="Error Rate" 
          value={`${statsData?.total ? ((statsData.error_count / statsData.total) * 100).toFixed(1) : 0}%`} 
          subValue={`${statsData?.error_count || 0} errors`}
          icon={<ShieldAlert className="h-5 w-5 text-red-500" />} 
          trend="down"
        />
        <StatCard 
          title="Avg LLM Latency" 
          value={`${statsData?.llm_performance?.[0]?.avg_ms ? statsData.llm_performance[0].avg_ms.toFixed(0) : 0} ms`}
          subValue={statsData?.llm_performance?.[0]?.model || "No data"}
          icon={<Cpu className="h-5 w-5 text-purple-500" />} 
        />
        <StatCard 
          title="Active Agents" 
          value={statsData?.by_agent?.length || "0"} 
          icon={<BrainCircuit className="h-5 w-5 text-emerald-500" />} 
        />
      </div>

      <div className="flex flex-col lg:flex-row gap-6">
        {/* Filters Sidebar */}
        <div className="w-full lg:w-64 flex-shrink-0 space-y-6">
          <div className="bg-card border border-border rounded-xl p-5 shadow-sm">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-semibold text-sm flex items-center gap-2">
                <Filter className="w-4 h-4" /> Filters
              </h2>
              <button onClick={resetFilters} className="text-xs text-muted-foreground hover:text-primary transition-colors">
                Reset
              </button>
            </div>
            
            <div className="space-y-4">
              <div>
                <label className="text-xs font-medium text-muted-foreground mb-1 block">Search Message</label>
                <div className="relative">
                  <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
                  <Input 
                    placeholder="Search logs..." 
                    className="pl-8 h-8 text-sm"
                    value={filters.search}
                    onChange={(e) => handleFilterChange("search", e.target.value)}
                  />
                </div>
              </div>

              <div>
                <label className="text-xs font-medium text-muted-foreground mb-1 block">Application ID</label>
                <Input 
                  placeholder="APP-..." 
                  className="h-8 text-sm"
                  value={filters.application_id}
                  onChange={(e) => handleFilterChange("application_id", e.target.value)}
                />
              </div>

              <div>
                <label className="text-xs font-medium text-muted-foreground mb-2 block">Level</label>
                <div className="flex flex-wrap gap-2">
                  {["ERROR", "WARN", "INFO", "DEBUG"].map(lvl => (
                    <button
                      key={lvl}
                      onClick={() => handleFilterChange("log_level", filters.log_level === lvl ? "" : lvl)}
                      className={`text-xs px-2.5 py-1 rounded border transition-colors ${
                        filters.log_level === lvl 
                          ? LOG_LEVEL_COLORS[lvl] 
                          : "border-border text-muted-foreground hover:bg-muted"
                      }`}
                    >
                      {lvl}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="text-xs font-medium text-muted-foreground mb-2 block">Category</label>
                <select 
                  className="w-full h-8 px-3 rounded-md border border-border bg-background text-sm text-foreground focus:ring-1 focus:ring-primary focus:outline-none"
                  value={filters.log_category}
                  onChange={(e) => handleFilterChange("log_category", e.target.value)}
                >
                  <option value="">All Categories</option>
                  {["agent", "llm", "tool", "system", "integration"].map(cat => (
                    <option key={cat} value={cat}>{cat.charAt(0).toUpperCase() + cat.slice(1)}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="text-xs font-medium text-muted-foreground mb-2 block">Agent Name</label>
                <select 
                  className="w-full h-8 px-3 rounded-md border border-border bg-background text-sm text-foreground focus:ring-1 focus:ring-primary focus:outline-none"
                  value={filters.agent_name}
                  onChange={(e) => handleFilterChange("agent_name", e.target.value)}
                >
                  <option value="">All Agents</option>
                  {allAgentsStats?.by_agent?.map((a: any) => (
                    <option key={a.agent_name} value={a.agent_name}>
                      {a.agent_name} ({a.total})
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>

          {/* Quick Insights */}
          <div className="bg-card border border-border rounded-xl p-5 shadow-sm space-y-4">
            <h2 className="font-semibold text-sm">Top Errors</h2>
            {statsData?.top_errors?.length > 0 ? (
              <div className="space-y-3">
                {statsData.top_errors.map((e: any) => (
                  <div key={e.error_type} className="flex justify-between items-center text-sm">
                    <span className="text-red-500 font-mono text-xs truncate max-w-[150px]" title={e.error_type}>
                      {e.error_type}
                    </span>
                    <span className="text-muted-foreground bg-muted px-2 py-0.5 rounded text-xs">{e.count}</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-muted-foreground italic">No errors in current view.</p>
            )}
          </div>
        </div>

        {/* Main Table */}
        <div className="flex-1 bg-card border border-border rounded-xl shadow-sm overflow-hidden flex flex-col min-h-[600px]">
          <div className="overflow-x-auto flex-1">
            <table className="w-full text-left text-sm whitespace-nowrap">
              <thead className="bg-muted/50 text-muted-foreground sticky top-0 z-10 backdrop-blur-md">
                <tr>
                  <th className="px-4 py-3 font-medium border-b border-border w-48">Timestamp</th>
                  <th className="px-4 py-3 font-medium border-b border-border w-24">Level</th>
                  <th className="px-4 py-3 font-medium border-b border-border w-32">Source</th>
                  <th className="px-4 py-3 font-medium border-b border-border max-w-[400px]">Message</th>
                  <th className="px-4 py-3 font-medium border-b border-border w-32 text-right">Duration</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {logs.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="px-4 py-12 text-center text-muted-foreground">
                      No logs found matching criteria.
                    </td>
                  </tr>
                ) : (
                  logs.map((log) => (
                    <tr 
                      key={log.id} 
                      className={`hover:bg-muted/30 cursor-pointer transition-colors ${selectedLog?.id === log.id ? "bg-primary/5" : ""}`}
                      onClick={() => setSelectedLog(log)}
                    >
                      <td className="px-4 py-3 text-muted-foreground text-xs font-mono">
                        {formatDate(log.timestamp)}
                      </td>
                      <td className="px-4 py-3">
                        <span className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold border ${LOG_LEVEL_COLORS[log.log_level]}`}>
                          {log.log_level}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-1.5 text-xs text-foreground">
                          {CATEGORY_ICONS[log.log_category] || <Activity className="w-3 h-3" />}
                          <span className="truncate max-w-[120px]">{log.agent_name}</span>
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <div className="truncate max-w-[400px] text-foreground" title={log.message}>
                          {log.message}
                          {log.application_id && (
                            <span className="ml-2 text-xs text-muted-foreground font-mono bg-muted px-1.5 py-0.5 rounded">
                              {log.application_id}
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-3 text-right text-xs text-muted-foreground">
                        {log.execution_time_ms ? `${Math.round(log.execution_time_ms)}ms` : "—"}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <div className="p-4 border-t border-border flex items-center justify-between bg-muted/20">
            <span className="text-xs text-muted-foreground">
              Showing {(filters.page - 1) * filters.limit + 1} - {Math.min(filters.page * filters.limit, totalLogs)} of {totalLogs} logs
            </span>
            <div className="flex gap-2">
              <button 
                disabled={filters.page === 1}
                onClick={() => handleFilterChange("page", filters.page - 1)}
                className="px-3 py-1.5 border border-border rounded bg-background text-xs font-medium hover:bg-muted disabled:opacity-50 transition-colors"
              >
                Previous
              </button>
              <button 
                disabled={filters.page >= totalPages}
                onClick={() => handleFilterChange("page", filters.page + 1)}
                className="px-3 py-1.5 border border-border rounded bg-background text-xs font-medium hover:bg-muted disabled:opacity-50 transition-colors"
              >
                Next
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Detail Modal Overlay */}
      {selectedLog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 bg-background/80 backdrop-blur-sm">
          <div className="bg-card w-full max-w-4xl max-h-[90vh] rounded-xl border border-border shadow-2xl flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-200">
            {/* Header */}
            <div className={`p-4 border-b flex items-center justify-between ${
              selectedLog.log_level === "ERROR" ? "bg-red-500/5 border-red-500/20" : 
              selectedLog.log_level === "WARN" ? "bg-orange-500/5 border-orange-500/20" : 
              "bg-muted/30 border-border"
            }`}>
              <div className="flex items-center gap-3">
                <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-bold border ${LOG_LEVEL_COLORS[selectedLog.log_level]}`}>
                  {selectedLog.log_level}
                </span>
                <span className="text-sm font-medium text-foreground">{selectedLog.message}</span>
              </div>
              <button onClick={() => setSelectedLog(null)} className="text-muted-foreground hover:text-foreground p-1 rounded-md hover:bg-muted/50 transition-colors">
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-auto p-0">
              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 border-b border-border">
                <DetailTile label="Timestamp" value={formatDate(selectedLog.timestamp)} />
                <DetailTile label="Agent" value={selectedLog.agent_name} />
                <DetailTile label="Category" value={selectedLog.log_category} />
                <DetailTile label="Application ID" value={selectedLog.application_id || "N/A"} className="font-mono text-xs" />
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-3 border-b border-border">
                <DetailTile label="Tool / Node" value={selectedLog.tool_name || "N/A"} />
                <DetailTile label="LLM Model" value={selectedLog.llm_model_name || "N/A"} />
                <DetailTile label="Execution Time" value={selectedLog.execution_time_ms ? `${Math.round(selectedLog.execution_time_ms)} ms` : "N/A"} />
              </div>

              <div className="p-6 space-y-6">
                {selectedLog.error_type && (
                  <div>
                    <h3 className="text-sm font-semibold text-red-500 flex items-center gap-2 mb-2">
                      <AlertCircle className="w-4 h-4" /> {selectedLog.error_type}
                    </h3>
                    {selectedLog.stack_trace && (
                      <pre className="bg-red-500/5 border border-red-500/20 rounded-lg p-4 overflow-x-auto text-xs text-red-400 font-mono whitespace-pre-wrap">
                        {selectedLog.stack_trace}
                      </pre>
                    )}
                  </div>
                )}

                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                  {selectedLog.input_data && (
                    <div>
                      <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Input / Prompt</h3>
                      <pre className="bg-muted rounded-lg p-4 overflow-x-auto text-xs text-foreground font-mono border border-border whitespace-pre-wrap max-h-[300px] overflow-y-auto">
                        {formatJson(selectedLog.input_data)}
                      </pre>
                    </div>
                  )}
                  {selectedLog.output_data && (
                    <div>
                      <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Output / Response</h3>
                      <pre className="bg-muted rounded-lg p-4 overflow-x-auto text-xs text-foreground font-mono border border-border whitespace-pre-wrap max-h-[300px] overflow-y-auto">
                        {formatJson(selectedLog.output_data)}
                      </pre>
                    </div>
                  )}
                </div>

                {selectedLog.metadata && selectedLog.metadata !== "{}" && (
                  <div>
                    <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Metadata</h3>
                    <pre className="bg-muted/50 rounded-lg p-3 overflow-x-auto text-xs text-muted-foreground font-mono border border-border">
                      {formatJson(selectedLog.metadata)}
                    </pre>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function StatCard({ title, value, icon, subValue, trend }: { title: string, value: string | number, icon: React.ReactNode, subValue?: string, trend?: 'up'|'down' }) {
  return (
    <div className="bg-card border border-border rounded-xl p-5 shadow-sm flex flex-col justify-between">
      <div className="flex justify-between items-start mb-4">
        <h3 className="text-sm font-medium text-muted-foreground">{title}</h3>
        <div className="p-2 rounded-lg bg-muted/50">{icon}</div>
      </div>
      <div>
        <div className="text-2xl font-bold text-foreground">{value}</div>
        {subValue && (
          <div className={`text-xs mt-1 font-medium ${trend === 'down' ? 'text-red-500' : trend === 'up' ? 'text-emerald-500' : 'text-muted-foreground'}`}>
            {subValue}
          </div>
        )}
      </div>
    </div>
  );
}

function DetailTile({ label, value, className = "" }: { label: string, value: React.ReactNode, className?: string }) {
  return (
    <div className="p-4 border-r border-border last:border-r-0">
      <div className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider mb-1">{label}</div>
      <div className={`text-sm text-foreground truncate ${className}`}>{value}</div>
    </div>
  );
}

function formatJson(data: string | undefined): string {
  if (!data) return "";
  try {
    const parsed = JSON.parse(data);
    return JSON.stringify(parsed, null, 2);
  } catch (e) {
    return data;
  }
}
