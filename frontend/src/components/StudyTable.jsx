import { useState } from "react";
import { Edit, Trash2, ArrowUp, ArrowDown, ArrowUpDown, Loader2 } from "lucide-react";
import { Input } from "./ui/Field";
import Badge from "./ui/Badge";
import EmptyState from "./ui/EmptyState";
import { FilterMenu, FilterDropdown } from "./ui/FilterMenu";

const SESSION_TYPE_LABELS = {
  DEEP_WORK: "Deep Work",
  REVIEW: "Review",
  LECTURE: "Lecture",
  PRACTICE_EXAM: "Practice Exam",
  ASSIGNMENT: "Assignment",
  RESEARCH: "Research",
};

/* Hours are stored as entered. The form converts "5 hours 59 minutes" to
 * 5.983333333333333, so the raw value has to be rounded for display — a session
 * rendered as "5.9833333333333 hrs" is a formatting bug, not extra precision. */
const SORTERS = {
  date: (s) => new Date(s.session_date || 0).getTime(),
  hours: (s) => Number(s.study_hours ?? s.hours ?? 0),
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

function StudyTable({
  sessions, onEdit, onDelete, isLoading = false,
  subjectFilter, sessionTypeFilter, onSubjectFilterChange, onSessionTypeFilterChange,
  onClearFilters, subjects = [],
}) {

  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState("date");
  const [sortDir, setSortDir] = useState("desc");

  /* Search narrows the page you are looking at; the menu filters re-query the
   * server. Same split as the Finance table — subject and session type change
   * which rows exist, so they cannot be done client-side over one page of 50. */
  const filteredSessions = sessions.filter((item) =>
    (item.subject || "").toLowerCase().includes(search.toLowerCase())
  );

  const sortedSessions = [...filteredSessions].sort((a, b) => {
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
          <h3 className="text-lg font-semibold text-slate-800 dark:text-slate-100">Study History</h3>
          {isLoading && (
            <Loader2 size={16} strokeWidth={2} className="animate-spin text-slate-400" aria-label="Refreshing" />
          )}
        </div>

        <div className="flex items-center gap-2.5">

          <Input
            type="text"
            placeholder="Search subject..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="max-w-56"
          />

          <FilterMenu
            label="Filter sessions"
            hasActiveFilter={Boolean(subjectFilter || sessionTypeFilter)}
            onClearFilters={onClearFilters}
          >
            <FilterDropdown
              label="Filter by subject"
              placeholder="All subjects"
              value={subjectFilter}
              onChange={onSubjectFilterChange}
              options={subjects.map((s) => ({ value: s, label: s }))}
            />

            <FilterDropdown
              label="Filter by session type"
              placeholder="All types"
              value={sessionTypeFilter}
              onChange={onSessionTypeFilterChange}
              options={Object.entries(SESSION_TYPE_LABELS).map(([value, label]) => ({ value, label }))}
            />
          </FilterMenu>

        </div>

      </div>

      {filteredSessions.length === 0 ? (
        <EmptyState title="No study sessions found" message="Try a different search or log a new session." />
      ) : (
        <div className={`overflow-x-auto transition-opacity ${isLoading ? "opacity-50" : "opacity-100"}`}>
          <table className="w-full min-w-150 border-collapse text-sm">

            <thead>
              <tr>
                <th className="border-b border-slate-200 dark:border-slate-700 p-2.5 text-left">
                  <SortButton label="Date" active={sortKey === "date"} dir={sortDir} onClick={() => toggleSort("date")} />
                </th>
                <th className="border-b border-slate-200 dark:border-slate-700 p-2.5 text-left font-semibold text-slate-500 dark:text-slate-400">Subject</th>
                <th className="border-b border-slate-200 dark:border-slate-700 p-2.5 text-left">
                  <SortButton label="Hours" active={sortKey === "hours"} dir={sortDir} onClick={() => toggleSort("hours")} />
                </th>
                <th className="border-b border-slate-200 dark:border-slate-700 p-2.5 text-left font-semibold text-slate-500 dark:text-slate-400">Session Type</th>
                <th className="border-b border-slate-200 dark:border-slate-700 p-2.5 text-left font-semibold text-slate-500 dark:text-slate-400">Actions</th>
              </tr>
            </thead>

            <tbody>
              {sortedSessions.map((item) => (
                <tr key={item.id} className="hover:bg-slate-50 dark:hover:bg-slate-700/40">
                  <td className="border-b border-slate-100 dark:border-slate-700 p-2.5 font-mono tabular-nums text-slate-600 dark:text-slate-400">
                    {item.session_date ? new Date(item.session_date).toLocaleDateString() : "-"}
                  </td>

                  <td className="border-b border-slate-100 dark:border-slate-700 p-2.5 text-slate-600 dark:text-slate-400">{item.subject}</td>

                  <td className="border-b border-slate-100 dark:border-slate-700 p-2.5 font-mono tabular-nums text-slate-600 dark:text-slate-400">{Number(item.study_hours ?? item.hours ?? 0).toFixed(1)} hrs</td>

                  <td className="border-b border-slate-100 dark:border-slate-700 p-2.5">
                    <Badge tone={item.session_type === "DEEP_WORK" || item.session_type === "REVIEW" ? "success" : "warning"}>
                      {item.session_type ? item.session_type.replace(/_/g, " ") : "-"}
                    </Badge>
                  </td>

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

export default StudyTable;
