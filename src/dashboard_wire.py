"""Lossless, JSON-only UI transport; never serialize executable Python objects.

These contracts supplement the original v1 responses, which remain unchanged.
DataFrame dtype metadata preserves Decimal money, calendar dates and nullable flags.
"""

from dataclasses import asdict
from datetime import date
from decimal import Decimal
from typing import Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, StrictBool, StrictInt, StrictStr

from src.anomaly_detection import AnomalyResult
from src.dashboard_service import DashboardBundle
from src.data_processing import ImportResult, ValidationIssue
from src.forecasting import ForecastEvent, ForecastResult, RecurringPattern
from src.metrics import FinancialMetrics
from src.risk_engine import RiskFactor, RiskResult
from src.scenario_simulator import ScenarioConfig, ScenarioResult


class Wire(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Column(Wire):
    name: str = Field(max_length=100)
    dtype: Literal["object", "int64", "float64", "bool", "boolean", "Int64", "Float64", "str", "string"]
    kind: Literal["native", "date", "decimal"] = "native"
    missing: Literal["none", "nan", "pdna"] = "none"


class Table(Wire):
    columns: list[Column] = Field(max_length=60)
    rows: list[dict[str, StrictStr | StrictBool | StrictInt | FiniteFloat | None]] = Field(max_length=10000)


def table(frame):
    columns = []
    for name in frame.columns:
        values = frame[name].dropna()
        first = values.iloc[0] if len(values) else None
        kind = "decimal" if isinstance(first, Decimal) else "date" if isinstance(first, date) else "native"
        absent = frame.loc[frame[name].isna(), name]
        missing = absent.iloc[0] if len(absent) else None
        missing_kind = "none" if missing is None else "pdna" if missing is pd.NA else "nan"
        columns.append(Column(name=name, dtype=str(frame[name].dtype), kind=kind, missing=missing_kind))
    def cell(value):
        if pd.isna(value):
            return None
        if isinstance(value, (date, Decimal)):
            return value.isoformat() if isinstance(value, date) else str(value)
        return value.item() if hasattr(value, "item") else value
    return Table(columns=columns, rows=[{name: cell(value) for name, value in row.items()}
                                      for row in frame.to_dict("records")])


def dataframe(value):
    value = Table.model_validate(value)
    names = [column.name for column in value.columns]
    if len(names) != len(set(names)) or any(set(row) != set(names) for row in value.rows):
        raise ValueError("Invalid table shape")
    frame = pd.DataFrame(value.rows, columns=names, dtype=object)
    for column in value.columns:
        convert = date.fromisoformat if column.kind == "date" else Decimal if column.kind == "decimal" else lambda v: v
        missing = None if column.missing == "none" else pd.NA if column.missing == "pdna" else float("nan")
        frame[column.name] = pd.Series([missing if v is None else convert(v) for v in frame[column.name]], dtype=object)
        frame[column.name] = frame[column.name].astype(column.dtype)
    return frame


class ImportWire(Wire):
    data: Table
    issues: list[ValidationIssue]
    input_rows: int
    duplicates_removed: int

    @classmethod
    def pack(cls, value):
        return cls(data=table(value.data), issues=value.issues,
                   input_rows=value.input_rows, duplicates_removed=value.duplicates_removed)

    def unpack(self):
        return ImportResult(dataframe(self.data), self.issues, self.input_rows, self.duplicates_removed)


class ForecastWire(Wire):
    as_of: date
    horizon_days: int
    current_balance_cents: int
    cash_threshold_cents: int
    history_days: int
    history_rows: int
    daily: Table
    events: list[ForecastEvent]
    recurring_patterns: list[RecurringPattern]
    assumptions: list[str]
    warnings: list[str]

    @classmethod
    def pack(cls, value):
        return cls(**{name: table(getattr(value, name)) if name == "daily" else getattr(value, name)
                      for name in cls.model_fields})

    def unpack(self):
        return ForecastResult(**{name: dataframe(self.daily) if name == "daily"
                                 else tuple(getattr(self, name)) if name in {"events", "recurring_patterns", "assumptions", "warnings"}
                                 else getattr(self, name) for name in type(self).model_fields})


class AnomalyWire(Wire):
    data: Table
    as_of: date
    warnings: list[str]

    @classmethod
    def pack(cls, value):
        return cls(data=table(value.data), as_of=value.as_of, warnings=value.warnings)

    def unpack(self):
        return AnomalyResult(dataframe(self.data), self.as_of, tuple(self.warnings))


class RiskWire(Wire):
    score: int | None
    level: str
    data_sufficiency: str
    factors: list[RiskFactor]
    warnings: list[str]


class DashboardWire(Wire):
    data: Table
    metrics: FinancialMetrics
    forecast: ForecastWire
    anomalies: AnomalyWire
    risk: RiskWire
    balance_history: Table
    monthly: Table
    spending: Table

    @classmethod
    def pack(cls, value):
        return cls(data=table(value.data), metrics=value.metrics, forecast=ForecastWire.pack(value.forecast),
                   anomalies=AnomalyWire.pack(value.anomalies), risk=RiskWire(**asdict(value.risk)),
                   balance_history=table(value.balance_history), monthly=table(value.monthly), spending=table(value.spending))

    def unpack(self):
        return DashboardBundle(dataframe(self.data), self.metrics, self.forecast.unpack(), self.anomalies.unpack(),
                               RiskResult(self.risk.score, self.risk.level, self.risk.data_sufficiency,
                                          tuple(self.risk.factors), tuple(self.risk.warnings)),
                               dataframe(self.balance_history), dataframe(self.monthly), dataframe(self.spending))


class ScenarioWire(Wire):
    baseline: ForecastWire
    forecast: ForecastWire
    config: ScenarioConfig
    deferred_events: list[ForecastEvent]

    @classmethod
    def pack(cls, value):
        return cls(baseline=ForecastWire.pack(value.baseline), forecast=ForecastWire.pack(value.forecast),
                   config=value.config, deferred_events=value.deferred_events)

    def unpack(self):
        return ScenarioResult(self.baseline.unpack(), self.forecast.unpack(), self.config, tuple(self.deferred_events))
