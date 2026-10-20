"""UI-independent session-bound API adapter; never silently mix backend modes."""

from config import TRANSACTION_COLUMNS
from src.api_client import ApiClient, ApiClientError


class DashboardBackend:
    def __init__(self, settings, *, client=None, session_id=None):
        self.settings, self.client, self.session_id = settings, client, session_id

    def call(self, operation, payload):
        if self.client is not None:
            return self.client.call(operation, payload).value
        with ApiClient(self.settings.api_url, timeout_seconds=self.settings.client_timeout_seconds,
                       max_retries=self.settings.client_max_retries, allowed_hosts=self.settings.api_allowed_hosts,
                       allow_private_http=self.settings.private_api_http, token=self.settings.api_token,
                       session_id=self.session_id) as client:
            return client.call(operation, payload).value

    def import_csv(self, raw, remove_duplicates=False):
        if len(raw) > self.settings.max_request_bytes:
            raise ApiClientError("request_too_large")
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeError:
            raise ApiClientError("invalid_request") from None
        return self.call("import_csv", {"csv_text": text, "remove_ambiguous_duplicates": remove_duplicates}).unpack()

    def payload(self, imported, opening, *, as_of, threshold, irregular, reviewed, engine, currency="USD"):
        from src.data_processing import Transaction
        return dict(transactions=[Transaction(**{name: row[name] for name in TRANSACTION_COLUMNS}).model_dump(mode="json")
                                  for row in imported.data.to_dict("records")], opening_balance=str(opening),
                    as_of=as_of, cash_threshold=str(threshold), include_irregular_income=irregular,
                    reviewed_duplicates=reviewed, anomaly_engine=engine, currency=currency)

    def dashboard(self, payload):
        return self.call("dashboard", payload).unpack()

    def anomalies(self, imported, *, as_of, engine, currency, reviewed=False):
        from api.schemas.requests import HistoryRequest
        values = self.payload(imported, "0", as_of=as_of, threshold="0", irregular=False,
                              reviewed=reviewed, engine=engine, currency=currency)
        return self.call("dashboard_anomalies", {key: value for key, value in values.items()
                                                if key in HistoryRequest.model_fields}).unpack()

    def scenario(self, payload, config):
        return self.call("dashboard_scenario", {**payload, "scenario": config.model_dump(mode="json")}).unpack()

    def model_status(self, model, timeout=30):
        return self.call("model_status", {"model": model, "timeout_seconds": timeout})

    def insights(self, payload, model, timeout, *, scenario=None):
        from src.insight_workflow import InsightReport
        request = {**payload, "model": model, "timeout_seconds": timeout,
                   "scenario": scenario.config.model_dump(mode="json") if scenario else None}
        result = self.call("insights", request)
        return InsightReport(result.source, result.model, result.context_fingerprint, result.insights,
                             result.evidence, tuple(tuple(pair) for pair in result.fallback),
                             result.message, result.error_code)
