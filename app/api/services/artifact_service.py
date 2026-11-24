"""Compatibility alias; implementation belongs to infrastructure."""

import sys
from agenthub.infrastructure.persistence import artifacts

sys.modules[__name__] = artifacts
