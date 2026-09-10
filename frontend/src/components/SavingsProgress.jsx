import GoalProgressCard from "./GoalProgressCard";
import { formatCurrency } from "../utils/currency";

/** Finance's goal card — GoalProgressCard with money formatting. */
function SavingsProgress({ goal, currency = "USD" }) {
  return (
    <GoalProgressCard
      goal={goal}
      formatValue={(value) => formatCurrency(value, currency)}
      emptyTitle="Savings Goal"
      emptyMessage="You haven't set a finance goal yet — add one from the Goals page to track progress here."
    />
  );
}

export default SavingsProgress;
