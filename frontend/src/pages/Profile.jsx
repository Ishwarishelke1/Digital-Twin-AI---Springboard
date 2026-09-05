import { useEffect, useState } from "react";
import { toast } from "react-toastify";
import { Link } from "react-router-dom";
import { UserX } from "lucide-react";

import ProfileCard from "../components/ProfileCard";
import InfoCard from "../components/InfoCard";
import ProfileForm from "../components/ProfileForm";
import { SkeletonCard } from "../components/ui/Skeleton";
import EmptyState from "../components/ui/EmptyState";

import { getUser, updateUser } from "../services/userService";

function Profile() {

  const [user, setUser] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [editing, setEditing] = useState(false);

  useEffect(() => {

    async function loadUser() {
      try {
        const data = await getUser();
        setUser(data);
      } catch (err) {
        console.error("Failed to load profile:", err);
        toast.error("Could not load your profile. Please try again.");
      } finally {
        setIsLoading(false);
      }
    }

    loadUser();

  }, []);

  async function saveUser(profilePayload) {
    const updated = await updateUser(profilePayload);
    setUser(updated);
    setEditing(false);
    toast.success("Profile updated successfully.");
  }

  if (isLoading) return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[320px_1fr]">
      <SkeletonCard lines={2} />
      <SkeletonCard lines={4} />
    </div>
  );
  if (!user) return (
    <EmptyState
      icon={UserX}
      title="Could not load your profile"
      message="Something went wrong loading your profile. Please refresh the page to try again."
    />
  );

  return (

    <div>

      <h2 className="mb-6 text-2xl font-semibold text-slate-800 dark:text-slate-100">My Digital Twin Profile</h2>

      {editing ? (

        <ProfileForm
          user={user}
          onSave={saveUser}
          onCancel={() => setEditing(false)}
        />

      ) : (

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[320px_1fr]">

          <ProfileCard
            user={user}
            onEdit={() => setEditing(true)}
          />

          <div className="flex flex-col gap-5">

            <InfoCard user={user} />

            {/* Goal management moved to its own page (/goals) — see Sidebar's
                Overview group — rather than duplicating the add/edit/delete
                flow here too. */}
            <div className="flex items-center justify-between rounded-2xl bg-white dark:bg-slate-800 p-5 shadow-sm">
              <div>
                <h3 className="text-base font-semibold text-slate-800 dark:text-slate-100">Goals</h3>
                <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
                  {user.active_goals?.length
                    ? `${user.active_goals.filter((g) => g.status !== "COMPLETED").length} active, ${user.active_goals.filter((g) => g.status === "COMPLETED").length} completed`
                    : "No goals yet."}
                </p>
              </div>
              <Link to="/goals" className="text-sm font-medium text-indigo-600 dark:text-indigo-400 hover:underline">
                View Goals →
              </Link>
            </div>

          </div>

        </div>

      )}

    </div>

  );

}

export default Profile;
