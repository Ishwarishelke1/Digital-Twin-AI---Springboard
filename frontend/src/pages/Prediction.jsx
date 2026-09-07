import { useState, useEffect, lazy, Suspense } from "react";
import { toast } from "react-toastify";

import PredictionSummary from "../components/PredictionSummary";
import PredictionCards from "../components/PredictionCards";
import FutureChart from "../components/FutureChart";
import SimulationForm from "../components/SimulationForm";
import StudySimulationForm from "../components/StudySimulationForm";
import FitnessSimulationForm from "../components/FitnessSimulationForm";
import HybridSimulationForm from "../components/HybridSimulationForm";
import DomainComparison from "../components/DomainComparison";
import SimulationHistoryList from "../components/SimulationHistoryList";
import AIInsights from "../components/AIInsights";
import PredictionHistory from "../components/PredictionHistory";
import GoalTrendList from "../components/GoalTrendList";
import { SkeletonStatGrid, SkeletonChart } from "../components/ui/Skeleton";

import { getTrendSummary } from "../services/trendService";
import { getProductivityScore, getWeeklyProductivityTrend } from "../services/productivityService";
import { getConsistencyScore } from "../services/habitAnalyticsService";
import { useAuth } from "../context/useAuth";
import { formatCurrency } from "../utils/currency";

// Lazy-loaded: pulls in the Plotly cartesian bundle, which is sizeable even
// trimmed down — no reason to pay for it until the "Compare All" subtab
// (the only place it's used) is actually opened.
const ScenarioExplorer = lazy(() => import("../components/ScenarioExplorer"));

// Short "Aug 3" style label for chart x-axes, from an ISO date/period string.
function formatShortDate(value) {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

// Linear-regression projections (study/fitness "future" scores) are an unbounded
// extrapolation on the backend — a strong trend can project past 100 or below 0.
// Clamp before display so percentage labels and progress-bar widths stay sane.
function clampPct(value) {
  return Math.min(100, Math.max(0, value));
}

const TABS = [
  { id: "forecasts", label: "Forecasts" },
  { id: "what-if", label: "What-If" },
];

const WHAT_IF_SUBTABS = [
  { id: "finance", label: "Finance" },
  { id: "study", label: "Study" },
  { id: "fitness", label: "Fitness" },
  { id: "hybrid", label: "Combined" },
  { id: "compare", label: "Compare All" },
];

function Prediction() {
  const { user } = useAuth();
  const currency = user?.preferences?.currency ?? "USD";
  const [activeTab, setActiveTab]         = useState("forecasts");
  const [whatIfSubtab, setWhatIfSubtab]   = useState("finance");
  const [trend, setTrend]                 = useState(null);
  const [productivityScore, setProductivityScore] = useState(null);
  const [consistencyScore, setConsistencyScore]   = useState(null);
  const [weeklyTrend, setWeeklyTrend]      = useState([]);
  const [isLoading, setIsLoading]          = useState(true);

  useEffect(() => {
    async function fetchAll() {
      try {
        const [trendSummary, productivity, consistency, weekly] = await Promise.all([
          getTrendSummary(),
          getProductivityScore(),
          getConsistencyScore(),
          getWeeklyProductivityTrend(6),
        ]);
        setTrend(trendSummary);
        setProductivityScore(productivity);
        setConsistencyScore(consistency);
        setWeeklyTrend(weekly.trend || []);
      } catch (err) {
        console.error("Failed to fetch prediction data:", err);
        toast.error("Could not load your predictions. Please try again later.");
      } finally {
        setIsLoading(false);
      }
    }
    fetchAll();
  }, []);

  // Single real snapshot (the backend doesn't persist a history of past predictions,
  // so PredictionSummary/PredictionHistory get today's real confidence scores as one row
  // instead of the fabricated multi-row mock they used to render).
  const derivedHistory = trend
    ? [
        {
          id: 1,
          date: trend.generated_at ? new Date(trend.generated_at).toLocaleDateString() : "—",
          finance: Math.round((trend.savings?.confidence_score ?? 0) * 100),
          study: Math.round((trend.study?.productivity_confidence_score ?? 0) * 100),
          health: Math.round((trend.fitness?.confidence_score ?? 0) * 100),
          overall: Math.round((trend.overall_confidence_score ?? 0) * 100),
        },
      ]
    : [];

  // Study + Fitness are both real 0-100 scores, so they map cleanly onto PredictionCards'
  // current/future percentage format. Savings is a currency amount, not a percentage,
  // so it isn't forced into this card — it's represented in AIInsights instead.
  const predictionCards = trend
    ? [
        {
          title: "Study",
          current: Math.round(clampPct(productivityScore?.productivity_score ?? 0)),
          future: Math.round(clampPct(trend.study?.projected_productivity?.[0]?.value ?? 0)),
        },
        {
          title: "Fitness",
          current: Math.round(clampPct(consistencyScore?.consistency_score ?? 0)),
          future: Math.round(clampPct(trend.fitness?.projected_fitness_score?.[0]?.value ?? 0)),
        },
      ]
    : [];

  // Historical weekly productivity trend + the trend engine's projected future weeks,
  // concatenated chronologically for a single "past -> predicted" growth line.
  // The predicted point is anchored to the study engine's last *active* week, which can
  // fall before the current calendar week if the user hasn't logged a session recently —
  // filter out anything that wouldn't chronologically follow the historical portion, so
  // the line never shows a "future" point landing on/before data already on the chart.
  const lastHistoricalWeek = weeklyTrend.length > 0
    ? new Date(weeklyTrend[weeklyTrend.length - 1].week_start)
    : null;
  const futureChartData = [
    ...weeklyTrend.map((w) => ({
      month: formatShortDate(w.week_start),
      score: Math.round(clampPct(w.average_productivity_score)),
    })),
    ...(trend?.study?.projected_productivity ?? [])
      .filter((p) => !lastHistoricalWeek || new Date(p.period) > lastHistoricalWeek)
      .map((p) => ({
        month: formatShortDate(p.period),
        score: Math.round(clampPct(p.value)),
      })),
  ];

  const aiInsights = trend
    ? [
        `Predicted savings next month: ${formatCurrency(
          Math.round(trend.savings?.projected_savings?.[0]?.value ?? 0), currency
        )} (data sufficiency ${Math.round((trend.savings?.confidence_score ?? 0) * 100)}%)`,
        `Predicted study score next week: ${Math.round(
          clampPct(trend.study?.projected_productivity?.[0]?.value ?? 0)
        )}% (data sufficiency ${Math.round((trend.study?.productivity_confidence_score ?? 0) * 100)}%)`,
        `Predicted fitness score next week: ${Math.round(
          clampPct(trend.fitness?.projected_fitness_score?.[0]?.value ?? 0)
        )}% (data sufficiency ${Math.round((trend.fitness?.confidence_score ?? 0) * 100)}%)`,
        ...(trend.study?.predicted_exam_score != null
          ? [`Predicted exam score: ${Math.round(clampPct(trend.study.predicted_exam_score))}%`]
          : []),
        `Overall prediction confidence: ${Math.round((trend.overall_confidence_score ?? 0) * 100)}%`,
      ]
    : [];

  return (

    <div>

      <h2 className="mb-6 text-2xl font-semibold text-slate-800 dark:text-slate-100">AI Prediction Dashboard</h2>

      <div role="tablist" aria-label="Prediction views" className="mb-6 flex gap-1 border-b border-slate-200 dark:border-slate-700">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            role="tab"
            id={`tab-${tab.id}`}
            aria-selected={activeTab === tab.id}
            aria-controls={`panel-${tab.id}`}
            onClick={() => setActiveTab(tab.id)}
            className={`-mb-px border-b-2 px-1 py-2.5 text-sm font-semibold ${
              activeTab === tab.id
                ? "border-indigo-600 text-indigo-600 dark:text-indigo-400"
                : "border-transparent text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {isLoading ? (
        <div className="flex flex-col gap-5">
          <SkeletonStatGrid count={4} />
          <SkeletonChart />
        </div>
      ) : activeTab === "forecasts" ? (
        <div role="tabpanel" id="panel-forecasts" aria-labelledby="tab-forecasts" className="flex flex-col gap-6">
          <PredictionSummary history={derivedHistory} />

          <PredictionCards predictions={predictionCards} />

          <FutureChart data={futureChartData} />
          <AIInsights insights={aiInsights} />

          <GoalTrendList goals={trend?.goals} />

          <PredictionHistory history={derivedHistory} />
        </div>
      ) : (
        <div role="tabpanel" id="panel-what-if" aria-labelledby="tab-what-if" className="flex flex-col gap-6">
          <div role="tablist" aria-label="What-if domains" className="flex flex-wrap gap-2">
            {WHAT_IF_SUBTABS.map((subtab) => (
              <button
                key={subtab.id}
                role="tab"
                aria-selected={whatIfSubtab === subtab.id}
                onClick={() => setWhatIfSubtab(subtab.id)}
                className={`rounded-full px-3 py-1.5 text-xs font-semibold ${
                  whatIfSubtab === subtab.id
                    ? "bg-indigo-600 text-white"
                    : "bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-700 dark:text-slate-300 dark:hover:bg-slate-600"
                }`}
              >
                {subtab.label}
              </button>
            ))}
          </div>

          {whatIfSubtab === "finance" && <SimulationForm />}
          {whatIfSubtab === "study" && <StudySimulationForm />}
          {whatIfSubtab === "fitness" && <FitnessSimulationForm />}
          {whatIfSubtab === "hybrid" && <HybridSimulationForm />}
          {whatIfSubtab === "compare" && (
            <div className="flex flex-col gap-6">
              <DomainComparison />
              <Suspense fallback={<SkeletonChart />}>
                <ScenarioExplorer />
              </Suspense>
            </div>
          )}

          <SimulationHistoryList />
        </div>
      )}

    </div>

  );

}

export default Prediction;