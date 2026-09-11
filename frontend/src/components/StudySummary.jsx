import { StatGrid, StatTile } from "./ui/StatTile";

function StudySummary({ sessions, productivitySummary }) {
  const totalHours = Math.round(
    sessions.reduce((sum, session) => sum + Number(session.study_hours || 0), 0) * 10
  ) / 10;

  const totalSubjects = new Set(
    sessions.map((session) => session.subject)
  ).size;

  // Goal Completion and Productivity come from the backend's productivity
  // analytics (days studied / productivity score) rather than being derived
  // from session fields that don't exist on the real record shape.
  const goalPercentage = Math.round(
    productivitySummary?.completion_percentage?.completion_percentage ?? 0
  );

  const productivityScore = productivitySummary?.productivity_score?.productivity_score;
  const productivity =
    productivityScore == null
      ? "—"
      : productivityScore >= 80
      ? "Excellent"
      : productivityScore >= 50
      ? "Good"
      : "Average";

  return (
    <StatGrid>
      <StatTile label="Total Study Hours" value={totalHours} suffix=" hrs" />
      <StatTile label="Subjects" value={totalSubjects} />
      <StatTile label="Goal Completion" value={goalPercentage} suffix="%" />
      <StatTile label="Productivity" value={productivity} />
    </StatGrid>
  );
}

export default StudySummary;
