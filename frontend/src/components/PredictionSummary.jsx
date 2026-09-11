import { StatGrid, StatTile } from "./ui/StatTile";

function PredictionSummary({ history }) {

  const latest =
    history.length > 0
      ? history[history.length - 1]
      : {
          finance: 0,
          study: 0,
          health: 0,
          overall: 0,
        };

  return (
    <div className="">
      <StatGrid>
        <StatTile predicted label="Overall AI Score" value={latest.overall} suffix="%" />
        <StatTile predicted label="Finance Prediction" value={latest.finance} suffix="%" />
        <StatTile predicted label="Study Prediction" value={latest.study} suffix="%" />
        <StatTile predicted label="Health Prediction" value={latest.health} suffix="%" />
      </StatGrid>
    </div>
  );
}

export default PredictionSummary;
