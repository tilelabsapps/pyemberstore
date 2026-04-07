class PyemberStoreError(Exception):
    """Base error type for pyemberstore."""


class DocumentNotFoundError(PyemberStoreError):
    """Raised when an operation requires an existing document."""
