import { useState } from "react";
import { toast } from "react-toastify";
import { Input, Select } from "./ui/Field";
import Button from "./ui/Button";

const SESSION_TYPES = [
  { value: "DEEP_WORK", label: "Deep Work" },
  { value: "REVIEW", label: "Review" },
  { value: "LECTURE", label: "Lecture" },
  { value: "PRACTICE_EXAM", label: "Practice Exam" },
  { value: "ASSIGNMENT", label: "Assignment" },
  { value: "RESEARCH", label: "Research" },
];

const PRACTICE_EXAM = "PRACTICE_EXAM";

/* Broad disciplines rather than course codes — the point is that the same subject
 * spells itself the same way every time, since subject strings are what the
 * per-subject averages group on. "Maths" and "Mathematics" logged on different days
 * become two subjects with half the history each. Anything not covered here goes in
 * through Other, which keeps the field open without making free text the default. */
const SUBJECTS = [
  "Biology",
  "Business & Finance",
  "Chemistry",
  "Computer Science",
  "Economics",
  "Engineering",
  "English & Literature",
  "Geography",
  "History",
  "Languages",
  "Law",
  "Mathematics",
  "Medicine & Health",
  "Philosophy",
  "Physics",
  "Psychology",
];

const OTHER_SUBJECT = "__other__";

const DEFAULT_FORM = {
  date: "",
  subject: "",
  hours: "",
  minutes: "",
  session_type: "",
  linked_goal_id: "",
  quiz_marks: "",
  max_quiz_marks: "",
  exam_marks: "",
  max_exam_marks: "",
  focus_score: "",
};

function StudyForm({
  addSession,
  goals = [],
  initialData = null,
  onUpdate = null,
  onCancel = null,
}) {
  const [formData, setFormData] = useState(
    initialData
      ? {
          ...initialData,
          linked_goal_id: initialData.linked_goal_id || "",
        }
      : DEFAULT_FORM
  );

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [fieldErrors, setFieldErrors] = useState({});

  /* Whether the subject is being typed rather than picked. Held as state instead of
   * derived from the value, because picking Other leaves the subject empty until the
   * user types — a derived check would read that as "not custom" and snap the field
   * back to the dropdown mid-entry. An existing session whose subject predates this
   * list (or came from the seed data) opens in typing mode with its value intact. */
  const [isCustomSubject, setIsCustomSubject] = useState(
    () => !!initialData?.subject && !SUBJECTS.includes(initialData.subject)
  );

  const handleSubjectSelect = (e) => {
    const { value } = e.target;
    const custom = value === OTHER_SUBJECT;
    setIsCustomSubject(custom);
    setFormData((prev) => ({ ...prev, subject: custom ? "" : value }));
    setFieldErrors((prev) => ({ ...prev, subject: undefined }));
  };

  /* Marks only mean something on a practice exam — it is the one session type you
   * come away from with a score — so they stay out of the way on every other type.
   * They also stay visible on a session that already has them recorded regardless
   * of its type: otherwise editing an older record would hide a score that is really
   * there, and the user would have no way to see or correct it. */
  const hasValue = (v) => v !== "" && v != null;
  const showMarks =
    formData.session_type === PRACTICE_EXAM ||
    hasValue(formData.quiz_marks) ||
    hasValue(formData.max_quiz_marks) ||
    hasValue(formData.exam_marks) ||
    hasValue(formData.max_exam_marks);

  const handleChange = (e) => {
    const { name, value } = e.target;
    const next = { ...formData, [name]: value };

    // Switching to a type that isn't a practice exam clears the mark fields rather
    // than just hiding them — a hidden-but-populated field would still be submitted,
    // attaching a score to a session that never had one.
    const clearsMarks = name === "session_type" && value !== PRACTICE_EXAM;
    if (clearsMarks) {
      next.quiz_marks = "";
      next.max_quiz_marks = "";
      next.exam_marks = "";
      next.max_exam_marks = "";
    }

    setFormData(next);

    if (fieldErrors[name] || clearsMarks) {
      setFieldErrors((prev) => ({
        ...prev,
        [name]: undefined,
        ...(clearsMarks
          ? {
              quiz_marks: undefined,
              max_quiz_marks: undefined,
              exam_marks: undefined,
              max_exam_marks: undefined,
            }
          : {}),
      }));
    }
  };

  const submitHandler = async (e) => {
    e.preventDefault();

    const errors = {};
    if (!formData.date) errors.date = "Date is required.";
    const subject = String(formData.subject ?? "").trim();
    if (!subject) errors.subject = "Subject is required.";

    // Validated against the COMBINED duration (hours + minutes), matching what
    // Study.jsx actually sends as study_hours — checking `hours` alone rejected
    // legitimate short sessions like "0 hours, 30 minutes" even though 0.5h is
    // well within the backend's accepted range (0.1–24).
    const totalHours = Number(formData.hours || 0) + Number(formData.minutes || 0) / 60;
    if (totalHours <= 0 || totalHours > 24) {
      errors.hours = "Duration must be between 6 minutes (0.1h) and 24 hours.";
    }

    if (!formData.session_type) errors.session_type = "Select a session type.";

    if (showMarks && hasValue(formData.quiz_marks) && formData.max_quiz_marks === "") {
      errors.max_quiz_marks = "Enter the max quiz marks too, so the percentage can be computed.";
    }
    if (showMarks && hasValue(formData.exam_marks) && formData.max_exam_marks === "") {
      errors.max_exam_marks = "Enter the max exam marks too, so the percentage can be computed.";
    }

    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      toast.error("Please fix the highlighted fields.");
      return;
    }

    setIsSubmitting(true);

    // Trimmed on the way out so " Physics" and "Physics" don't become two subjects.
    const submission = { ...formData, subject };

    try {
      if (initialData && onUpdate) {
        await onUpdate(initialData.id, submission);
      } else {
        await addSession(submission);
        setFormData(DEFAULT_FORM);
        setIsCustomSubject(false);
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <form onSubmit={submitHandler}>
      <div className="grid grid-cols-1 gap-4 @sm:grid-cols-2">

        <Input
          type="date"
          name="date"
          value={formData.date}
          onChange={handleChange}
          error={fieldErrors.date}
          required
        />

        <Select
          name="subject_choice"
          value={isCustomSubject ? OTHER_SUBJECT : formData.subject}
          onChange={handleSubjectSelect}
          error={isCustomSubject ? undefined : fieldErrors.subject}
          aria-label="Subject"
          required
        >
          <option value="" disabled>
            Select Subject
          </option>

          {SUBJECTS.map((subjectName) => (
            <option key={subjectName} value={subjectName}>
              {subjectName}
            </option>
          ))}

          <option value={OTHER_SUBJECT}>Other…</option>
        </Select>

        {isCustomSubject && (
          <Input
            type="text"
            name="subject"
            placeholder="Subject name"
            maxLength={100}
            value={formData.subject}
            onChange={handleChange}
            error={fieldErrors.subject}
            aria-label="Custom subject name"
            required
          />
        )}

        <Input
          type="number"
          name="hours"
          placeholder="Hours"
          min="0"
          max="24"
          step="1"
          value={formData.hours}
          onChange={handleChange}
          error={fieldErrors.hours}
        />

        <Input
          type="number"
          name="minutes"
          placeholder="Minutes (0–59)"
          min="0"
          max="59"
          step="1"
          value={formData.minutes}
          onChange={handleChange}
        />

        <Select
          name="session_type"
          value={formData.session_type}
          onChange={handleChange}
          error={fieldErrors.session_type}
          required
        >
          <option value="" disabled>
            Select Type
          </option>

          {SESSION_TYPES.map((t) => (
            <option key={t.value} value={t.value}>
              {t.label}
            </option>
          ))}
        </Select>

        <Select
          name="linked_goal_id"
          value={formData.linked_goal_id}
          onChange={handleChange}
        >
          <option value="">No Goal</option>

          {goals.map((goal) => (
            <option key={goal.goal_id} value={goal.goal_id}>
              {goal.title}
            </option>
          ))}
        </Select>

      </div>

      <p className="mb-3 mt-5 text-xs font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">
        {showMarks ? "Scores (optional)" : "Focus (optional)"}
      </p>

      <div className="grid grid-cols-1 gap-4 @sm:grid-cols-2">

        {showMarks && (
          <>
            <Input
              type="number"
              name="quiz_marks"
              placeholder="Quiz marks"
              min="0"
              step="0.01"
              value={formData.quiz_marks}
              onChange={handleChange}
            />

            <Input
              type="number"
              name="max_quiz_marks"
              placeholder="Out of (max quiz marks)"
              min="0"
              step="0.01"
              value={formData.max_quiz_marks}
              onChange={handleChange}
              error={fieldErrors.max_quiz_marks}
            />

            <Input
              type="number"
              name="exam_marks"
              placeholder="Exam marks"
              min="0"
              step="0.01"
              value={formData.exam_marks}
              onChange={handleChange}
            />

            <Input
              type="number"
              name="max_exam_marks"
              placeholder="Out of (max exam marks)"
              min="0"
              step="0.01"
              value={formData.max_exam_marks}
              onChange={handleChange}
              error={fieldErrors.max_exam_marks}
            />
          </>
        )}

        <Input
          type="number"
          name="focus_score"
          placeholder="Focus score (0-100)"
          min="0"
          max="100"
          step="1"
          value={formData.focus_score}
          onChange={handleChange}
        />

      </div>

      <div className="mt-5 flex gap-2.5">
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting
            ? "Saving..."
            : initialData
            ? "Update Session"
            : "Add Session"}
        </Button>

        {initialData && onCancel && (
          <Button
            type="button"
            variant="secondary"
            onClick={onCancel}
            disabled={isSubmitting}
          >
            Cancel
          </Button>
        )}
      </div>
    </form>
  );
}

export default StudyForm;