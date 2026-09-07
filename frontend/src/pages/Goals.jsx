import { useState, useEffect } from "react";
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
function Goals() {
  const { user, refreshUser } = useAuth();
  const [addingGoal, setAddingGoal] = useState(false);
  const [editingGoal, setEditingGoal] = useState(null);
  const [confirmDeleteGoalId, setConfirmDeleteGoalId] = useState(null);
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
  const activeGoals = goals.filter((g) => g.status !== "COMPLETED");
  const completedGoals = goals.filter((g) => g.status === "COMPLETED");

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
        <div className="mb-6">
          <GoalForm onSave={handleAddGoal} onCancel={() => setAddingGoal(false)} />
        </div>
      )}

      <section className="mb-8">
        <h3 className="mb-4 text-lg font-semibold text-slate-800 dark:text-slate-100">Active Goals</h3>
        {activeGoals.length > 0 ? (
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {activeGoals.map((g) => (
              <GoalCard
                key={g.goal_id}
                title={g.title}
                value={`${Number(g.current_value).toLocaleString()} / ${Number(g.target_value).toLocaleString()} ${g.unit}`}
                targetDate={g.target_date}
                prediction={predictions[g.goal_id]}
                onEdit={() => startEditGoal(g)}
                onDelete={() => handleDeleteGoal(g.goal_id)}
              />
            ))}
          </div>
        ) : (
          <EmptyState title="No active goals" message="Add a goal above to start tracking progress toward it." />
        )}
      </section>

      <section>
        <h3 className="mb-4 text-lg font-semibold text-slate-800 dark:text-slate-100">Completed Goals</h3>
        {completedGoals.length > 0 ? (
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {completedGoals.map((g) => (
              <GoalCard
                key={g.goal_id}
                title={g.title}
                value={`${Number(g.current_value).toLocaleString()} / ${Number(g.target_value).toLocaleString()} ${g.unit}`}
                completed
                targetDate={g.target_date}
                prediction={predictions[g.goal_id]}
                onEdit={() => startEditGoal(g)}
                onDelete={() => handleDeleteGoal(g.goal_id)}
              />
            ))}
          </div>
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
