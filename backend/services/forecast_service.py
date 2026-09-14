"""
services/forecast_service.py — Financial Forecasting Service (Milestone 2, Pillar A).

Reads existing financial history via services.finance_service.get_monthly_cashflow()
(no new Mongo aggregation is written here) and existing User.active_goals, and produces:
  - monthly savings forecast
  - income projection
  - expense projection
  - goal completion estimate
  - confidence score (per forecast)

Forecasting method is chosen by how much history is available (avoids overengineering —
no ML dependency is required for a single-variable trend line):
  0 months   -> insufficient_data (income falls back to profile.monthly_income_baseline)
  1 month    -> naive_last_value
  2-3 months -> moving_average
  4+ months  -> linear_regression (manual least-squares)

All the actual math lives in plain module-level functions (no Beanie/Mongo involved),
so it is unit-testable without a live database. ForecastService only orchestrates:
fetch -> call pure functions -> wrap in response schema.
"""
from __future__ import annotations

import asyncio
import calendar
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from beanie import PydanticObjectId

from core.exceptions import NotFoundError
from models.enums import GoalCategory, TransactionType
from models.user import ActiveGoal, User
from schemas.finance_schema import MonthlyCashflowItem
from schemas.forecast_schema import (
    ExpenseProjectionResponse,
    ForecastAccuracyResponse,
    ForecastMethod,
    ForecastSummaryResponse,
    GoalCompletionResponse,
    IncomeProjectionResponse,
    MonthlyProjectionPoint,
    SavingsForecastResponse,
    SeriesAccuracy,
)
import services.finance_service as finance_service

DEFAULT_LOOKBACK_MONTHS = 12
MOVING_AVERAGE_WINDOW = 3


# ─── Pure data structures & helpers (no I/O — unit-tested directly) ───────────

@dataclass
class MonthlySeries:
    """Chronologically ordered (oldest -> newest) monthly income/expense/savings history."""
    periods: list[tuple[int, int]] = field(default_factory=list)  # (year, month)
    income: list[float] = field(default_factory=list)
    expense: list[float] = field(default_factory=list)
    savings: list[float] = field(default_factory=list)


def _generate_period_range(reference_date: datetime, lookback_months: int) -> list[tuple[int, int]]:
    """Returns `lookback_months` (year, month) tuples ending at reference_date's month, oldest first."""
    base = reference_date.year * 12 + (reference_date.month - 1)
    periods = []
    for i in range(lookback_months - 1, -1, -1):
        total = base - i
        year, month0 = divmod(total, 12)
        periods.append((year, month0 + 1))
    return periods


def _build_monthly_series(
    items: list[MonthlyCashflowItem],
    lookback_months: int,
    reference_date: Optional[datetime] = None,
) -> MonthlySeries:
    """
    Pivots MonthlyCashflowItem rows into ordered income/expense/savings series.
    Trims to the range [earliest month with any transaction, current month] and
    zero-fills gaps *within* that active range — it does not manufacture years of
    empty history before the user's first transaction, which would dilute the trend.
    """
    reference_date = reference_date or datetime.now(timezone.utc)
    all_periods = _generate_period_range(reference_date, lookback_months)

    income_map: dict[tuple[int, int], float] = {}
    expense_map: dict[tuple[int, int], float] = {}
    for item in items:
        key = (item.year, item.month)
        amount = float(item.total_amount)
        if item.type == TransactionType.INCOME:
            income_map[key] = income_map.get(key, 0.0) + amount
        elif item.type == TransactionType.EXPENSE:
            expense_map[key] = expense_map.get(key, 0.0) + amount

    active_periods = set(income_map) | set(expense_map)
    if not active_periods:
        return MonthlySeries()

    first_active_index = min(
        idx for idx, period in enumerate(all_periods) if period in active_periods
    )
    trimmed_periods = all_periods[first_active_index:]

    income_series = [income_map.get(p, 0.0) for p in trimmed_periods]
    expense_series = [expense_map.get(p, 0.0) for p in trimmed_periods]
    savings_series = [i - e for i, e in zip(income_series, expense_series)]

    return MonthlySeries(
        periods=trimmed_periods,
        income=income_series,
        expense=expense_series,
        savings=savings_series,
    )


def _select_method(n_points: int) -> ForecastMethod:
    if n_points <= 0:
        return ForecastMethod.INSUFFICIENT_DATA
    if n_points == 1:
        return ForecastMethod.NAIVE_LAST_VALUE
    if n_points <= 3:
        return ForecastMethod.MOVING_AVERAGE
    return ForecastMethod.LINEAR_REGRESSION


def _naive_forecast(values: list[float], periods_ahead: int) -> list[float]:
    return [values[-1]] * periods_ahead


def _moving_average_forecast(
    values: list[float], periods_ahead: int, window: int = MOVING_AVERAGE_WINDOW
) -> list[float]:
    window_values = values[-window:] if len(values) >= window else values
    average = sum(window_values) / len(window_values)
    return [average] * periods_ahead


def _linear_regression_forecast(
    values: list[float], periods_ahead: int
) -> tuple[list[float], float]:
    """Manual least-squares fit over x = 0..n-1. Returns (forecast_values, r_squared)."""
    n = len(values)
    xs = list(range(n))
    mean_x = sum(xs) / n
    mean_y = sum(values) / n

    ss_xx = sum((x - mean_x) ** 2 for x in xs)
    ss_xy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, values))
    slope = (ss_xy / ss_xx) if ss_xx != 0 else 0.0
    intercept = mean_y - slope * mean_x

    ss_tot = sum((y - mean_y) ** 2 for y in values)
    if ss_tot == 0:
        # All historical values are identical — the flat line fits perfectly.
        r_squared = 1.0
    else:
        predicted = [slope * x + intercept for x in xs]
        ss_res = sum((y - yp) ** 2 for y, yp in zip(values, predicted))
        r_squared = max(0.0, 1 - (ss_res / ss_tot))

    forecast = [slope * (n + i) + intercept for i in range(periods_ahead)]
    return forecast, r_squared


def _forecast_series(
    values: list[float], periods_ahead: int
) -> tuple[ForecastMethod, list[float], Optional[float]]:
    """Dispatches to the appropriate forecasting method based on how many points are available."""
    method = _select_method(len(values))
    if method == ForecastMethod.INSUFFICIENT_DATA:
        return method, [0.0] * periods_ahead, None
    if method == ForecastMethod.NAIVE_LAST_VALUE:
        return method, _naive_forecast(values, periods_ahead), None
    if method == ForecastMethod.MOVING_AVERAGE:
        return method, _moving_average_forecast(values, periods_ahead), None
    forecast, r_squared = _linear_regression_forecast(values, periods_ahead)
    return method, forecast, r_squared


@dataclass
class BacktestPoint:
    method: ForecastMethod
    actual: float
    predicted: float
    accuracy_pct: float


@dataclass
class BacktestResult:
    points: list[BacktestPoint] = field(default_factory=list)
    overall_accuracy_pct: float = 0.0


def _exclude_current_month(
    series: MonthlySeries, reference_date: Optional[datetime] = None
) -> tuple[list[float], list[float], list[float]]:
    """Drops the trailing period from income/expense/savings if it's the
    current calendar month — see backtest_accuracy's docstring for why."""
    if not series.periods:
        return [], [], []
    reference_date = reference_date or datetime.now(timezone.utc)
    current_period = (reference_date.year, reference_date.month)
    if series.periods[-1] == current_period:
        return series.income[:-1], series.expense[:-1], series.savings[:-1]
    return list(series.income), list(series.expense), list(series.savings)


def _backtest_series(values: list[float]) -> BacktestResult:
    """
    Walk-forward backtest: for each cutoff k (1..n-1), forecasts one step ahead using
    only values[:k] — the exact method-selection logic a live forecast would have used
    at that point in time — then scores it against the real values[k].

    Error is absolute percentage error against a magnitude-scaled floor (not a fixed
    constant), because a `savings` series can legitimately sit at/near zero some
    months, which would otherwise make a raw percentage error blow up or become
    meaningless. Per-point accuracy is 1 - ape, clamped to [0, 100]%.
    """
    n = len(values)
    if n < 2:
        return BacktestResult()

    points: list[BacktestPoint] = []
    for k in range(1, n):
        method, forecast_values, _ = _forecast_series(values[:k], periods_ahead=1)
        if method == ForecastMethod.INSUFFICIENT_DATA:
            continue
        predicted = forecast_values[0]
        actual = values[k]
        # Floor is derived only from values[:k] — the data a live forecast at
        # cutoff k would actually have had — not the whole series, which would
        # leak future magnitude into a supposedly point-in-time score.
        mean_abs = sum(abs(v) for v in values[:k]) / k
        floor = max(1.0, 0.01 * mean_abs)
        ape = abs(actual - predicted) / max(abs(actual), floor)
        accuracy_pct = max(0.0, min(100.0, (1 - ape) * 100))
        points.append(BacktestPoint(method=method, actual=actual, predicted=predicted, accuracy_pct=accuracy_pct))

    overall = round(sum(p.accuracy_pct for p in points) / len(points), 2) if points else 0.0
    return BacktestResult(points=points, overall_accuracy_pct=overall)


def _compute_confidence(
    method: ForecastMethod, n_points: int, r_squared: Optional[float]
) -> float:
    """
    Confidence score in [0.0, 1.0]. Monotonic with data volume and (for regression) fit quality.
    Thresholds are intentionally simple, not hidden magic — see plan doc for rationale.
    """
    if method == ForecastMethod.INSUFFICIENT_DATA:
        return 0.0
    if method == ForecastMethod.BASELINE_FALLBACK:
        return 0.1
    if method == ForecastMethod.NAIVE_LAST_VALUE:
        return 0.2
    if method == ForecastMethod.MOVING_AVERAGE:
        return round(0.35 + 0.05 * (n_points - 2), 2)  # 0.35 .. 0.45 for n=2..3

    # LINEAR_REGRESSION
    r2 = max(0.0, min(1.0, r_squared or 0.0))
    extra_points_bonus = min(0.1, max(0.0, 0.01 * (n_points - 4)))
    confidence = 0.5 + 0.4 * r2 + extra_points_bonus
    return round(min(0.95, max(0.0, confidence)), 2)


def _estimate_months_to_goal(
    current_value: Decimal, target_value: Decimal, monthly_delta: float
) -> Optional[int]:
    """0 if already met, None if unreachable at the current trend, else months (rounded up)."""
    remaining = float(target_value) - float(current_value)
    if remaining <= 0:
        return 0
    if monthly_delta <= 0:
        return None
    return math.ceil(remaining / monthly_delta)


def _days_in_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def _add_months(dt: datetime, months: int) -> datetime:
    total = dt.year * 12 + (dt.month - 1) + months
    year, month0 = divmod(total, 12)
    month = month0 + 1
    day = min(dt.day, _days_in_month(year, month))
    return dt.replace(year=year, month=month, day=day)


def _future_periods(
    anchor_year: int, anchor_month: int, periods_ahead: int
) -> list[tuple[int, int]]:
    """The `periods_ahead` (year, month) tuples immediately following the anchor month."""
    absolute = anchor_year * 12 + (anchor_month - 1)
    result = []
    for i in range(1, periods_ahead + 1):
        total = absolute + i
        year, month0 = divmod(total, 12)
        result.append((year, month0 + 1))
    return result


def _build_projection_points(
    series: MonthlySeries, values: list[float], periods_ahead: int, reference_date: datetime
) -> list[MonthlyProjectionPoint]:
    """Labels forecast values with the (year, month) that follows the series' last known period,
    or the current month if there's no history at all."""
    if series.periods:
        anchor_year, anchor_month = series.periods[-1]
    else:
        anchor_year, anchor_month = reference_date.year, reference_date.month

    future = _future_periods(anchor_year, anchor_month, periods_ahead)
    return [
        MonthlyProjectionPoint(year=y, month=m, projected_amount=Decimal(str(round(v, 2))))
        for (y, m), v in zip(future, values)
    ]


# ─── ForecastService ───────────────────────────────────────────────────────────

class ForecastService:
    def __init__(self, lookback_months: int = DEFAULT_LOOKBACK_MONTHS):
        self.lookback_months = lookback_months

    async def _get_monthly_series(self, user_id: str) -> MonthlySeries:
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=self.lookback_months * 30)
        items = await finance_service.get_monthly_cashflow(user_id, start, now)
        return _build_monthly_series(items, self.lookback_months, reference_date=now)

    async def _get_income_baseline(self, user_id: str) -> Optional[float]:
        user = await User.get(PydanticObjectId(user_id))
        if user and user.profile and user.profile.monthly_income_baseline > 0:
            return float(user.profile.monthly_income_baseline)
        return None

    async def forecast_monthly_savings(
        self, user_id: str, months_ahead: int = 1
    ) -> SavingsForecastResponse:
        """Projects future monthly savings (income - expense)."""
        now = datetime.now(timezone.utc)
        series = await self._get_monthly_series(user_id)
        method, values, r_squared = _forecast_series(series.savings, months_ahead)
        confidence = _compute_confidence(method, len(series.savings), r_squared)
        return SavingsForecastResponse(
            user_id=user_id,
            projections=_build_projection_points(series, values, months_ahead, now),
            method_used=method,
            data_points_used=len(series.savings),
            confidence_score=confidence,
        )

    async def project_income(
        self, user_id: str, months_ahead: int = 1
    ) -> IncomeProjectionResponse:
        """Projects future monthly income. Falls back to profile.monthly_income_baseline
        when there is no transaction history at all."""
        now = datetime.now(timezone.utc)
        series = await self._get_monthly_series(user_id)

        if not series.income:
            baseline = await self._get_income_baseline(user_id)
            if baseline is not None:
                method = ForecastMethod.BASELINE_FALLBACK
                values = [baseline] * months_ahead
                confidence = _compute_confidence(method, 0, None)
                return IncomeProjectionResponse(
                    user_id=user_id,
                    projections=_build_projection_points(series, values, months_ahead, now),
                    method_used=method,
                    data_points_used=0,
                    confidence_score=confidence,
                )

        method, values, r_squared = _forecast_series(series.income, months_ahead)
        confidence = _compute_confidence(method, len(series.income), r_squared)
        return IncomeProjectionResponse(
            user_id=user_id,
            projections=_build_projection_points(series, values, months_ahead, now),
            method_used=method,
            data_points_used=len(series.income),
            confidence_score=confidence,
        )

    async def project_expenses(
        self, user_id: str, months_ahead: int = 1
    ) -> ExpenseProjectionResponse:
        """Projects future monthly expenses. No sane fallback exists for expenses when
        there's no history, so this simply reports insufficient_data."""
        now = datetime.now(timezone.utc)
        series = await self._get_monthly_series(user_id)
        method, values, r_squared = _forecast_series(series.expense, months_ahead)
        confidence = _compute_confidence(method, len(series.expense), r_squared)
        return ExpenseProjectionResponse(
            user_id=user_id,
            projections=_build_projection_points(series, values, months_ahead, now),
            method_used=method,
            data_points_used=len(series.expense),
            confidence_score=confidence,
        )

    def _build_goal_completion(
        self, goal: ActiveGoal, series: MonthlySeries
    ) -> GoalCompletionResponse:
        method, values, r_squared = _forecast_series(series.savings, 1)
        monthly_delta = values[0] if values else 0.0
        confidence = _compute_confidence(method, len(series.savings), r_squared)

        months_remaining = _estimate_months_to_goal(
            goal.current_value, goal.target_value, monthly_delta
        )
        completion_date: Optional[datetime] = None
        on_track: Optional[bool] = None
        if months_remaining is not None:
            completion_date = _add_months(datetime.now(timezone.utc), months_remaining)
            on_track = completion_date <= goal.target_date

        return GoalCompletionResponse(
            goal_id=goal.goal_id,
            title=goal.title,
            category=goal.category,
            current_value=goal.current_value,
            target_value=goal.target_value,
            target_date=goal.target_date,
            monthly_projected_delta=Decimal(str(round(monthly_delta, 2))),
            estimated_months_remaining=months_remaining,
            estimated_completion_date=completion_date,
            on_track=on_track,
            method_used=method,
            confidence_score=confidence,
        )

    async def estimate_goal_completion(
        self, user_id: str, goal_id: str
    ) -> GoalCompletionResponse:
        user = await User.get(PydanticObjectId(user_id))
        if not user:
            raise NotFoundError("User", user_id)
        goal = next((g for g in user.active_goals if g.goal_id == goal_id), None)
        if not goal:
            raise NotFoundError("Goal", goal_id)

        series = await self._get_monthly_series(user_id)
        return self._build_goal_completion(goal, series)

    async def estimate_all_goal_completions(
        self, user_id: str
    ) -> list[GoalCompletionResponse]:
        user = await User.get(PydanticObjectId(user_id))
        if not user:
            raise NotFoundError("User", user_id)

        finance_goals = [g for g in user.active_goals if g.category == GoalCategory.FINANCE]
        series = await self._get_monthly_series(user_id)
        return [self._build_goal_completion(g, series) for g in finance_goals]

    async def get_forecast_summary(self, user_id: str) -> ForecastSummaryResponse:
        savings, income, expenses, goals = await asyncio.gather(
            self.forecast_monthly_savings(user_id),
            self.project_income(user_id),
            self.project_expenses(user_id),
            self.estimate_all_goal_completions(user_id),
        )

        confidences = [savings.confidence_score, income.confidence_score, expenses.confidence_score]
        confidences.extend(g.confidence_score for g in goals)
        overall_confidence = round(sum(confidences) / len(confidences), 2) if confidences else 0.0

        return ForecastSummaryResponse(
            user_id=user_id,
            savings_forecast=savings,
            income_projection=income,
            expense_projection=expenses,
            goal_completions=goals,
            overall_confidence_score=overall_confidence,
            generated_at=datetime.now(timezone.utc),
        )

    async def backtest_accuracy(self, user_id: str) -> ForecastAccuracyResponse:
        """Retrospective accuracy (Milestone 2's '≥85%' evaluation criterion) — distinct
        from confidence_score, which is a live, forward-looking heuristic. Walk-forward
        backtests income/expense/savings against this user's real transaction history.

        The current (still in-progress) calendar month is excluded from the backtest
        only — _get_monthly_series legitimately includes it for live forward-looking
        forecasts (it's the most recent real signal), but scoring a forecast against
        a partial month's total is not a fair accuracy measurement: a $30k/month
        earner's day-1-of-the-month total looks like a collapse to $1k, which every
        method will "miss" no matter how good it is."""
        series = await self._get_monthly_series(user_id)
        income, expense, savings = _exclude_current_month(series)
        income_result = _backtest_series(income)
        expense_result = _backtest_series(expense)
        savings_result = _backtest_series(savings)

        all_points = income_result.points + expense_result.points + savings_result.points
        overall = round(sum(p.accuracy_pct for p in all_points) / len(all_points), 2) if all_points else 0.0

        by_method: dict[ForecastMethod, list[float]] = {}
        for p in all_points:
            by_method.setdefault(p.method, []).append(p.accuracy_pct)
        by_method_avg = {method: round(sum(vals) / len(vals), 2) for method, vals in by_method.items()}

        return ForecastAccuracyResponse(
            user_id=user_id,
            income_accuracy=SeriesAccuracy(
                accuracy_pct=income_result.overall_accuracy_pct, points_evaluated=len(income_result.points)
            ),
            expense_accuracy=SeriesAccuracy(
                accuracy_pct=expense_result.overall_accuracy_pct, points_evaluated=len(expense_result.points)
            ),
            savings_accuracy=SeriesAccuracy(
                accuracy_pct=savings_result.overall_accuracy_pct, points_evaluated=len(savings_result.points)
            ),
            overall_accuracy_pct=overall,
            by_method=by_method_avg,
            generated_at=datetime.now(timezone.utc),
        )


forecast_service = ForecastService()
