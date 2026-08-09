class SharedDataError(Exception):
    """Base error for shared data operations."""


class DataValidationError(SharedDataError):
    pass


class DataLockError(SharedDataError):
    pass


class ManifestError(SharedDataError):
    pass

