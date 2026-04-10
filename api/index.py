"""Vercel serverless entry point — exposes the Flask app as a WSGI handler."""

import sys
import os

# Add project root to path so imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app
