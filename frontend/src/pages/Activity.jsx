import { useState, useEffect } from "react";
import { toast } from "react-toastify";
import { ArrowUp, ArrowDown, ArrowUpDown } from "lucide-react";
import { getActivityHistory } from "../services/activityService";
import Badge from "../components/ui/Badge";
import { SkeletonTable } from "../components/ui/Skeleton";
import EmptyState from "../components/ui/EmptyState";
import { activityBadgeTone } from "../utils/activityBadge";
import { Select } from "../components/ui/Field";
import Pagination from "../components/Pagination";

const TYPE_FILTERS = [
  { value: "", label: "All actions" },
  { value: "CREATED", label: "Created" },
  { value: "UPDATED", label: "Updated" },
  { value: "DELETED", label: "Deleted" },
];

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

function Activity() {
  const [activities, setActivities] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [typeFilter, setTypeFilter] = useState("");
  const [sortDir, setSortDir] = useState("desc");
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);

  useEffect(() => {
    let cancelled = false;
    async function fetchActivities() {
      setIsLoading(true);
      try {
        const result = await getActivityHistory({ page, limit: 20 });
        if (cancelled) return;
        setActivities(result.data || []);
        setTotalPages(result.total_pages || 1);
      } catch (err) {
        if (cancelled) return;
        console.error("Failed to fetch activity history:", err);
        toast.error("Could not load activity history. Please try again later.");
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }
    fetchActivities();
    return () => {
      cancelled = true;
    };
  }, [page]);

  // Client-side filter: action_type is already returned by the existing
  // /activity endpoint, so no new API call is needed for this.
  const filteredActivities = (typeFilter
    ? activities.filter((act) => (act.action_type || "").startsWith(typeFilter))
    : activities
  ).slice().sort((a, b) => {
    const diff = new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime();
    return sortDir === "asc" ? diff : -diff;
  });

  return (
    <div>
      <h2 className="text-2xl font-semibold text-slate-800 dark:text-slate-100">Activity History</h2>
      <p className="mb-6 mt-1.5 text-sm text-slate-500 dark:text-slate-400">
        A timeline of all your recent actions across Digital Twin.
      </p>

      {isLoading ? (
        <SkeletonTable rows={6} cols={4} />
      ) : activities.length === 0 ? (
        <EmptyState title="No activity found" message="Actions you take across Digital Twin will show up here." />
      ) : (
        <div className="overflow-x-auto rounded-2xl bg-white dark:bg-slate-800 p-6 shadow-sm">
          <div className="mb-4 flex justify-end">
            <Select
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value)}
              aria-label="Filter by action type"
              className="w-auto"
            >
              {TYPE_FILTERS.map((f) => (
                <option key={f.value} value={f.value}>{f.label}</option>
              ))}
            </Select>
          </div>
          <table className="w-full sm:min-w-125 border-collapse text-sm">
            <thead>
              <tr>
                <th className="border-b border-slate-200 dark:border-slate-700 p-2.5 text-left">
                  <SortButton label="Time" active dir={sortDir} onClick={() => setSortDir((d) => (d === "asc" ? "desc" : "asc"))} />
                </th>
                <th className="border-b border-slate-200 dark:border-slate-700 p-2.5 text-left font-semibold text-slate-500 dark:text-slate-400">Action</th>
                <th className="border-b border-slate-200 dark:border-slate-700 p-2.5 text-left font-semibold text-slate-500 dark:text-slate-400">Entity</th>
                <th className="hidden sm:table-cell border-b border-slate-200 dark:border-slate-700 p-2.5 text-left font-semibold text-slate-500 dark:text-slate-400">Description</th>
              </tr>
            </thead>
            <tbody>
              {filteredActivities.map((act) => {
                // action_type is like: CREATED_FINANCE, UPDATED_STUDY, DELETED_HABIT, UPSERTED_HABIT
                const at = act.action_type || "";
                return (
                  <tr key={act.id} className="hover:bg-slate-50 dark:hover:bg-slate-700/40">
                    <td className="border-b border-slate-100 dark:border-slate-700 p-2.5 font-mono tabular-nums text-slate-600 dark:text-slate-400">
                      {new Date(act.timestamp).toLocaleString(undefined, {
                        year: 'numeric', month: 'short', day: 'numeric',
                        hour: '2-digit', minute: '2-digit'
                      })}
                    </td>
                    <td className="border-b border-slate-100 dark:border-slate-700 p-2.5">
                      <Badge tone={activityBadgeTone(at)}>
                        {at.replace(/_/g, ' ')}
                      </Badge>
                    </td>
                    <td className="border-b border-slate-100 dark:border-slate-700 p-2.5 text-slate-600 dark:text-slate-400">{act.entity_type}</td>
                    <td className="hidden sm:table-cell border-b border-slate-100 dark:border-slate-700 p-2.5 text-slate-600 dark:text-slate-400">
                      {act.description || "-"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {filteredActivities.length === 0 && (
            <EmptyState title="No matching activity" message="Try a different action-type filter." />
          )}

          <div className="mt-4">
            <Pagination page={page} totalPages={totalPages} onPageChange={setPage} disabled={isLoading} />
          </div>
        </div>
      )}
    </div>
  );
}

export default Activity;
