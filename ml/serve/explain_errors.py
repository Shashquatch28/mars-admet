"""Why an explanation could not be given. No dependencies, so the API can map them to status codes
in an environment that does not have the ml stack."""


class ExplainUnavailable(RuntimeError):
    """The model that serves this endpoint cannot explain it right now."""


class ExplainBusy(ExplainUnavailable):
    """The KERMT explanation queue is full (ADR-035): try again later."""


class ExplainJobLost(RuntimeError):
    """The service no longer knows this explanation job (it restarted, or the job aged out): start it again."""


class NothingToExplain(RuntimeError):
    """No promoted model serves this endpoint (it is stub-served): there is no model to explain."""
