# Isolated conftest for wallet/billing tests (no global DB fixtures needed for billing math tests)
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
