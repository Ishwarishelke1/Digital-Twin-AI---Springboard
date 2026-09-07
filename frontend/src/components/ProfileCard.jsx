import Button from "./ui/Button";

function ProfileCard({ user, onEdit }) {
  const name       = user?.profile?.name       ?? "—";
  const occupation = user?.profile?.occupation ?? "Digital Twin User";

  // Derive initials for the avatar placeholder
  const initials = name
    .split(" ")
    .map((w) => w[0])
    .join("")
    .toUpperCase()
    .slice(0, 2);

  return (

    <div className="rounded-2xl border border-slate-100 bg-white dark:border-slate-700 dark:bg-slate-800 p-8 text-center shadow-sm">

      <div
        className="mx-auto mb-5 flex h-35 w-35 items-center justify-center rounded-full bg-indigo-100 text-4xl font-semibold text-indigo-600 dark:text-indigo-400"
        role="img"
        aria-label={`Avatar for ${name}`}
      >
        {initials}
      </div>

      <h2 className="mb-2.5 text-xl font-semibold text-slate-800 dark:text-slate-100">{name}</h2>

      <p className="mb-5 text-sm text-slate-500 dark:text-slate-400">{occupation}</p>

      <Button onClick={onEdit}>
        Edit Profile
      </Button>

    </div>

  );
}

export default ProfileCard;
