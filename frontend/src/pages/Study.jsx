import { useState, useEffect } from "react";
import { toast } from "react-toastify";
import { useAuth } from "../context/useAuth";

import StudySummary from "../components/StudySummary";
import StudyForm from "../components/StudyForm";
import StudyChart from "../components/StudyChart";
import SubjectProgress from "../components/SubjectProgress";
import GoalProgressCard from "../components/GoalProgressCard";
import AddGoalCard from "../components/AddGoalCard";
import useAIRecommendations from "../hooks/useAIRecommendations";
import { getStudyRecommendations } from "../services/recommendationService";
import AIRecommendationPanel from "../components/AIRecommendationPanel";
import StudyTable from "../components/StudyTable";
import ConfirmDialog from "../components/ConfirmDialog";
import Pagination from "../components/Pagination";

import Button from "../components/ui/Button";
import { SkeletonStatGrid, SkeletonChart, SkeletonTable } from "../components/ui/Skeleton";
import Modal from "../components/ui/Modal";
import Drawer from "../components/ui/Drawer";

import {
  getSessions,
  createSession,
  updateSession,
  deleteSession,
  getSubjectPerformance,
} from "../services/studyService";

import { getProductivitySummary } from "../services/productivityService";

/** Builds SubjectProgress's [{ name, progress }] list. */
const DAY_NAMES = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

function buildWeeklyChart(sessions) {
  const totals = {
    Mon: 0,
    Tue: 0,
    Wed: 0,
    Thu: 0,
    Fri: 0,
    Sat: 0,
    Sun: 0,
  };

  for (const s of sessions) {
    const d = new Date(s.session_date || s.created_at);
    const label = DAY_NAMES[d.getDay()];
    totals[label] += Number(s.study_hours || 0);
  }

  return ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((day) => ({
    day,
    hours: Math.round(totals[day] * 10) / 10,
  }));
}

function Study() {
  const { user } = useAuth();

  /*
   * Only STUDY-category goals are shown in the Study form.
   *
   * Example:
   *   "Complete Python Course"
   *   "Study 100 Hours"
   *   "Score 90% in Exams"
   *
   * These come directly from Profile -> Goals.
   *
   * If the user has no STUDY goal, the form still works because
   * "No Goal" is always available.
   */
  const studyGoals =
    user?.active_goals?.filter((g) => g.category === "STUDY") ?? [];

  const recommendations = useAIRecommendations(getStudyRecommendations);

  const [sessions, setSessions] = useState([]);
  const [chartData, setChartData] = useState([]);
  const [subjectProgress, setSubjectProgress] = useState([]);
  const [productivitySummary, setProductivitySummary] = useState(null);
  const [isLoading, setIsLoading] = useState(true);

  const [editingRecord, setEditingRecord] = useState(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState(null);
  const [addDrawerOpen, setAddDrawerOpen] = useState(false);

  const [subjectFilter, setSubjectFilter] = useState("");
  const [sessionTypeFilter, setSessionTypeFilter] = useState("");
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [isTableLoading, setIsTableLoading] = useState(false);

  useEffect(() => {
    async function fetchSessions() {
      try {
        const [result, summary, subjectPerformance] = await Promise.all([
          getSessions({ limit: 50 }),
          getProductivitySummary(),
          getSubjectPerformance(),
        ]);

        const data = result.data || [];

        setSessions(data);
        setTotalPages(result.total_pages || 1);
        setChartData(buildWeeklyChart(data));
        setProductivitySummary(summary);
        setSubjectProgress(subjectPerformance);
      } catch (err) {
        console.error("Failed to fetch study sessions:", err);
        toast.error(
          "Could not load study sessions. Please try again later."
        );
      } finally {
        setIsLoading(false);
      }
    }

    fetchSessions();
  }, []);

  // Re-fetch the table whenever subject filter or page changes.
  useEffect(() => {
    if (isLoading) return;

    let cancelled = false;

    async function fetchTablePage() {
      setIsTableLoading(true);

      try {
        const result = await getSessions({
          page,
          limit: 20,
          ...(subjectFilter ? { subject: subjectFilter } : {}),
          ...(sessionTypeFilter ? { session_type: sessionTypeFilter } : {}),
        });

        if (cancelled) return;

        const data = result.data || [];

        setSessions(data);
        setTotalPages(result.total_pages || 1);
        setChartData(buildWeeklyChart(data));
      } catch (err) {
        if (cancelled) return;

        console.error("Failed to fetch study sessions:", err);
        toast.error(
          "Could not load study sessions. Please try again later."
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
  }, [page, subjectFilter, sessionTypeFilter]);

  function handleSubjectFilterChange(e) {
    setSubjectFilter(e.target.value);
    setPage(1);
  }

  function handleSessionTypeFilterChange(e) {
    setSessionTypeFilter(e.target.value);
    setPage(1);
  }

  function clearFilters() {
    setSubjectFilter("");
    setSessionTypeFilter("");
    setPage(1);
  }

  /**
   * Creates a new study session.
   *
   * linked_goal_id is passed only when the user selected a goal.
   * "No Goal" sends null.
   */
  async function addSession(formData) {
    try {
      const payload = {
        subject: formData.subject,

        study_hours:
          Number(formData.hours) +
          Number(formData.minutes || 0) / 60,

        session_type: formData.session_type,

        linked_goal_id: formData.linked_goal_id || null,

        // Optional quiz/exam scores — omitted entirely (not sent as "") when
        // left blank, since the backend expects a real Decimal/int or nothing.
        ...(formData.quiz_marks !== "" && formData.quiz_marks != null
          ? { quiz_marks: Number(formData.quiz_marks), max_quiz_marks: Number(formData.max_quiz_marks) }
          : {}),
        ...(formData.exam_marks !== "" && formData.exam_marks != null
          ? { exam_marks: Number(formData.exam_marks), max_exam_marks: Number(formData.max_exam_marks) }
          : {}),
        ...(formData.focus_score !== "" && formData.focus_score != null
          ? { focus_score: Number(formData.focus_score) }
          : {}),

        session_date: formData.date
          ? new Date(formData.date).toISOString()
          : undefined,
      };

      const newRecord = await createSession(payload);

      setSessions((prev) => {
        const updated = [newRecord, ...prev];

        setChartData(buildWeeklyChart(updated));

        return updated;
      });

      toast.success("Study session logged successfully.");
      setAddDrawerOpen(false);
    } catch (err) {
      console.error("Failed to add study session:", err);

      toast.error(
        "Failed to log study session. Please try again."
      );

      throw err;
    }
  }

  const handleUpdate = async (id, formData) => {
    try {
      const payload = {
        subject: formData.subject,

        study_hours:
          Number(formData.hours) +
          Number(formData.minutes || 0) / 60,

        session_type: formData.session_type,

        linked_goal_id: formData.linked_goal_id || null,

        // On edit, blank marks are sent as an explicit null rather than omitted.
        // The backend PATCH uses exclude_unset, so an omitted field keeps its stored
        // value — which would leave a quiz score attached to a session after the user
        // switched it away from Practice Exam and the quiz fields cleared themselves.
        ...(formData.quiz_marks !== "" && formData.quiz_marks != null
          ? { quiz_marks: Number(formData.quiz_marks), max_quiz_marks: Number(formData.max_quiz_marks) }
          : { quiz_marks: null, max_quiz_marks: null }),
        ...(formData.exam_marks !== "" && formData.exam_marks != null
          ? { exam_marks: Number(formData.exam_marks), max_exam_marks: Number(formData.max_exam_marks) }
          : { exam_marks: null, max_exam_marks: null }),
        ...(formData.focus_score !== "" && formData.focus_score != null
          ? { focus_score: Number(formData.focus_score) }
          : { focus_score: null }),

        session_date: formData.date
          ? new Date(formData.date).toISOString()
          : undefined,
      };

      const updatedRecord = await updateSession(id, payload);

      setSessions((prev) => {
        const updated = prev.map((s) =>
          s.id === id ? updatedRecord : s
        );

        setChartData(buildWeeklyChart(updated));

        return updated;
      });

      toast.success("Study session updated successfully.");
      setEditingRecord(null);
    } catch (err) {
      console.error("Failed to update session:", err);

      toast.error(
        "Failed to update study session. Please try again."
      );

      throw err;
    }
  };

  const handleDelete = (id) => {
    setConfirmDeleteId(id);
  };

  const confirmDelete = async () => {
    const id = confirmDeleteId;

    setConfirmDeleteId(null);

    try {
      await deleteSession(id);

      setSessions((prev) => {
        const updated = prev.filter((s) => s.id !== id);

        setChartData(buildWeeklyChart(updated));

        return updated;
      });

      toast.success("Study session deleted.");
    } catch (err) {
      console.error("Failed to delete session:", err);
      toast.error("Failed to delete study session.");
    }
  };

  const startEdit = (record) => {
    const dateStr = record.session_date || record.date;

    const totalHours = Number(
      record.study_hours ?? record.hours ?? 0
    );

    const hours = Math.floor(totalHours);
    const minutes = Math.round((totalHours - hours) * 60);

    setEditingRecord({
      id: record.id,

      date: dateStr ? dateStr.substring(0, 10) : "",

      subject: record.subject,

      hours,

      minutes,

      session_type:
        record.session_type || "DEEP_WORK",

      linked_goal_id:
        record.linked_goal_id || "",

      quiz_marks: record.quiz_marks ?? "",
      max_quiz_marks: record.max_quiz_marks ?? "",
      exam_marks: record.exam_marks ?? "",
      max_exam_marks: record.max_exam_marks ?? "",
      focus_score: record.focus_score ?? "",
    });
  };

  return (
    <div>

      {/* Header */}

      <div className="mb-6 flex flex-wrap items-center justify-between gap-4">

        <h2 className="text-2xl font-semibold text-slate-800 dark:text-slate-100">
          Study Dashboard
        </h2>

        <Button onClick={() => setAddDrawerOpen(true)}>
          + Add Study Session
        </Button>

      </div>

      {isLoading ? (

        <div className="flex flex-col gap-5">

          <SkeletonStatGrid count={4} />

          <SkeletonChart />

          <SkeletonTable rows={6} cols={4} />

        </div>

      ) : (

        <div className="flex flex-col gap-6">

          <StudySummary
            sessions={sessions}
            productivitySummary={productivitySummary}
          />

          <div className="rounded-2xl bg-white dark:bg-slate-800 p-6 shadow-sm">
            <StudyChart data={chartData} />
          </div>

          <SubjectProgress subjects={subjectProgress} />

          {/* Study goals — same treatment Finance gives its savings goals.
              Progress is the backend's per-goal current_value, incremented by
              sessions linked to that goal, not a count of sessions on screen.

              Fixed columns, not a flexing row: a single goal stretched to full
              width read as a layout choice rather than as "you have one goal".
              The add tile fills the first empty slot with the action someone
              looking at a short row most likely wants. */}
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {studyGoals.map((goal) => (
              <GoalProgressCard
                key={goal.goal_id}
                goal={goal}
                formatValue={(value) => Number(value).toLocaleString()}
                unitLabel={goal.unit}
              />
            ))}

            <AddGoalCard
              category="STUDY"
              label={studyGoals.length > 0 ? "Add another goal" : "Add your first study goal"}
              hint="Finish a course, hit a target score"
            />
          </div>

          <AIRecommendationPanel
            title="AI Study Recommendations"
            items={recommendations.items}
            provider={recommendations.provider}
            generatedAt={recommendations.generatedAt}
            stale={recommendations.stale}
            isLoading={recommendations.isLoading}
            isGenerating={recommendations.isGenerating}
            onGenerate={recommendations.generate}
            emptyMessage="Log a few study sessions and recommendations will appear here."
          />

          <StudyTable
            sessions={sessions}
            onEdit={startEdit}
            onDelete={handleDelete}
            isLoading={isTableLoading}
            subjectFilter={subjectFilter}
            sessionTypeFilter={sessionTypeFilter}
            onSubjectFilterChange={handleSubjectFilterChange}
            onSessionTypeFilterChange={handleSessionTypeFilterChange}
            onClearFilters={clearFilters}
            subjects={subjectProgress.map((s) => s.subject)}
          />

          <Pagination
            page={page}
            totalPages={totalPages}
            onPageChange={setPage}
            disabled={isTableLoading}
          />

        </div>

      )}

      {/* ADD STUDY SESSION */}

      <Drawer
        open={addDrawerOpen}
        onClose={() => setAddDrawerOpen(false)}
        title="Add Study Session"
      >

        <StudyForm
          addSession={addSession}
          goals={studyGoals}
        />

      </Drawer>

      {/* EDIT STUDY SESSION */}

      <Modal
        open={!!editingRecord}
        onClose={() => setEditingRecord(null)}
        title="Edit Study Session"
        maxWidth="max-w-xl"
      >

        <StudyForm
          initialData={editingRecord}
          onUpdate={handleUpdate}
          goals={studyGoals}
          onCancel={() => setEditingRecord(null)}
        />

      </Modal>

      {/* DELETE CONFIRMATION */}

      <ConfirmDialog
        open={confirmDeleteId !== null}
        title="Delete Study Session"
        message="Are you sure you want to delete this session? This action cannot be undone."
        confirmLabel="Delete"
        danger
        onConfirm={confirmDelete}
        onCancel={() => setConfirmDeleteId(null)}
      />

    </div>
  );
}

export default Study;