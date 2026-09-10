import { useState } from "react";
import { toast } from "react-toastify";
import { Input, Select } from "./ui/Field";
import Button from "./ui/Button";
import { getApiErrorMessage } from "../utils/apiError";

/**
 * GoalForm — creates a new active goal, or edits an existing one when
 * `initialData`/`onUpdate` are supplied (same convention as StudyForm/TransactionForm).
 * Maps to POST /api/v1/users/me/goals (create) or PATCH /api/v1/users/me/goals/{id} (edit).
 */
function GoalForm({
  onSave, initialData = null, onUpdate = null, onCancel = null,
  defaultCategory = "FINANCE",
}) {

  const [formData, setFormData] = useState(
    initialData || {
      title: "",
      // Preset when the form was opened from a domain page's "Add a goal" tile,
      // so someone coming from Habits does not land on a finance goal. Kept out
      // of `initialData`, which is what puts the form into edit mode.
      category: defaultCategory,
      target_value: "",
      unit: "",
      target_date: "",
    }
  );

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [fieldErrors, setFieldErrors] = useState({});

  function handleChange(e) {
    const { name, value } = e.target;
    setFormData({
      ...formData,
      [name]: value,
    });
    if (fieldErrors[name]) {
      setFieldErrors((prev) => ({ ...prev, [name]: undefined }));
    }
  }

  async function submit(e) {
    e.preventDefault();

    const errors = {};
    if (!formData.title) errors.title = "Title is required.";
    if (!formData.target_value) errors.target_value = "Target value is required.";
    else if (Number(formData.target_value) <= 0) errors.target_value = "Must be greater than 0.";
    if (!formData.unit) errors.unit = "Unit is required.";
    if (!formData.target_date) errors.target_date = "Target date is required.";

    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      toast.error("Please fix the highlighted fields.");
      return;
    }

    setIsSubmitting(true);
    try {
      if (initialData && onUpdate) {
        await onUpdate(initialData.goal_id, {
          title: formData.title,
          category: formData.category,
          target_value: Number(formData.target_value),
          current_value: formData.current_value !== "" && formData.current_value != null
            ? Number(formData.current_value)
            : undefined,
          unit: formData.unit,
          target_date: new Date(formData.target_date).toISOString(),
        });
      } else {
        await onSave({
          title: formData.title,
          category: formData.category,
          target_value: Number(formData.target_value),
          unit: formData.unit,
          target_date: new Date(formData.target_date).toISOString(),
        });
      }
      // Success toast is shown by Profile.jsx to avoid duplicates
    } catch (err) {
      toast.error(getApiErrorMessage(
        err, initialData ? "Failed to update goal. Please try again." : "Failed to add goal. Please try again."
      ));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <form onSubmit={submit}>
      {/* Same shape as Finance's TransactionForm: one dense row of fields on a
          wide container, two up on a narrow one, collapsing to a stack on a
          phone. Container queries, not viewport breakpoints, because this form
          renders inline on the Goals page and inside a Modal when editing — the
          space it has is its container's, not the window's. */}
      <div className="grid grid-cols-1 gap-4 @sm:grid-cols-2 @lg:grid-cols-5">

        <Input
          type="text"
          name="title"
          placeholder="Goal Title"
          value={formData.title}
          onChange={handleChange}
          error={fieldErrors.title}
          required
        />

        <Select
          name="category"
          value={formData.category}
          onChange={handleChange}
          required
        >
          <option value="" disabled>
            Select Category
          </option>
          <option value="FINANCE">Finance</option>
          <option value="STUDY">Study</option>
          <option value="HABIT">Habit</option>
          <option value="FITNESS">Fitness</option>
          <option value="CAREER">Career</option>
        </Select>

        <Input
          type="number"
          name="target_value"
          placeholder="Target Value"
          min="0.01"
          step="0.01"
          value={formData.target_value}
          onChange={handleChange}
          error={fieldErrors.target_value}
          required
        />

        <Input
          type="text"
          name="unit"
          placeholder="Unit (e.g. USD, hours)"
          value={formData.unit}
          onChange={handleChange}
          error={fieldErrors.unit}
          required
        />

        <Input
          type="date"
          name="target_date"
          value={formData.target_date}
          onChange={handleChange}
          error={fieldErrors.target_date}
          required
        />

        {/* Only offered when editing — on a new goal there is no progress to
            correct, and a create payload has no current_value field at all. */}
        {initialData && (
          <Input
            type="number"
            name="current_value"
            placeholder="Current Value"
            min="0"
            step="0.01"
            value={formData.current_value ?? ""}
            onChange={handleChange}
          />
        )}

      </div>

      <div className="mt-4 flex flex-wrap gap-3">

        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting ? "Saving..." : initialData ? "Update Goal" : "Add Goal"}
        </Button>

        {onCancel && (
          <Button type="button" variant="secondary" onClick={onCancel} disabled={isSubmitting}>
            Cancel
          </Button>
        )}

      </div>

    </form>
  );
}

export default GoalForm;
