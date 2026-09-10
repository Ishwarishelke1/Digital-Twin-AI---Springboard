import { useState } from "react";
import { Edit, Trash2, ArrowUp, ArrowDown, ArrowUpDown, Loader2 } from "lucide-react";
import { Input } from "./ui/Field";
import Badge from "./ui/Badge";
import EmptyState from "./ui/EmptyState";
import { FilterMenu, FilterDropdown } from "./ui/FilterMenu";
import { formatCurrency } from "../utils/currency";

const SORTERS = {
  date: (t) => new Date(t.transaction_date || 0).getTime(),
  amount: (t) => Number(t.amount || 0),
};

function SortButton({ label, active, dir, onClick }) {
  const Icon = !active ? ArrowUpDown : dir === "asc" ? ArrowUp : ArrowDown;
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex items-center gap-1 font-semibold text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200"
    >
      {label}
      <Icon size={13} className={active ? "text-indigo-600 dark:text-indigo-400" : "text-slate-300 dark:text-slate-600"} />
    </button>
  );
}

function TransactionTable({
  transactions, onEdit, onDelete, currency = "USD", isLoading = false,
  typeFilter, categoryFilter, onTypeFilterChange, onCategoryFilterChange,
  onClearFilters, transactionTypes = [], financialCategories = [],
}) {
  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState("date");
  const [sortDir, setSortDir] = useState("desc");

  const filteredTransactions = transactions.filter((item) =>
    (item.category || "")
      .toLowerCase()
      .includes(search.toLowerCase())
  );

  // Sorts the currently-loaded page only — the backend already orders by
  // date via idx_finance_user_date, so this just lets the user flip that
  // order (or sort by amount) without a new API contract.
  const sortedTransactions = [...filteredTransactions].sort((a, b) => {
    const diff = SORTERS[sortKey](a) - SORTERS[sortKey](b);
    return sortDir === "asc" ? diff : -diff;
  });

  function toggleSort(key) {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  }

  return (
    <div className="rounded-2xl bg-white dark:bg-slate-800 p-6 shadow-sm">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <h3 className="text-lg font-semibold text-slate-800 dark:text-slate-100">Transaction History</h3>
          {isLoading && (
            <Loader2 size={16} strokeWidth={2} className="animate-spin text-slate-400" aria-label="Refreshing" />
          )}
        </div>

        <div className="flex items-center gap-2.5">
          <Input
            type="text"
            placeholder="Search category..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="max-w-56"
          />

          <FilterMenu
            label="Filter transactions"
            hasActiveFilter={Boolean(typeFilter || categoryFilter)}
            onClearFilters={onClearFilters}
          >
            <FilterDropdown
              label="Filter by type"
              placeholder="All types"
              value={typeFilter}
              onChange={onTypeFilterChange}
              options={transactionTypes.map((t) => ({ value: t, label: t.replace("_", " ") }))}
            />

            <FilterDropdown
              label="Filter by category"
              placeholder="All categories"
              value={categoryFilter}
              onChange={onCategoryFilterChange}
              options={financialCategories.map((c) => ({ value: c, label: c }))}
            />
          </FilterMenu>
        </div>
      </div>

      {filteredTransactions.length === 0 ? (
        <EmptyState title="No transactions found" message="Try a different search or add a new transaction." />
      ) : (
        <div className={`overflow-x-auto transition-opacity ${isLoading ? "opacity-50" : "opacity-100"}`}>
          <table className="w-full min-w-150 border-collapse text-sm">
            <thead>
              <tr>
                <th className="border-b border-slate-200 dark:border-slate-700 p-2.5 text-left">
                  <SortButton label="Date" active={sortKey === "date"} dir={sortDir} onClick={() => toggleSort("date")} />
                </th>
                <th className="border-b border-slate-200 dark:border-slate-700 p-2.5 text-left font-semibold text-slate-500 dark:text-slate-400">Type</th>
                <th className="border-b border-slate-200 dark:border-slate-700 p-2.5 text-left font-semibold text-slate-500 dark:text-slate-400">Category</th>
                <th className="border-b border-slate-200 dark:border-slate-700 p-2.5 text-right">
                  <div className="flex justify-end">
                    <SortButton label="Amount" active={sortKey === "amount"} dir={sortDir} onClick={() => toggleSort("amount")} />
                  </div>
                </th>
                <th className="border-b border-slate-200 dark:border-slate-700 p-2.5 text-left font-semibold text-slate-500 dark:text-slate-400">Description</th>
                <th className="border-b border-slate-200 dark:border-slate-700 p-2.5 text-left font-semibold text-slate-500 dark:text-slate-400">Actions</th>
              </tr>
            </thead>

            <tbody>
              {sortedTransactions.map((item) => (
                <tr key={item.id} className="hover:bg-slate-50 dark:hover:bg-slate-700/40">
                  <td className="border-b border-slate-100 dark:border-slate-700 p-2.5 font-mono tabular-nums text-slate-600 dark:text-slate-400">
                    {item.transaction_date ? new Date(item.transaction_date).toLocaleDateString() : "-"}
                  </td>

                  <td className="border-b border-slate-100 dark:border-slate-700 p-2.5">
                    <Badge tone={String(item.type).toUpperCase() === "INCOME" ? "success" : "danger"}>{item.type}</Badge>
                  </td>

                  <td className="border-b border-slate-100 dark:border-slate-700 p-2.5 text-slate-600 dark:text-slate-400">{item.category}</td>

                  <td className="border-b border-slate-100 dark:border-slate-700 p-2.5 text-right font-mono tabular-nums text-slate-600 dark:text-slate-400">{formatCurrency(item.amount, currency)}</td>

                  <td className="border-b border-slate-100 dark:border-slate-700 p-2.5 text-slate-600 dark:text-slate-400">{item.description}</td>

                  <td className="border-b border-slate-100 dark:border-slate-700 p-2.5">
                    <div className="flex gap-1">
                      <button
                        onClick={() => onEdit && onEdit(item)}
                        className="rounded-md p-1.5 text-slate-400 hover:bg-slate-100 hover:text-indigo-600 dark:hover:text-indigo-400 dark:hover:bg-white/10"
                        aria-label="Edit"
                      >
                        <Edit size={16} />
                      </button>
                      <button
                        onClick={() => onDelete && onDelete(item.id)}
                        className="rounded-md p-1.5 text-red-400 hover:bg-slate-100 hover:text-red-600 dark:hover:bg-white/10"
                        aria-label="Delete"
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default TransactionTable;
