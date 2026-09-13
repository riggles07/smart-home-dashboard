"""
Test suite for Smart Home Dashboard Node-RED flows
"""
import os
import sys
import json
import asyncio
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import pytest

# Add the app directory to the path (Python modules)
sys.path.insert(0, str(Path(__file__).parent.parent / 'app'))

# Add the flows directory for Node-RED JS flows
sys.path.insert(0, str(Path(__file__).parent.parent / 'flows'))

# Test configuration
TEST_CONFIG = {
    'url': 'http://localhost:8080',
    'apiKey': 'test-api-key',
    'username': 'testuser',
    'password': 'testpass'
}

# Mock Node-RED context
class MockRED:
    def __init__(self):
        self.nodes = {}
        self.types = {}
        self.httpIn = Mock()
        self.httpOut = Mock()
        self.httpRequest = Mock()
        self.status = Mock()

    def addType(self, node_type, config):
        self.types[node_type] = config

    def registerType(self, node_type, node_class):
        self.nodes[node_type] = node_class
