import { useState } from "react";
import { toast } from "react-toastify";
import { Input, Select } from "./ui/Field";
import Button from "./ui/Button";

/**
 * TransactionForm — creates or updates a financial record.
 * Maps to POST/PATCH /api/v1/finance/transactions.
 */
function TransactionForm({
  addTransaction,
  initialData = null,
  onUpdate = null,
  onCancel = null,
  goals = [],
}) {
  const [formData, setFormData] = useState(
    initialData || {
      date: "",
      type: "",
      category: "",
      amount: "",
      description: "",
      linked_goal_id: "",
      is_recurring: false,
      recurring_frequency: "",
    }
  );

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [fieldErrors, setFieldErrors] = useState({});

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;
    setFormData({
      ...formData,
      [name]: type === "checkbox" ? checked : value,
    });
    if (fieldErrors[name]) {
      setFieldErrors((prev) => ({ ...prev, [name]: undefined }));
    }
  };

  const submitHandler = async (e) => {
    e.preventDefault();

    const errors = {};
    if (!formData.date) errors.date = "Date is required.";
    if (!formData.amount) errors.amount = "Amount is required.";
    else if (Number(formData.amount) <= 0) errors.amount = "Amount must be greater than 0.";
    if (formData.is_recurring && !formData.recurring_frequency) {
      errors.recurring_frequency = "Select a recurring frequency.";
    }

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
        await addTransaction(formData);

        setFormData({
          date: "",
          type: "",
          category: "",
          amount: "",
          description: "",
          linked_goal_id: "",
          is_recurring: false,
          recurring_frequency: "",
        });
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
          name="type"
          value={formData.type}
          onChange={handleChange}
          required
        >
          <option value="" disabled>
            Select Type
          </option>
          <option value="INCOME">Income</option>
          <option value="EXPENSE">Expense</option>
          <option value="SAVINGS_DEPOSIT">Savings Deposit</option>
          <option value="INVESTMENT">Investment</option>
        </Select>

        <Select
          name="category"
          value={formData.category}
          onChange={handleChange}
          required
        >
          <option value="" disabled>
            Select Category
          </option>
          <option value="SALARY">Salary</option>
          <option value="FOOD">Food</option>
          <option value="HOUSING">Housing</option>
          <option value="UTILITIES">Utilities</option>
          <option value="ENTERTAINMENT">Entertainment</option>
          <option value="HEALTH">Health</option>
          <option value="EDUCATION">Education</option>
          <option value="INVESTMENT">Investment</option>
          <option value="TRANSPORT">Transport</option>
          <option value="SAVINGS">Savings</option>
          <option value="OTHER">Other</option>
        </Select>

        <Input
          type="number"
          name="amount"
          placeholder="Amount"
          min="1"
          step="0.01"
          value={formData.amount}
          onChange={handleChange}
          error={fieldErrors.amount}
          required
        />

        <Select
          name="linked_goal_id"
          value={formData.linked_goal_id || ""}
          onChange={handleChange}
        >
          <option value="">No Goal</option>

          {goals.map((goal) => (
            <option key={goal.goal_id} value={goal.goal_id}>
              {goal.title}
            </option>
          ))}
        </Select>

        <Input
          type="text"
          name="description"
          placeholder="Description (optional)"
          value={formData.description}
          onChange={handleChange}
        />

      </div>

      <div className="mt-4 flex flex-wrap items-center gap-4">
        <label className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300">
          <input
            type="checkbox"
            name="is_recurring"
            checked={!!formData.is_recurring}
            onChange={handleChange}
            className="h-4 w-4 rounded border-slate-300 text-indigo-600 dark:text-indigo-400 focus:ring-indigo-500"
          />
          Recurring transaction
        </label>

        {formData.is_recurring && (
          <Select
            name="recurring_frequency"
            value={formData.recurring_frequency || ""}
            onChange={handleChange}
            error={fieldErrors.recurring_frequency}
            required
          >
            <option value="" disabled>
              Select Frequency
            </option>
            <option value="DAILY">Daily</option>
            <option value="WEEKLY">Weekly</option>
            <option value="BIWEEKLY">Biweekly</option>
            <option value="MONTHLY">Monthly</option>
            <option value="QUARTERLY">Quarterly</option>
            <option value="ANNUALLY">Annually</option>
          </Select>
        )}
      </div>

      <div className="mt-5 flex gap-2.5">
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting
            ? "Saving..."
            : initialData
            ? "Update Transaction"
            : "Add Transaction"}
        </Button>

        {initialData && onCancel && (
          <Button
            type="button"
            variant="secondary"
            onClick={onCancel}
          >
            Cancel
          </Button>
        )}
      </div>
    </form>
  );
}

export default TransactionForm;