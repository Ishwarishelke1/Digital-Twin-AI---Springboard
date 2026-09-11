import { useState, useEffect } from "react";
import { toast } from "react-toastify";

import HabitSummary from "../components/HabitSummary";
import HabitForm from "../components/HabitForm";
import HabitChart from "../components/HabitChart";
import HabitProgress from "../components/HabitProgress";
import GoalProgressCard from "../components/GoalProgressCard";
import AddGoalCard from "../components/AddGoalCard";
import HabitTable from "../components/HabitTable";
import AIRecommendationPanel from "../components/AIRecommendationPanel";
import useAIRecommendations from "../hooks/useAIRecommendations";
import { getHabitRecommendations } from "../services/recommendationService";
import ConfirmDialog from "../components/ConfirmDialog";
import Pagination from "../components/Pagination";
import Button from "../components/ui/Button";
import Drawer from "../components/ui/Drawer";
import StaggerIn from "../components/ui/StaggerIn";
import {
  SkeletonStatGrid,
  SkeletonChart,
  SkeletonTable,
} from "../components/ui/Skeleton";
import {
  getHabitLogs,
  logDailyHabit,
  deleteHabitLog,
} from "../services/habitService";
import { getUser } from "../services/userService";
import {
  getHabitTrend,
} from "../services/habitAnalyticsService";
import { getApiErrorMessage } from "../utils/apiError";

const MOOD_LABELS = {
  5: "Excellent",
  4: "Happy",
  3: "Normal",
  2: "Sad",
  1: "Sad",
};

function toDisplayHabit(record) {
  return {
    ...record,
    date: new Date(record.log_date).toLocaleDateString(),
    water: record.water_intake_liters,
    sleep: record.sleep_hours,
    exercise: record.exercise_minutes,
    mood: MOOD_LABELS[record.mood_rating] ?? "Normal",
  };
}

function buildHabitChartData(dailyTrend) {
  return dailyTrend.map((point) => ({
    day: new Date(point.date).toLocaleDateString(undefined, {
      weekday: "short",
    }),
    score: Math.round(point.habit_score),
  }));
}

function Habits() {
  const [user, setUser] = useState(null);

  const recommendations = useAIRecommendations(getHabitRecommendations);

  const [habitList, setHabitList] = useState([]);
  const [habitChartData, setHabitChartData] = useState([]);

  const [isLoading, setIsLoading] = useState(true);
  const [confirmDeleteId, setConfirmDeleteId] = useState(null);
  const [addDrawerOpen, setAddDrawerOpen] = useState(false);

  const [moodFilter, setMoodFilter] = useState("");
  const [sleepFilter, setSleepFilter] = useState("");
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [isTableLoading, setIsTableLoading] = useState(false);

  /*
   * Get all active HABIT goals.
   */
  const habitGoals =
    user?.active_goals?.filter(
      (goal) => goal.category === "HABIT"
    ) || [];

  useEffect(() => {
    async function fetchHabits() {
      try {
        // The analytics summary used to be fetched here to build the insight
        // lines client-side. The recommendations endpoint computes the same
        // summary server-side now, so this page no longer asks for it.
        const [result, trend, userData] =
          await Promise.all([
            getHabitLogs({ limit: 30 }),
            getHabitTrend({ dailyDays: 7 }),
            getUser(),
          ]);

        setHabitList(
          (result.data || []).map(toDisplayHabit)
        );

        setTotalPages(result.total_pages || 1);

        setHabitChartData(
          buildHabitChartData(trend.daily || [])
        );

        setUser(userData);
      } catch (err) {
        console.error("Failed to fetch habit logs:", err);

        toast.error(
          "Could not load habit logs. Please try again later."
        );
      } finally {
        setIsLoading(false);
      }
    }

    fetchHabits();
  }, []);

  useEffect(() => {
    if (isLoading) return;

    let cancelled = false;

    async function fetchTablePage() {
      setIsTableLoading(true);

      try {
        const result = await getHabitLogs({
          page,
          limit: 30,
          ...(moodFilter ? { mood_rating: Number(moodFilter) } : {}),
          ...(sleepFilter ? { sleep_band: sleepFilter } : {}),
        });

        if (cancelled) return;

        setHabitList(
          (result.data || []).map(toDisplayHabit)
        );

        setTotalPages(result.total_pages || 1);
      } catch (err) {
        if (cancelled) return;

        console.error("Failed to fetch habit logs:", err);

        toast.error(
          "Could not load habit logs. Please try again later."
        );
      } finally {
        if (!cancelled) {
          setIsTableLoading(false);
        }
      }
    }

    fetchTablePage();

    return () => {
      cancelled = true;
    };

    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, moodFilter, sleepFilter]);

  // Every filter change resets to page 1: the row you were looking at on page 3
  // may not exist under the new filter.
  function handleMoodFilterChange(e) {
    setMoodFilter(e.target.value);
    setPage(1);
  }

  function handleSleepFilterChange(e) {
    setSleepFilter(e.target.value);
    setPage(1);
  }

  function clearFilters() {
    setMoodFilter("");
    setSleepFilter("");
    setPage(1);
  }

  async function addHabit(formData) {
    try {
      const moodMap = {
        Excellent: 5,
        Happy: 4,
        Normal: 3,
        Sad: 2,
      };

      const payload = {
        sleep_hours: Number(formData.sleep),

        exercise_minutes: Number(formData.exercise),

        water_intake_liters: Number(formData.water),

        screen_time_hours: Number(
          formData.screenTime || 0
        ),

        mood_rating: moodMap[formData.mood] ?? 3,

        /*
         * Habit Goal
         */
        linked_goal_id:
          formData.linked_goal_id || undefined,

        log_date: formData.date
          ? new Date(formData.date).toISOString()
          : undefined,
      };

      const newRecord = toDisplayHabit(
        await logDailyHabit(payload)
      );

      const trend = await getHabitTrend({
        dailyDays: 7,
      });

      setHabitChartData(
        buildHabitChartData(trend.daily || [])
      );

      setHabitList((prev) => {
        const sameDay = (h) =>
          new Date(h.log_date).toDateString() ===
          new Date(newRecord.log_date).toDateString();

        if (prev.some(sameDay)) {
          return prev.map((h) =>
            sameDay(h) ? newRecord : h
          );
        }

        return [newRecord, ...prev];
      });

      toast.success("Habit log saved successfully.");

      setAddDrawerOpen(false);
    } catch (err) {
      console.error("Failed to add habit log:", err);

      toast.error(
        getApiErrorMessage(
          err,
          "Failed to log habit. Please try again."
        )
      );

      throw err;
    }
  }

  const handleDelete = (id) => {
    setConfirmDeleteId(id);
  };

  const confirmDelete = async () => {
    const id = confirmDeleteId;

    setConfirmDeleteId(null);

    try {
      await deleteHabitLog(id);

      setHabitList((prev) =>
        prev.filter((h) => h.id !== id)
      );

      toast.success("Habit log deleted.");
    } catch (err) {
      console.error(
        "Failed to delete habit log:",
        err
      );

      toast.error("Failed to delete habit log.");
    }
  };

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <h2 className="text-2xl font-semibold text-slate-800 dark:text-slate-100">
          Habit Dashboard
        </h2>

        <Button
          onClick={() => setAddDrawerOpen(true)}
        >
          + Add Today's Habits
        </Button>
      </div>

      {isLoading ? (
        <div className="flex flex-col gap-5">
          <SkeletonStatGrid count={4} />
          <SkeletonChart />
          <SkeletonTable rows={6} cols={5} />
        </div>
      ) : (
        <div className="flex flex-col gap-6">
          <HabitSummary habits={habitList} />

          <HabitChart data={habitChartData} />

          {/* Habit goals — the same card Finance and Study use, replacing a
              bespoke text-only list that showed the same numbers without the
              progress ring.

              Fixed columns, not a flexing row: a single goal stretched to full
              width read as a layout choice rather than as "you have one goal".
              The add tile fills the first empty slot with the action someone
              looking at a short row most likely wants. */}
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {habitGoals.map((goal, i) => (
              <StaggerIn key={goal.goal_id} index={i}>
                <GoalProgressCard
                  goal={goal}
                  formatValue={(value) => Number(value).toLocaleString()}
                  unitLabel={goal.unit}
                />
              </StaggerIn>
            ))}

            <AddGoalCard
              category="HABIT"
              label={habitGoals.length > 0 ? "Add another goal" : "Add your first habit goal"}
              hint="Build a streak, hit a weekly target"
            />
          </div>

          <HabitProgress habits={habitList} />

          <AIRecommendationPanel
            title="AI Lifestyle Recommendations"
            items={recommendations.items}
            provider={recommendations.provider}
            generatedAt={recommendations.generatedAt}
            stale={recommendations.stale}
            isLoading={recommendations.isLoading}
            isGenerating={recommendations.isGenerating}
            onGenerate={recommendations.generate}
            emptyMessage="Log a few days of habits and recommendations will appear here."
          />

          <HabitTable
            habits={habitList}
            onDelete={handleDelete}
            isLoading={isTableLoading}
            moodFilter={moodFilter}
            sleepFilter={sleepFilter}
            onMoodFilterChange={handleMoodFilterChange}
            onSleepFilterChange={handleSleepFilterChange}
            onClearFilters={clearFilters}
          />

          <Pagination
            page={page}
            totalPages={totalPages}
            onPageChange={setPage}
            disabled={isTableLoading}
          />
        </div>
      )}

      <Drawer
        open={addDrawerOpen}
        onClose={() => setAddDrawerOpen(false)}
        title="Add Today's Habits"
      >
        {/* Pass HABIT goals to HabitForm */}
        <HabitForm
          addHabit={addHabit}
          goals={habitGoals}
        />
      </Drawer>

      <ConfirmDialog
        open={confirmDeleteId !== null}
        title="Delete Habit Log"
        message="Are you sure you want to delete this habit log? This action cannot be undone."
        confirmLabel="Delete"
        danger
        onConfirm={confirmDelete}
        onCancel={() => setConfirmDeleteId(null)}
      />
    </div>
  );
}

export default Habits;