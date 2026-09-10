import { useState, useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "react-toastify";

import GoalCard from "../components/GoalCard";
import GoalForm from "../components/GoalForm";
import ConfirmDialog from "../components/ConfirmDialog";
import Button from "../components/ui/Button";
import Modal from "../components/ui/Modal";
import EmptyState from "../components/ui/EmptyState";

import { addGoal, updateGoal, deleteGoal, getGoalPredictions } from "../services/userService";
import { useAuth } from "../context/useAuth";

/**
 * Goals — a dedicated view of every goal across Finance/Study/Habit/Fitness/
 * Career, split into Active and Completed. Reads `user` straight off
 * AuthContext (ProtectedRoute already guarantees it's loaded before any
 * protected page mounts) rather than fetching its own copy, and calls
 * `refreshUser()` after every mutation — that's the same context Finance.jsx
 * and Study.jsx read `active_goals` from for their goal-linking dropdowns, so
 * a goal added/edited/deleted here shows up there immediately instead of
 * only after the next login.
 */
/* Goals arrive in the order they were created, which mixes a savings target in
 * between two study goals for no reason a reader can see. Grouping by category
 * puts everything about one part of your life together. Anything outside this
 * list sorts after it rather than being dropped, so a category added later still
 * appears — at the end, until it is given a place here.
 *
 * Within a category, the nearest deadline comes first: it is the goal most
 * likely to need attention, and undated goals sort last rather than to 1970. */
const CATEGORY_ORDER = ["FINANCE", "HABIT", "STUDY", "FITNESS", "CAREER"];

function sortGoals(goals) {
  return [...goals].sort((a, b) => {
    const categoryDiff =
      (CATEGORY_ORDER.indexOf(a.category) + 1 || CATEGORY_ORDER.length + 1) -
      (CATEGORY_ORDER.indexOf(b.category) + 1 || CATEGORY_ORDER.length + 1);
    if (categoryDiff !== 0) return categoryDiff;

    const aDate = a.target_date ? new Date(a.target_date).getTime() : Infinity;
    const bDate = b.target_date ? new Date(b.target_date).getTime() : Infinity;
    if (aDate !== bDate) return aDate - bDate;

    return (a.title ?? "").localeCompare(b.title ?? "");
  });
}

const CATEGORY_LABELS = {
  FINANCE: "Finance",
  HABIT: "Habits",
  STUDY: "Study",
  FITNESS: "Fitness",
  CAREER: "Career",
};

/* Groups consecutive runs rather than bucketing by category, so the headings can
 * only ever agree with sortGoals above — re-deriving an order here would give the
 * page two sources of truth about what comes first. An unrecognised category
 * still gets a run, labelled with its raw value. */
function groupByCategory(goals) {
  return goals.reduce((groups, goal) => {
    const last = groups[groups.length - 1];
    if (last && last.category === goal.category) last.goals.push(goal);
    else groups.push({ category: goal.category, goals: [goal] });
    return groups;
  }, []);
}

/** One labelled run of goal cards per category. */
function GoalGroups({ goals, completed = false, predictions, onEdit, onDelete }) {
  return (
    <div className="flex flex-col gap-6">
      {groupByCategory(goals).map(({ category, goals: groupGoals }) => (
        <div key={category}>
          <p className="mb-3 font-mono text-xs font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">
            {CATEGORY_LABELS[category] ?? category}
            <span className="ml-2 font-sans normal-case tracking-normal">
              {groupGoals.length}
            </span>
          </p>

          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {groupGoals.map((g) => (
              <GoalCard
                key={g.goal_id}
                title={g.title}
                value={`${Number(g.current_value).toLocaleString()} / ${Number(g.target_value).toLocaleString()} ${g.unit}`}
                completed={completed}
                targetDate={g.target_date}
                prediction={predictions[g.goal_id]}
                onEdit={() => onEdit(g)}
                onDelete={() => onDelete(g.goal_id)}
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function Goals() {
  const { user, refreshUser } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();

  /* Arriving from a domain page's "Add a goal" tile opens the form straight
   * away — landing on a list and hunting for a button would undo the point of
   * the tile. Both values are read once, in a state initialiser, so clearing the
   * query string below cannot close a form the user is still filling in. */
  const [addingGoal, setAddingGoal] = useState(() => searchParams.get("new") === "1");
  const [presetCategory] = useState(() => searchParams.get("category") || undefined);
  const [editingGoal, setEditingGoal] = useState(null);
  const [confirmDeleteGoalId, setConfirmDeleteGoalId] = useState(null);

  useEffect(() => {
    // Consume the deep-link params. Replaces rather than pushes, so Back still
    // returns to the page the user came from instead of re-triggering the form.
    if (searchParams.has("new") || searchParams.has("category")) {
      setSearchParams({}, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  // Keyed by goal_id. Fetched separately from the user payload: predictions need
  // the model loaded and a per-goal feature build, so a failure here must leave
  // the goals rendering rather than take the page down.
  const [predictions, setPredictions] = useState({});

  const goalCount = user?.active_goals?.length ?? 0;
  useEffect(() => {
    let cancelled = false;
    getGoalPredictions()
      .then((rows) => {
        if (!cancelled) setPredictions(Object.fromEntries(rows.map((r) => [r.goal_id, r])));
      })
      .catch(() => {
        if (!cancelled) setPredictions({});
      });
    return () => {
      cancelled = true;
    };
  }, [goalCount]);

  const handleAddGoal = async (goalPayload) => {
    await addGoal(goalPayload);
    await refreshUser();
    setAddingGoal(false);
    toast.success("Goal added successfully.");
  };

  const startEditGoal = (goal) => {
    setEditingGoal({
      goal_id: goal.goal_id,
      title: goal.title,
      category: goal.category,
      target_value: goal.target_value,
      current_value: goal.current_value,
      unit: goal.unit,
      target_date: goal.target_date ? goal.target_date.substring(0, 10) : "",
    });
  };

  const handleUpdateGoal = async (goalId, payload) => {
    await updateGoal(goalId, payload);
    await refreshUser();
    setEditingGoal(null);
    toast.success("Goal updated.");
  };

  const handleDeleteGoal = (goalId) => setConfirmDeleteGoalId(goalId);

  const confirmDeleteGoal = async () => {
    const goalId = confirmDeleteGoalId;
    setConfirmDeleteGoalId(null);
    try {
      await deleteGoal(goalId);
      await refreshUser();
      toast.success("Goal deleted.");
    } catch (err) {
      console.error("Failed to delete goal:", err);
      toast.error("Failed to delete goal.");
    }
  };

  const goals = user?.active_goals ?? [];
  const activeGoals = sortGoals(goals.filter((g) => g.status !== "COMPLETED"));
  const completedGoals = sortGoals(goals.filter((g) => g.status === "COMPLETED"));

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-semibold text-slate-800 dark:text-slate-100">Goals</h2>
          <p className="mt-1.5 text-sm text-slate-500 dark:text-slate-400">
            {activeGoals.length} active, {completedGoals.length} completed
          </p>
        </div>

        {addingGoal ? null : (
          <Button onClick={() => setAddingGoal(true)}>+ New Goal</Button>
        )}
      </div>

      {addingGoal && (
        <div className="@container mb-6 rounded-2xl bg-white p-6 shadow-sm dark:bg-slate-800">
          <GoalForm
            onSave={handleAddGoal}
            onCancel={() => setAddingGoal(false)}
            defaultCategory={presetCategory}
          />
        </div>
      )}

      <section className="mb-8">
        <h3 className="mb-4 text-lg font-semibold text-slate-800 dark:text-slate-100">Active Goals</h3>
        {activeGoals.length > 0 ? (
          <GoalGroups
            goals={activeGoals}
            predictions={predictions}
            onEdit={startEditGoal}
            onDelete={handleDeleteGoal}
          />
        ) : (
          <EmptyState title="No active goals" message="Add a goal above to start tracking progress toward it." />
        )}
      </section>

      <section>
        <h3 className="mb-4 text-lg font-semibold text-slate-800 dark:text-slate-100">Completed Goals</h3>
        {completedGoals.length > 0 ? (
          <GoalGroups
            goals={completedGoals}
            completed
            predictions={predictions}
            onEdit={startEditGoal}
            onDelete={handleDeleteGoal}
          />
        ) : (
          <EmptyState title="No completed goals yet" message="Goals move here automatically once you reach their target." />
        )}
      </section>

      <Modal open={!!editingGoal} onClose={() => setEditingGoal(null)} title="Edit Goal" maxWidth="max-w-lg">
        <GoalForm
          initialData={editingGoal}
          onUpdate={handleUpdateGoal}
          onCancel={() => setEditingGoal(null)}
        />
      </Modal>

      <ConfirmDialog
        open={confirmDeleteGoalId !== null}
        title="Delete Goal"
        message="Are you sure you want to delete this goal? This action cannot be undone."
        confirmLabel="Delete"
        danger
        onConfirm={confirmDeleteGoal}
        onCancel={() => setConfirmDeleteGoalId(null)}
      />
    </div>
  );
}

export default Goals;
