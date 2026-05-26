"""Entry point for Render deployment."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))
from main import app

__all__ = ["app"]
