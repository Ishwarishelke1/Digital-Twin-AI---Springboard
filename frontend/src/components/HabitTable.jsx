import { useState } from "react";
import { Trash2, ArrowUp, ArrowDown, ArrowUpDown } from "lucide-react";
import { Input } from "./ui/Field";
import Badge from "./ui/Badge";
import EmptyState from "./ui/EmptyState";

const SORTERS = {
  date: (h) => new Date(h.log_date || 0).getTime(),
  sleep: (h) => Number(h.sleep || 0),
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

function HabitTable({ habits, onDelete }) {

  const [searchMood, setSearchMood] = useState("");
  const [sortKey, setSortKey] = useState("date");
  const [sortDir, setSortDir] = useState("desc");

  const filteredHabits = habits.filter((item) =>
    (item.mood || "")
      .toLowerCase()
      .includes(searchMood.toLowerCase())
  );

  const sortedHabits = [...filteredHabits].sort((a, b) => {
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

        <h3 className="text-lg font-semibold text-slate-800 dark:text-slate-100">Habit History</h3>

        <Input
          type="text"
          placeholder="Search Mood..."
          value={searchMood}
          onChange={(e) => setSearchMood(e.target.value)}
          className="max-w-48"
        />

      </div>

      {filteredHabits.length === 0 ? (
        <EmptyState title="No habit logs found" message="Try a different search or log today's habits." />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-125 border-collapse text-sm">

            <thead>
              <tr>
                <th className="border-b border-slate-200 dark:border-slate-700 p-2 text-left">
                  <SortButton label="Date" active={sortKey === "date"} dir={sortDir} onClick={() => toggleSort("date")} />
                </th>
                <th className="border-b border-slate-200 dark:border-slate-700 p-2 text-left font-semibold text-slate-500 dark:text-slate-400">Water (L)</th>
                <th className="border-b border-slate-200 dark:border-slate-700 p-2 text-left">
                  <SortButton label="Sleep" active={sortKey === "sleep"} dir={sortDir} onClick={() => toggleSort("sleep")} />
                </th>
                <th className="border-b border-slate-200 dark:border-slate-700 p-2 text-left font-semibold text-slate-500 dark:text-slate-400">Exercise</th>
                <th className="border-b border-slate-200 dark:border-slate-700 p-2 text-left font-semibold text-slate-500 dark:text-slate-400">Mood</th>
                <th className="border-b border-slate-200 dark:border-slate-700 p-2 text-left font-semibold text-slate-500 dark:text-slate-400">Actions</th>
              </tr>
            </thead>

            <tbody>
              {sortedHabits.map((habit) => (
                <tr key={habit.id} className="hover:bg-slate-50 dark:hover:bg-slate-700/40">
                  <td className="border-b border-slate-100 dark:border-slate-700 p-2 font-mono tabular-nums text-slate-600 dark:text-slate-400">{habit.date}</td>
                  <td className="border-b border-slate-100 dark:border-slate-700 p-2 font-mono tabular-nums text-slate-600 dark:text-slate-400">{habit.water} L</td>
                  <td className="border-b border-slate-100 dark:border-slate-700 p-2 font-mono tabular-nums text-slate-600 dark:text-slate-400">{habit.sleep} hrs</td>
                  <td className="border-b border-slate-100 dark:border-slate-700 p-2 font-mono tabular-nums text-slate-600 dark:text-slate-400">{habit.exercise} min</td>
                  <td className="border-b border-slate-100 dark:border-slate-700 p-2">
                    <Badge tone="info">{habit.mood}</Badge>
                  </td>
                  <td className="border-b border-slate-100 dark:border-slate-700 p-2">
                    <button
                      onClick={() => onDelete && onDelete(habit.id)}
                      className="rounded-md p-1.5 text-red-400 hover:bg-slate-100 hover:text-red-600 dark:hover:bg-white/10"
                      aria-label="Delete"
                    >
                      <Trash2 size={16} />
                    </button>
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

export default HabitTable;
