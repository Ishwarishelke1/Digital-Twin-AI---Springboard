import { StatTile } from "./ui/StatTile";
import { getCurrencySymbol } from "../utils/currency";

/**
 * Bug fix: this component received a `transactions` prop but never read it —
 * it rendered 4 hardcoded numbers regardless of the user's real data. Now
 * computed from the actual transaction list. "Budget Used" is retired (no
 * budget-setting feature exists anywhere in the backend to back it).
 */
function FinanceSummary({ transactions, currency = "USD" }) {
  const income = transactions
    .filter((t) => String(t.type).toUpperCase() === "INCOME")
    .reduce((sum, t) => sum + Number(t.amount), 0);

  const expense = transactions
    .filter((t) => String(t.type).toUpperCase() === "EXPENSE")
    .reduce((sum, t) => sum + Number(t.amount), 0);

  const savings = income - expense;

  return (
    <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
      <StatTile accent="emerald" label="Total Income" value={income} prefix={getCurrencySymbol(currency)} />
      <StatTile accent="red" label="Total Expense" value={expense} prefix={getCurrencySymbol(currency)} />
      <StatTile accent="indigo" label="Total Savings" value={savings} prefix={getCurrencySymbol(currency)} />
    </div>
  );
}

export default FinanceSummary;
