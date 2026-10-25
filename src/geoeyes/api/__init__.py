"""Web app back end (``geoeyes serve``): a thin JSON API over the workspace, the controller and the products."""
from geoeyes.api.app import DEFAULT_PORT, create_app, serve

__all__ = ["DEFAULT_PORT", "create_app", "serve"]
