import { StatGrid, StatTile } from "./ui/StatTile";

function HabitSummary({ habits }) {
  const averageWater = habits.length === 0
    ? 0
    : Number(
        (
          habits.reduce((sum, item) => sum + Number(item.water), 0) / habits.length
        ).toFixed(1)
      );

  const averageSleep = habits.length === 0
    ? 0
    : Number(
        (
          habits.reduce((sum, item) => sum + Number(item.sleep), 0) / habits.length
        ).toFixed(1)
      );

  const totalExercise = habits.reduce(
    (sum, item) => sum + Number(item.exercise),
    0
  );

  const moodScore =
    habits.filter(
      (item) =>
        item.mood === "Happy" ||
        item.mood === "Excellent"
    ).length;

  return (
    <StatGrid>
      <StatTile label="Avg Water Intake" value={averageWater} decimals={1} suffix=" L" />
      <StatTile label="Average Sleep" value={averageSleep} decimals={1} suffix=" hrs" />
      <StatTile label="Total Exercise" value={totalExercise} suffix=" min" />
      <StatTile label="Positive Mood" value={`${moodScore}/${habits.length}`} />
    </StatGrid>
  );
}

export default HabitSummary;
