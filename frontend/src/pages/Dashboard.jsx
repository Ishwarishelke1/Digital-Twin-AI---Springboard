import { useState, useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import { CheckCircle2, Circle, ChevronDown } from "lucide-react";
import { toast } from "react-toastify";
import { RadialBarChart, RadialBar, ResponsiveContainer } from "recharts";

import FinanceChart from "../components/FinanceChart";
import StudyChart from "../components/StudyChart";
import DigitalTwinCard from "../components/DigitalTwinCard";
import GoalForm from "../components/GoalForm";
import Card from "../components/ui/Card";
import Button from "../components/ui/Button";
import Badge from "../components/ui/Badge";
import EmptyState from "../components/ui/EmptyState";
import Modal from "../components/ui/Modal";
import { StatGrid, StatTile } from "../components/ui/StatTile";
import { SkeletonStatGrid, SkeletonChart, SkeletonTable } from "../components/ui/Skeleton";

import { getUser, addGoal } from "../services/userService";
import { getCashflow } from "../services/financeService";
import { getSessions } from "../services/studyService";
import { getTrendSummary } from "../services/trendService";
import { getSavingsForecast } from "../services/forecastService";
import { getProductivityScore } from "../services/productivityService";
import { getConsistencyScore } from "../services/habitAnalyticsService";
import { getActivityHistory } from "../services/activityService";
import { buildChartData, computeSavingsRate, buildStudyChartData, appendSavingsForecast } from "../utils/dashboardHelpers";
import { activityBadgeTone } from "../utils/activityBadge";
import { CHART_COLORS } from "../utils/chartColors";
import { formatCurrency } from "../utils/currency";
import { useAuth } from "../context/useAuth";

/**
 * Compact circular gauge for a KPI-vs-target value (savings rate, consistency
 * score) — replaces a plain percentage + separate progress bar with a single
 * unified visual, per the "performance vs target" chart guidance for exactly
 * this data shape. Center label uses the same absolute-overlay technique as
 * SavingsProgress.jsx's donut chart.
 */
function GoalGauge({ percentage, color }) {
  const clamped = Math.min(100, Math.max(0, percentage ?? 0));
  const data = [{ value: clamped, fill: color }];

  return (
    <div className="relative mx-auto h-28 w-28">
      <ResponsiveContainer width="100%" height="100%">
        <RadialBarChart
          innerRadius="72%"
          outerRadius="100%"
          barSize={10}
          data={data}
          startAngle={90}
          endAngle={-270}
        >
          <RadialBar
            dataKey="value"
            background={{ fill: CHART_COLORS.grid }}
            cornerRadius={5}
            isAnimationActive={false}
          />
        </RadialBarChart>
      </ResponsiveContainer>
      <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
        <span className="font-mono text-xl font-semibold tabular-nums text-slate-800 dark:text-slate-100">
          {Math.round(clamped)}%
        </span>
      </div>
    </div>
  );
}

/** Quick-add: each option deep-links to the page that already owns that record's form. */
function AddRecordMenu() {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    function onClickOutside(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    }
    function onKey(e) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onClickOutside);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClickOutside);
      document.removeEventListener("keydown", onKey);
    };
  }, []);

  return (
    <div className="relative" ref={ref}>
      <Button onClick={() => setOpen((o) => !o)} aria-haspopup="menu" aria-expanded={open}>
        + Add Record <ChevronDown size={15} strokeWidth={2} />
      </Button>
      {open && (
        <div role="menu" className="absolute right-0 z-10 mt-2 w-48 overflow-hidden rounded-lg border border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-800 shadow-md">
          <Link role="menuitem" to="/finance" className="block px-4 py-2.5 text-sm text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700/40">Add Transaction</Link>
          <Link role="menuitem" to="/study" className="block px-4 py-2.5 text-sm text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700/40">Add Study Session</Link>
          <Link role="menuitem" to="/habits" className="block px-4 py-2.5 text-sm text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700/40">Add Habit Log</Link>
        </div>
      )}
    </div>
  );
}

function Dashboard() {
  const { refreshUser } = useAuth();
  const [userData, setUserData]         = useState(null);
  // Dashboard fetches its own user copy rather than reading context.
  const currency = userData?.preferences?.currency ?? "USD";
  const [financeChart, setFinanceChart] = useState([]);
  const [studyChart, setStudyChart]     = useState([]);
  const [savingsRatePct, setSavingsRatePct] = useState(null);
  const [productivityScore, setProductivityScore] = useState(null);
  const [consistencyScore, setConsistencyScore]   = useState(null);
  const [trend, setTrend]               = useState(null);
  const [recentActivity, setRecentActivity] = useState([]);
  const [isLoading, setIsLoading]       = useState(true);
  const [addingGoal, setAddingGoal]     = useState(false);
  const [forecastMethod, setForecastMethod] = useState(null);

  useEffect(() => {
    async function fetchAll() {
      try {
        const [user, cashflow, studySessions, trendSummary, productivity, consistency, activity, savingsForecast] =
          await Promise.all([
            getUser(),
            getCashflow(6),
            getSessions({ limit: 50 }),
            getTrendSummary(),
            getProductivityScore(),
            getConsistencyScore(),
            getActivityHistory({ limit: 5 }),
            // Non-fatal: the chart falls back to history alone if this fails,
            // rather than taking the whole dashboard down for a projection.
            getSavingsForecast(3).catch(() => null),
          ]);

        setUserData(user);
        setFinanceChart(appendSavingsForecast(buildChartData(cashflow), savingsForecast?.projections));
        setForecastMethod(savingsForecast?.method_used ?? null);
        setSavingsRatePct(computeSavingsRate(cashflow));
        setStudyChart(buildStudyChartData(studySessions.data || []));
        setTrend(trendSummary);
        setProductivityScore(productivity);
        setConsistencyScore(consistency);
        setRecentActivity(activity.data || []);
      } catch (err) {
        console.error("Dashboard fetch error:", err);
        toast.error("Could not load your dashboard. Please try again later.");
      } finally {
        setIsLoading(false);
      }
    }
    fetchAll();
  }, []);

  // Stat cards are driven by the Milestone 2 analytics engines (Financial
  // Forecasting, Productivity Analytics, Habit Analytics) rather than
  // User.digital_twin_state, which nothing in the backend ever computes/writes.
  const profile = userData?.profile;
  const goals   = userData?.active_goals ?? [];

  const savingsRate    = savingsRatePct != null ? `${savingsRatePct.toFixed(1)}%` : "—";
  const studyScore     = productivityScore ? `${Math.round(productivityScore.productivity_score)}%` : "—";
  const habitRate      = consistencyScore ? `${Math.round(consistencyScore.consistency_score)}%` : "—";
  const goalsCompleted = goals.length ? `${goals.filter(g => g.status === "COMPLETED").length}/${goals.length}` : "—";

  const handleAddGoal = async (goalPayload) => {
    const updatedUser = await addGoal(goalPayload);
    setUserData(updatedUser);
    // Keep AuthContext's copy in sync too — Finance.jsx and Study.jsx read
    // active_goals off useAuth() for their goal-linking dropdowns, not off
    // this page's own userData, so without this they'd keep showing the
    // pre-add goal list until the next login.
    await refreshUser();
    setAddingGoal(false);
    toast.success("Goal added successfully.");
  };

  return (
    <div>

      {/* Header */}

      <div className="mb-8 flex flex-wrap items-center justify-between gap-4">

        <div>
          <h2 className="text-3xl font-semibold text-slate-800 dark:text-slate-100">Dashboard</h2>

          <p className="mt-1.5 text-slate-500 dark:text-slate-400">
            {isLoading
              ? "Loading your Digital Twin overview..."
              : `Welcome back${profile?.name ? ", " + profile.name : ""}! Here's your Digital Twin overview.`}
          </p>
        </div>

        <AddRecordMenu />

      </div>

      {isLoading ? (
        <div className="flex flex-col gap-5">
          <SkeletonStatGrid count={4} />
          <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
            <div className="lg:col-span-2"><SkeletonChart /></div>
            <SkeletonChart />
          </div>
          <SkeletonTable rows={5} cols={3} />
        </div>
      ) : (
        <>
          {/* Summary Cards */}

          <StatGrid>
            <Link to="/finance" className="block rounded-2xl transition-transform duration-150 ease-out hover:-translate-y-0.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 motion-reduce:transition-none motion-reduce:hover:translate-y-0">
              <StatTile
                accent="indigo"
                label="Savings Rate"
                value={savingsRate}
                sublabel={
                  trend?.savings?.projected_savings?.length
                    ? `Predicted next month: ${formatCurrency(Math.round(trend.savings.projected_savings[0].value), currency)}`
                    : "No transactions logged yet"
                }
              />
            </Link>

            <Link to="/study" className="block rounded-2xl transition-transform duration-150 ease-out hover:-translate-y-0.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 motion-reduce:transition-none motion-reduce:hover:translate-y-0">
              <StatTile
                accent="emerald"
                label="Study Consistency"
                value={studyScore}
                sublabel={
                  trend?.study?.predicted_exam_score != null
                    ? `Predicted exam: ${Math.round(trend.study.predicted_exam_score)}%`
                    : "No study sessions logged yet"
                }
              />
            </Link>

            <Link to="/habits" className="block rounded-2xl transition-transform duration-150 ease-out hover:-translate-y-0.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 motion-reduce:transition-none motion-reduce:hover:translate-y-0">
              <StatTile
                accent="amber"
                label="Habit Score"
                value={habitRate}
                sublabel={
                  trend?.fitness?.projected_fitness_score?.length
                    ? `Predicted next week: ${Math.round(trend.fitness.projected_fitness_score[0].value)}%`
                    : "No habit logs yet"
                }
              />
            </Link>

            <Link to="/profile" className="block rounded-2xl transition-transform duration-150 ease-out hover:-translate-y-0.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 motion-reduce:transition-none motion-reduce:hover:translate-y-0">
              <StatTile accent="neutral" label="Goals Completed" value={goalsCompleted} sublabel="Keep going" />
            </Link>
          </StatGrid>

          {/* Charts */}

          <div className="mb-8 mt-8 grid grid-cols-1 gap-5 lg:grid-cols-3">

            <Card className="lg:col-span-2">
              <h3 className="mb-5 text-lg font-semibold text-slate-800 dark:text-slate-100">Financial Overview</h3>
              <FinanceChart data={financeChart} currency={currency} forecastMethod={forecastMethod} />
            </Card>

            <Card>
              <StudyChart data={studyChart} />
            </Card>

          </div>

          {/* Progress Cards */}

          <div className="mb-8 grid grid-cols-1 gap-5 md:grid-cols-3">

            <Card className="text-center">
              <h3 className="text-lg font-semibold text-slate-800 dark:text-slate-100">Financial Goal</h3>
              <div className="my-4" role="progressbar" aria-label="Savings rate progress" aria-valuenow={savingsRatePct != null ? Math.min(100, savingsRatePct) : 0} aria-valuemin={0} aria-valuemax={100}>
                <GoalGauge percentage={savingsRatePct} color={CHART_COLORS.action} />
              </div>
              <p className="text-sm text-slate-500 dark:text-slate-400">{savingsRatePct != null ? "Savings Rate" : "No data yet"}</p>
            </Card>

            <Card className="text-center">
              <h3 className="text-lg font-semibold text-slate-800 dark:text-slate-100">Study Goal</h3>
              <div className="my-4" role="progressbar" aria-label="Study consistency progress" aria-valuenow={productivityScore ? Math.min(100, productivityScore.productivity_score) : 0} aria-valuemin={0} aria-valuemax={100}>
                <GoalGauge percentage={productivityScore?.productivity_score} color={CHART_COLORS.positive} />
              </div>
              <p className="text-sm text-slate-500 dark:text-slate-400">{productivityScore ? "Consistency" : "No data yet"}</p>
            </Card>

            <Card className="text-center">
              <h3 className="text-lg font-semibold text-slate-800 dark:text-slate-100">Lifestyle Goal</h3>
              <div className="my-4" role="progressbar" aria-label="Lifestyle score progress" aria-valuenow={consistencyScore ? Math.min(100, consistencyScore.consistency_score) : 0} aria-valuemin={0} aria-valuemax={100}>
                <GoalGauge percentage={consistencyScore?.consistency_score} color={CHART_COLORS.warning} />
              </div>
              <p className="text-sm text-slate-500 dark:text-slate-400">{consistencyScore ? "Lifestyle Score (out of 100)" : "No data yet"}</p>
            </Card>

          </div>

          {/* Bottom Cards */}

          <div className="mb-8 grid grid-cols-1 gap-5 lg:grid-cols-3">

            <Card className="border-t-4 border-t-violet-500 lg:col-span-2">
              <h3 className="text-lg font-semibold text-violet-600 dark:text-violet-400">✦ AI Recommendation</h3>

              <p className="mt-4 text-sm text-slate-600 dark:text-slate-400">
                {trend
                  ? `Predicted savings next month: ${formatCurrency(
                      Math.round(trend.savings?.projected_savings?.[0]?.value ?? 0), currency
                    )} (data sufficiency ${Math.round((trend.savings?.confidence_score ?? 0) * 100)}%).`
                  : "Log a few transactions on the Finance page to get a personalized savings prediction."}
              </p>

              <p className="mt-3 text-sm text-slate-600 dark:text-slate-400">
                {trend
                  ? `Predicted study score next week: ${Math.round(
                      trend.study?.projected_productivity?.[0]?.value ?? 0
                    )}% (data sufficiency ${Math.round((trend.study?.productivity_confidence_score ?? 0) * 100)}%).`
                  : "Log a few study sessions to get a personalized study prediction."}
              </p>
            </Card>

            <Card>
              <div className="flex items-center justify-between gap-3">
                <h3 className="text-lg font-semibold text-slate-800 dark:text-slate-100">Active Goals</h3>
                <div className="flex items-center gap-3">
                  <Button
                    variant="ghost"
                    className="px-2 py-1 text-xs"
                    onClick={() => setAddingGoal(true)}
                  >
                    + Add Goal
                  </Button>
                  <Link to="/goals" className="text-sm font-medium text-indigo-600 dark:text-indigo-400 hover:underline">View all</Link>
                </div>
              </div>

              <ul className="mt-4 space-y-3">
                {goals.length > 0
                  ? goals.slice(0, 5).map((g) => {
                      const done = g.status === "COMPLETED";
                      return (
                        <li key={g.goal_id} className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300">
                          {done
                            ? <CheckCircle2 size={15} strokeWidth={2} className="shrink-0 text-emerald-500" />
                            : <Circle       size={15} strokeWidth={2} className="shrink-0 text-slate-300" />}
                          {g.title}
                        </li>
                      );
                    })
                  : (
                    <li className="text-sm italic text-slate-400">
                      No active goals yet. Add one above or from the Goals page.
                    </li>
                  )}
              </ul>
            </Card>

          </div>

          {/* Digital Twin State — the composite snapshot computed by the
              backend and returned on every GET /users/me, previously fetched
              here but never rendered anywhere in the app. */}
          <div className="mb-8">
            <DigitalTwinCard twinState={userData?.digital_twin_state} />
          </div>

          {/* Recent Activity — live feed from the /activity endpoint, replacing
              the previous 5 hardcoded rows */}

          <Card className="overflow-x-auto">

            <div className="mb-5 flex items-center justify-between">
              <h3 className="text-lg font-semibold text-slate-800 dark:text-slate-100">Recent Activity</h3>
              <Link to="/activity" className="text-sm font-medium text-indigo-600 dark:text-indigo-400 hover:underline">View all</Link>
            </div>

            {recentActivity.length === 0 ? (
              <EmptyState title="No activity yet" message="Actions you take across Digital Twin will show up here." />
            ) : (
              <table className="w-full border-collapse text-sm">
                <thead>
                  <tr>
                    <th className="border-b border-slate-200 dark:border-slate-700 p-2.5 text-left font-semibold text-slate-500 dark:text-slate-400">Time</th>
                    <th className="border-b border-slate-200 dark:border-slate-700 p-2.5 text-left font-semibold text-slate-500 dark:text-slate-400">Action</th>
                    <th className="border-b border-slate-200 dark:border-slate-700 p-2.5 text-left font-semibold text-slate-500 dark:text-slate-400">Description</th>
                  </tr>
                </thead>
                <tbody>
                  {recentActivity.map((act) => (
                    <tr key={act.id} className="hover:bg-slate-50 dark:hover:bg-slate-700/40">
                      <td className="border-b border-slate-100 dark:border-slate-700 p-2.5 font-mono tabular-nums text-slate-600 dark:text-slate-400">
                        {new Date(act.timestamp).toLocaleDateString(undefined, { month: "short", day: "numeric" })}
                      </td>
                      <td className="border-b border-slate-100 dark:border-slate-700 p-2.5">
                        <Badge tone={activityBadgeTone(act.action_type)}>{(act.action_type || "").replace(/_/g, " ")}</Badge>
                      </td>
                      <td className="border-b border-slate-100 dark:border-slate-700 p-2.5 text-slate-600 dark:text-slate-400">{act.description || "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}

          </Card>
        </>
      )}

      <Modal open={addingGoal} onClose={() => setAddingGoal(false)} title="New Goal" maxWidth="max-w-lg">
        <GoalForm onSave={handleAddGoal} onCancel={() => setAddingGoal(false)} />
      </Modal>

    </div>
  );
}

export default Dashboard;
