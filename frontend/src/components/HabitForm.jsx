import { useState } from "react";
import { toast } from "react-toastify";
import { Input, Select } from "./ui/Field";
import Button from "./ui/Button";

const DEFAULT_FORM = {
  date: "",
  water: "",
  sleep: "",
  exercise: "",
  screenTime: "",
  mood: "Happy",
  linked_goal_id: "",
};

function HabitForm({
  addHabit,
  goals = [],
  initialData = null,
  onUpdate = null,
  onCancel = null,
}) {
  const [formData, setFormData] = useState(
    initialData
      ? { ...DEFAULT_FORM, ...initialData, linked_goal_id: initialData.linked_goal_id || "" }
      : DEFAULT_FORM
  );

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [fieldErrors, setFieldErrors] = useState({});

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData({
      ...formData,
      [name]: value,
    });
    if (fieldErrors[name]) {
      setFieldErrors((prev) => ({ ...prev, [name]: undefined }));
    }
  };

  const submitHandler = async (e) => {
    e.preventDefault();

    const errors = {};
    if (!formData.date) errors.date = "Date is required.";
    if (!formData.water) errors.water = "Water intake is required.";
    if (!formData.sleep) errors.sleep = "Sleep hours are required.";
    if (!formData.exercise) errors.exercise = "Exercise minutes are required.";

    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      toast.error("Please fix the highlighted fields.");
      return;
    }

    setIsSubmitting(true);

    try {
      if (initialData && onUpdate) {
        await onUpdate(initialData.id, formData);
      } else {
        await addHabit(formData);
        setFormData(DEFAULT_FORM);
      }
    } catch (err) {
      console.error("HabitForm submission error:", err);
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
          disabled={!!initialData}
          title={initialData ? "The day of a log can't be changed — delete and re-log instead." : undefined}
        />

        <Input
          type="number"
          step="0.1"
          min="0"
          max="20"
          name="water"
          placeholder="Water (L)"
          value={formData.water}
          onChange={handleChange}
          error={fieldErrors.water}
        />

        <Input
          type="number"
          step="0.5"
          min="0"
          max="24"
          name="sleep"
          placeholder="Sleep (hrs)"
          value={formData.sleep}
          onChange={handleChange}
          error={fieldErrors.sleep}
        />

        <Input
          type="number"
          min="0"
          max="1440"
          name="exercise"
          placeholder="Exercise (min)"
          value={formData.exercise}
          onChange={handleChange}
          error={fieldErrors.exercise}
        />

        <Input
          type="number"
          step="0.5"
          min="0"
          max="24"
          name="screenTime"
          placeholder="Screen Time (hrs)"
          value={formData.screenTime}
          onChange={handleChange}
        />

        <Select
          name="mood"
          value={formData.mood}
          onChange={handleChange}
        >
          <option value="Excellent">Excellent</option>
          <option value="Happy">Happy</option>
          <option value="Normal">Normal</option>
          <option value="Sad">Sad</option>
        </Select>

        {/* Habit Goal */}
        <Select
          name="linked_goal_id"
          value={formData.linked_goal_id}
          onChange={handleChange}
        >
          <option value="">No Goal</option>

          {goals.map((goal) => (
            <option
              key={goal.goal_id}
              value={goal.goal_id}
            >
              {goal.title}
            </option>
          ))}
        </Select>

      </div>

      <div className="mt-5 flex gap-2.5">
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting ? "Saving..." : initialData ? "Update Habit" : "Save Habit"}
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

export default HabitForm;