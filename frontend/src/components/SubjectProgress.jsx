import { memo } from "react";
import ProgressList from "./ui/ProgressList";

const DAY_MS = 86_400_000;

/** Days since a subject was last studied, or null when it has never been dated. */
function daysSince(dateStr) {
  if (!dateStr) return null;
  const then = new Date(dateStr);
  if (Number.isNaN(then.getTime())) return null;
  return Math.floor((Date.now() - then.getTime()) / DAY_MS);
}

/** A subject untouched for this long is worth flagging. Two weeks is long enough
 *  to sit out a normal gap between sessions, short enough to catch a subject that
 *  has quietly been dropped. */
const STALE_DAYS = 14;

function StaleChip({ days }) {
  if (days == null || days < STALE_DAYS) return null;
  return (
    <span className="shrink-0 rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-medium text-amber-700 dark:bg-amber-500/15 dark:text-amber-400">
      {days}d untouched
    </span>
  );
}

/**
 * Where study time actually goes, by subject.
 *
 * The bar is each subject's share of total study hours — a real proportion of a
 * real total. It replaces an earlier "Subject Progress" panel whose bar was an
 * average exam score picked from a fallback chain, which meant the bars weren't
 * progress (they never filled as you studied) and weren't comparable to each
 * other (one subject's bar could be an exam average, the next one's a quiz
 * average, with nothing on screen saying which).
 *
 * Scores still appear, but as a trailing figure rather than the bar, so a
 * subject with no marks recorded reads as "no scores yet" instead of silently
 * borrowing a different metric.
 */
function SubjectProgress({ subjects = [] }) {
  const totalHours = subjects.reduce((sum, s) => sum + Number(s.total_study_hours || 0), 0);

  const items = [...subjects]
    .sort((a, b) => Number(b.total_study_hours || 0) - Number(a.total_study_hours || 0))
    .map((s) => {
      const hours = Number(s.total_study_hours || 0);
      const sessions = Number(s.session_count || 0);

      // Exam marks are the better signal where they exist; quiz marks stand in
      // otherwise. Checked against null rather than truthiness, because the backend
      // now reports an unrecorded average as null — a genuine 0% is a real score
      // and must not read as "no scores yet".
      const score =
        s.average_exam_pct != null
          ? s.average_exam_pct
          : s.average_quiz_pct != null
          ? s.average_quiz_pct
          : null;

      const stale = daysSince(s.last_session_date);

      return {
        key: s.subject,
        label: s.subject,
        value: totalHours > 0 ? (hours / totalHours) * 100 : 0,
        valueLabel: `${hours.toFixed(1)} hrs`,
        chip: <StaleChip days={stale} />,
        meta: [
          `${Math.round((totalHours > 0 ? hours / totalHours : 0) * 100)}% of your time`,
          `${sessions} session${sessions === 1 ? "" : "s"}`,
          score != null ? `${Math.round(score)}% avg score` : "no scores yet",
        ].join(" · "),
      };
    });

  return (
    <ProgressList
      title="Where your time goes"
      items={items}
      emptyMessage="No subject data yet — log a study session to see where your time goes."
      footnote={
        items.length > 0
          ? `${totalHours.toFixed(1)} hours logged across ${items.length} subject${items.length === 1 ? "" : "s"}.`
          : null
      }
    />
  );
}

export default memo(SubjectProgress);
