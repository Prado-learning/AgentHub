"""Compatibility alias; implementation belongs to infrastructure."""

import sys
from agenthub.infrastructure.persistence import patches

sys.modules[__name__] = patches
