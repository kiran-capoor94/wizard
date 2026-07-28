class ConfigurationError(Exception):
    """Raised when wizard configuration is missing or invalid."""


class GraphitiUnavailable(Exception):
    """Raised when the shared Graphiti graph service is unreachable or errors."""
