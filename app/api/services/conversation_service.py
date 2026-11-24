"""Compatibility alias; implementation belongs to infrastructure."""

import sys
from agenthub.infrastructure.persistence import conversations

sys.modules[__name__] = conversations
