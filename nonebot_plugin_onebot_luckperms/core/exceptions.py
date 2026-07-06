class PermissionException(Exception):
    """Base exception for the luckperms permission system."""


class CircularInheritanceError(PermissionException):
    """Raised when circular group inheritance is detected."""
