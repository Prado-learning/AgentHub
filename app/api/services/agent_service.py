"""Compatibility module; persistence is owned by infrastructure."""

import sys
from agenthub.infrastructure.persistence import custom_agents

sys.modules[__name__] = custom_agents
