import { useEffect, useState } from "react";

import Drawer from "./ui/Drawer";
import Badge from "./ui/Badge";
import { SkeletonCard } from "./ui/Skeleton";
import { getSimulationById } from "../services/simulationService";

const DOMAIN_LABELS = {
  FINANCE: "Finance",
  ACADEMIC: "Study",
  HABIT: "Fitness",
  HYBRID_LIFESTYLE: "Combined",
};

const STATUS_TONE = {
  SUCCESS: "success",
  PARTIAL: "warning",
  FAILED: "danger",
};

function formatValue(value) {
  if (typeof value !== "number") return String(value);
  return Number.isInteger(value) ? value.toLocaleString() : value.toFixed(2);
}

/**
 * Detail view for one past simulation — GET /simulation/{id} had no service
 * binding or UI caller anywhere in the app until now; SimulationHistoryList
 * could only ever show the lightweight list row.
 */
function SimulationDetailDrawer({ simulationId, open, onClose }) {
  const [detail, setDetail] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [hasError, setHasError] = useState(false);

  useEffect(() => {
    if (!open || !simulationId) return;

    let cancelled = false;

    async function fetchDetail() {
      setIsLoading(true);
      setHasError(false);
      setDetail(null);
      try {
        const data = await getSimulationById(simulationId);
        if (!cancelled) setDetail(data);
      } catch {
        if (!cancelled) setHasError(true);
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }
    fetchDetail();

    return () => {
      cancelled = true;
    };
  }, [open, simulationId]);

  const title = detail ? `${DOMAIN_LABELS[detail.domain] || detail.domain} simulation` : "Simulation detail";

  return (
    <Drawer open={open} onClose={onClose} title={title}>
      {isLoading && <SkeletonCard lines={4} />}

      {!isLoading && hasError && (
        <p className="text-sm text-red-600 dark:text-red-400">Couldn't load this simulation. Please try again later.</p>
      )}

      {!isLoading && !hasError && detail && (
        <div className="flex flex-col gap-6">
          <div className="flex items-center justify-between">
            <span className="text-xs text-slate-400">
              Run {new Date(detail.created_at).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}
            </span>
            <Badge tone={STATUS_TONE[detail.status] || "neutral"}>{detail.status}</Badge>
          </div>

          {detail.input_parameters && Object.keys(detail.input_parameters).length > 0 && (
            <div>
              <h4 className="mb-2 text-sm font-semibold text-slate-700 dark:text-slate-200">Inputs</h4>
              <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
                {Object.entries(detail.input_parameters).map(([key, value]) => (
                  <div key={key} className="contents">
                    <dt className="text-slate-500 dark:text-slate-400">{key.replace(/_/g, " ")}</dt>
                    <dd className="font-mono tabular-nums text-slate-700 dark:text-slate-200">{formatValue(value)}</dd>
                  </div>
                ))}
              </dl>
            </div>
          )}

          <div>
            <h4 className="mb-3 text-sm font-semibold text-slate-700 dark:text-slate-200">Scenarios</h4>
            <div className="flex flex-col gap-4">
              {detail.scenarios.map((scenario) => (
                <div key={scenario.name} className="rounded-lg border border-slate-200 p-4 dark:border-slate-700">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-semibold text-slate-800 dark:text-slate-100">{scenario.name}</span>
                    <span className="text-xs text-slate-400">data sufficiency {Math.round(scenario.confidence_score * 100)}%</span>
                  </div>
                  <p className="mt-2 font-mono text-lg tabular-nums text-slate-800 dark:text-slate-100">
                    {formatValue(scenario.primary_metric_value)}
                    <span className="ml-1.5 text-xs font-sans font-normal text-slate-500 dark:text-slate-400">{scenario.primary_metric_label}</span>
                  </p>
                  {scenario.metrics?.length > 0 && (
                    <ul className="mt-3 flex flex-col gap-1 text-xs text-slate-500 dark:text-slate-400">
                      {scenario.metrics.map((m) => (
                        <li key={m.label} className="flex justify-between">
                          <span>{m.label}</span>
                          <span className="font-mono tabular-nums">{formatValue(m.value)}{m.unit ? ` ${m.unit}` : ""}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </Drawer>
  );
}

export default SimulationDetailDrawer;
