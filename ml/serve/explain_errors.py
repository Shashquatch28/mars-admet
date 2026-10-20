"""Why an explanation could not be given. No dependencies, so the API can map them to status codes
in an environment that does not have the ml stack."""


class ExplainUnavailable(RuntimeError):
    """The model that serves this endpoint cannot explain it right now."""


class NothingToExplain(RuntimeError):
    """No promoted model serves this endpoint (it is stub-served): there is no model to explain."""
