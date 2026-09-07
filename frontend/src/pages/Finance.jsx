import { useState, useEffect } from "react";
import { toast } from "react-toastify";

import { useAuth } from "../context/useAuth";

import FinanceSummary from "../components/FinanceSummary";
import TransactionForm from "../components/TransactionForm";
import TransactionTable from "../components/TransactionTable";
import ExpenseChart from "../components/ExpenseChart";
import CategoryChart from "../components/CategoryChart";
import SavingsProgress from "../components/SavingsProgress";
import ConfirmDialog from "../components/ConfirmDialog";
import Pagination from "../components/Pagination";
import IncomeProjectionCard from "../components/IncomeProjectionCard";
import Button from "../components/ui/Button";
import Modal from "../components/ui/Modal";
import Drawer from "../components/ui/Drawer";
import {
  SkeletonStatGrid,
  SkeletonChart,
  SkeletonTable,
} from "../components/ui/Skeleton";

import {
  getTransactions,
  createTransaction,
  updateTransaction,
  deleteTransaction,
  getCategoryBreakdown,
} from "../services/financeService";
import {
  getExpenseProjection,
  getIncomeProjection,
} from "../services/forecastService";

const TRANSACTION_TYPES = [
  "INCOME",
  "EXPENSE",
  "SAVINGS_DEPOSIT",
  "INVESTMENT",
];

const FINANCIAL_CATEGORIES = [
  "HOUSING",
  "FOOD",
  "UTILITIES",
  "SALARY",
  "ENTERTAINMENT",
  "HEALTH",
  "EDUCATION",
  "INVESTMENT",
  "TRANSPORT",
  "SAVINGS",
  "OTHER",
];

const MONTH_NAMES = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];

function monthLabel(year, month) {
  return `${MONTH_NAMES[month - 1]} ${String(year).slice(-2)}`;
}

/**
 * Builds ExpenseChart's [{ month, expense }] series: last 6 months of actual
 * expenses followed by projected future months.
 */
function buildExpenseChartData(transactions, forecast) {
  const historicalMap = {};

  for (const t of transactions) {
    if (String(t.type).toUpperCase() !== "EXPENSE") continue;

    const d = new Date(t.transaction_date || t.date);

    const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(
      2,
      "0"
    )}`;

    historicalMap[key] =
      (historicalMap[key] || 0) + Number(t.amount || 0);
  }

  const historical = Object.entries(historicalMap)
    .sort(([a], [b]) => a.localeCompare(b))
    .slice(-6)
    .map(([key, expense]) => {
      const [year, month] = key.split("-").map(Number);

      return {
        month: monthLabel(year, month),
        expense: Math.round(expense),
      };
    });

  // Projections go in their own key. Pushing them into `expense` alongside the
  // actuals — as this did — made the chart draw one unbroken solid line across
  // both, so a viewer could not tell where measurement stopped and estimation
  // began. The last historical month carries both keys, which is what joins the
  // two lines; without it the projection starts detached.
  const projected = (forecast?.projections || []).map((p) => ({
    month: monthLabel(p.year, p.month),
    projected: Math.round(Number(p.projected_amount)),
  }));

  if (historical.length && projected.length) {
    const last = historical[historical.length - 1];
    historical[historical.length - 1] = { ...last, projected: last.expense };
  }

  return [...historical, ...projected];
}

function Finance() {
  const { user } = useAuth();

  /*
   * Get every FINANCE goal created by the user.
   *
   * Example:
   * Emergency Fund
   * Laptop Savings
   * New Phone
   *
   * These are NOT hardcoded. Whatever finance goals the user creates
   * will automatically appear in the TransactionForm dropdown.
   */
  const financeGoals =
    user?.active_goals?.filter(
      (goal) => goal.category === "FINANCE"
    ) ?? [];

  const currency = user?.preferences?.currency ?? "USD";

  // Dashboard transaction data
  const [transactions, setTransactions] = useState([]);
  const [expenseChartData, setExpenseChartData] = useState([]);
  const [categoryChartData, setCategoryChartData] = useState([]);
  const [incomeProjection, setIncomeProjection] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [editingRecord, setEditingRecord] = useState(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState(null);
  const [addDrawerOpen, setAddDrawerOpen] = useState(false);

  // Transaction table state
  const [tableTransactions, setTableTransactions] = useState([]);
  const [typeFilter, setTypeFilter] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [isTableLoading, setIsTableLoading] = useState(false);

  useEffect(() => {
    async function fetchDashboardData() {
      try {
        const [
          result,
          forecast,
          categoryBreakdown,
          income,
        ] = await Promise.all([
          getTransactions({ limit: 50 }),
          getExpenseProjection(3),
          // 6 months, matching the window every other chart on this page uses
          // (ExpenseChart's 6-month actuals, Dashboard's getCashflow(6)) — a
          // 1-month window meant categories logged outside the last 30 days
          // silently disappeared from this chart even though they're still
          // "recent" by every other chart's definition.
          getCategoryBreakdown(6),
          getIncomeProjection(3),
        ]);

        const txns = result.data || [];

        setTransactions(txns);
        setTableTransactions(txns);
        setTotalPages(result.total_pages || 1);

        setExpenseChartData(
          buildExpenseChartData(txns, forecast)
        );

        setCategoryChartData(
          categoryBreakdown.map((c) => ({
            name: c.category,
            value: Number(c.total_amount),
          }))
        );

        setIncomeProjection(income);
      } catch (err) {
        console.error("Failed to fetch transactions:", err);
        toast.error(
          "Could not load transactions. Please try again later."
        );
      } finally {
        setIsLoading(false);
      }
    }

    fetchDashboardData();
  }, []);

  // Re-fetch transaction table when filters/page change
  useEffect(() => {
    if (isLoading) return;

    let cancelled = false;

    async function fetchTablePage() {
      setIsTableLoading(true);

      try {
        const result = await getTransactions({
          page,
          limit: 20,
          ...(typeFilter ? { type: typeFilter } : {}),
          ...(categoryFilter
            ? { category: categoryFilter }
            : {}),
        });

        if (cancelled) return;

        setTableTransactions(result.data || []);
        setTotalPages(result.total_pages || 1);
      } catch (err) {
        if (cancelled) return;

        console.error("Failed to fetch transactions:", err);

        toast.error(
          "Could not load transactions. Please try again later."
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
  }, [page, typeFilter, categoryFilter]);

  function handleTypeFilterChange(e) {
    setTypeFilter(e.target.value);
    setPage(1);
  }

  function handleCategoryFilterChange(e) {
    setCategoryFilter(e.target.value);
    setPage(1);
  }

  function clearFilters() {
    setTypeFilter("");
    setCategoryFilter("");
    setPage(1);
  }

  /**
   * Creates a new transaction.
   *
   * IMPORTANT:
   * linked_goal_id connects the transaction to the goal selected
   * in TransactionForm.
   */
  const addTransaction = async (formData) => {
    try {
      const payload = {
        type: formData.type,
        amount: Number(formData.amount),
        category: formData.category,
        description: formData.description || undefined,

        // Connect transaction to selected finance goal
        linked_goal_id: formData.linked_goal_id || undefined,

        is_recurring: !!formData.is_recurring,
        recurring_frequency: formData.is_recurring ? formData.recurring_frequency : undefined,

        transaction_date: formData.date
          ? new Date(formData.date).toISOString()
          : undefined,
      };

      const newRecord = await createTransaction(payload);

      setTransactions((prev) => [newRecord, ...prev]);
      setTableTransactions((prev) => [newRecord, ...prev]);

      toast.success("Transaction added successfully.");

      setAddDrawerOpen(false);
    } catch (err) {
      console.error("Failed to add transaction:", err);

      toast.error(
        "Failed to add transaction. Please try again."
      );

      throw err;
    }
  };

  /**
   * Updates an existing transaction.
   */
  const handleUpdate = async (id, formData) => {
    try {
      const payload = {
        type: formData.type,
        amount: Number(formData.amount),
        category: formData.category,
        description: formData.description || undefined,

        // Keep the goal connection when editing
        linked_goal_id: formData.linked_goal_id || undefined,

        is_recurring: !!formData.is_recurring,
        recurring_frequency: formData.is_recurring ? formData.recurring_frequency : undefined,

        transaction_date: formData.date
          ? new Date(formData.date).toISOString()
          : undefined,
      };

      const updatedRecord = await updateTransaction(
        id,
        payload
      );

      setTransactions((prev) =>
        prev.map((t) =>
          t.id === id ? updatedRecord : t
        )
      );

      setTableTransactions((prev) =>
        prev.map((t) =>
          t.id === id ? updatedRecord : t
        )
      );

      toast.success(
        "Transaction updated successfully."
      );

      setEditingRecord(null);
    } catch (err) {
      console.error(
        "Failed to update transaction:",
        err
      );

      toast.error(
        "Failed to update transaction. Please try again."
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
      await deleteTransaction(id);

      setTransactions((prev) =>
        prev.filter((t) => t.id !== id)
      );

      setTableTransactions((prev) =>
        prev.filter((t) => t.id !== id)
      );

      toast.success("Transaction deleted.");
    } catch (err) {
      console.error(
        "Failed to delete transaction:",
        err
      );

      toast.error(
        "Failed to delete transaction."
      );
    }
  };

  const startEdit = (record) => {
    const dateStr =
      record.transaction_date || record.date;

    const initialData = {
      id: record.id,

      date: dateStr
        ? dateStr.substring(0, 10)
        : "",

      type: (
        record.type || "EXPENSE"
      ).toUpperCase(),

      category: (
        record.category || "OTHER"
      ).toUpperCase(),

      amount: record.amount,

      description: record.description || "",

      // Preserve the linked goal when editing
      linked_goal_id:
        record.linked_goal_id || "",

      is_recurring: !!record.is_recurring,
      recurring_frequency: record.recurring_frequency || "",
    };

    setEditingRecord(initialData);
  };

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <h2 className="text-2xl font-semibold text-slate-800 dark:text-slate-100">
          Finance Dashboard
        </h2>

        <Button
          onClick={() => setAddDrawerOpen(true)}
        >
          + Add Transaction
        </Button>
      </div>

      {isLoading ? (
        <div className="flex flex-col gap-5">
          <SkeletonStatGrid count={3} />

          <div className="grid grid-cols-1 gap-5 lg:grid-cols-[2fr_1fr]">
            <SkeletonChart />
            <SkeletonChart />
          </div>

          <SkeletonTable rows={6} cols={5} />
        </div>
      ) : (
        <div className="flex flex-col gap-6">
          <FinanceSummary
            transactions={transactions}
            currency={currency}
          />

          <div className="grid grid-cols-1 gap-5 lg:grid-cols-[2fr_1fr]">
            <ExpenseChart
              data={expenseChartData}
              currency={currency}
            />

            <CategoryChart
              data={categoryChartData}
              currency={currency}
            />
          </div>

          <IncomeProjectionCard
            projection={incomeProjection}
            currency={currency}
          />

          {/* Finance goals */}
          {financeGoals.length > 0 ? (
            <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
              {financeGoals.map((goal) => (
                <SavingsProgress
                  key={goal.goal_id}
                  goal={goal}
                  currency={currency}
                />
              ))}
            </div>
          ) : (
            <SavingsProgress goal={null} currency={currency} />
          )}

          <TransactionTable
            transactions={tableTransactions}
            onEdit={startEdit}
            onDelete={handleDelete}
            currency={currency}
            isLoading={isTableLoading}
            typeFilter={typeFilter}
            categoryFilter={categoryFilter}
            onTypeFilterChange={
              handleTypeFilterChange
            }
            onCategoryFilterChange={
              handleCategoryFilterChange
            }
            onClearFilters={clearFilters}
            transactionTypes={TRANSACTION_TYPES}
            financialCategories={
              FINANCIAL_CATEGORIES
            }
          />

          <Pagination
            page={page}
            totalPages={totalPages}
            onPageChange={setPage}
            disabled={isTableLoading}
          />
        </div>
      )}

      {/* ADD TRANSACTION */}
      <Drawer
        open={addDrawerOpen}
        onClose={() => setAddDrawerOpen(false)}
        title="Add Transaction"
      >
        <TransactionForm
          addTransaction={addTransaction}
          goals={financeGoals}
        />
      </Drawer>

      {/* EDIT TRANSACTION */}
      <Modal
        open={!!editingRecord}
        onClose={() => setEditingRecord(null)}
        title="Edit Transaction"
        maxWidth="max-w-xl"
      >
        <TransactionForm
          initialData={editingRecord}
          onUpdate={handleUpdate}
          onCancel={() => setEditingRecord(null)}
          goals={financeGoals}
        />
      </Modal>

      <ConfirmDialog
        open={confirmDeleteId !== null}
        title="Delete Transaction"
        message="Are you sure you want to delete this transaction? This action cannot be undone."
        confirmLabel="Delete"
        danger
        onConfirm={confirmDelete}
        onCancel={() => setConfirmDeleteId(null)}
      />
    </div>
  );
}

export default Finance;