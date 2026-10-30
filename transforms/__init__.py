"""Transform package.

Importing the module registers the @register_transform decorated function
with the SDK server.
"""

from . import alias_search  # noqa: F401

__all__ = ["alias_search"]
