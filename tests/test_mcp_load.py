import sys
import os
import unittest
from unittest.mock import MagicMock

# Add backend to path so we can import the mcp module
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

class TestMCPLoad(unittest.TestCase):
    def setUp(self):
        # Mock dependencies that might not be installed in the test env
        sys.modules['vt'] = MagicMock()
        sys.modules['mcp'] = MagicMock()
        sys.modules['mcp.server'] = MagicMock()
        sys.modules['mcp.server.fastmcp'] = MagicMock()

    def tearDown(self):
        # Cleanup mocks
        if 'vt' in sys.modules: del sys.modules['vt']
        if 'mcp' in sys.modules: del sys.modules['mcp']

    def test_mcp_embedded_import(self):
        """
        Verifies that the Embedded MCP server code structure is correct.
        Mocks external dependencies (vt, mcp) to test locally without installation.
        """
        try:
            from backend.mcp.gti import server
            print(f"✅ Successfully imported MCP Server from {server.__file__}")
            
            # Verify it has the expected 'server' object
            assert hasattr(server, 'server'), "MCP Module missing 'server' object"
            assert hasattr(server, 'main'), "MCP Module missing 'main' entrypoint"
            
        except ImportError as e:
            self.fail(f"❌ Failed to import Embedded MCP: {e}")
        except Exception as e:
            self.fail(f"❌ Unexpected error loading MCP: {e}")

if __name__ == "__main__":
    unittest.main()
