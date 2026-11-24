"""Compatibility alias; implementation belongs to infrastructure."""

import sys
from agenthub.infrastructure.persistence import attachments

sys.modules[__name__] = attachments
