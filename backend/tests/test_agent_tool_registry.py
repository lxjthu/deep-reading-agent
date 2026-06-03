from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.agent_tool_registry import (  # noqa: E402
    TOOL_SCHEMAS,
    get_tool,
    list_tool_capabilities,
)


class AgentToolRegistryTests(unittest.TestCase):
    def test_registry_exposes_permission_metadata(self) -> None:
        search = get_tool("research_search")
        self.assertEqual(search.permission, "read_local")
        self.assertFalse(search.consent_required)
        self.assertFalse(search.proposal_required)
        self.assertFalse(search.writes_database)
        self.assertFalse(search.uses_internet)

        start_reading = get_tool("start_reading")
        self.assertEqual(start_reading.permission, "propose_write")
        self.assertTrue(start_reading.proposal_required)
        self.assertTrue(start_reading.writes_database)

    def test_openai_tool_schemas_include_research_tools(self) -> None:
        tool_names = {schema["function"]["name"] for schema in TOOL_SCHEMAS}
        self.assertIn("research_search", tool_names)
        self.assertIn("get_evidence_pack", tool_names)
        self.assertIn("get_source_windows", tool_names)
        self.assertIn("analyze_reading_candidates", tool_names)
        self.assertIn("filter_analysis_cache", tool_names)
        self.assertIn("search_cnki", tool_names)
        self.assertIn("lookup_english_fulltext", tool_names)

    def test_scan_tools_support_iterative_batch_offsets(self) -> None:
        scan_schema = get_tool("scan_input_folder").schema["properties"]
        self.assertEqual(scan_schema["max_files"]["maximum"], 500)
        self.assertIn("offset", scan_schema)
        self.assertEqual(scan_schema["offset"]["minimum"], 0)

        import_schema = get_tool("import_folder_and_start_reading").schema["properties"]
        self.assertEqual(import_schema["max_files"]["maximum"], 500)
        self.assertIn("offset", import_schema)

    def test_external_tools_are_marked_as_internet_reads(self) -> None:
        cnki = get_tool("search_cnki")
        self.assertEqual(cnki.permission, "external_read")
        self.assertTrue(cnki.consent_required)
        self.assertTrue(cnki.uses_internet)
        self.assertFalse(cnki.writes_database)

        fulltext = get_tool("lookup_english_fulltext")
        self.assertEqual(fulltext.permission, "external_read")
        self.assertTrue(fulltext.consent_required)
        self.assertTrue(fulltext.uses_internet)
        self.assertFalse(fulltext.writes_database)

    def test_capability_matrix_is_serializable(self) -> None:
        matrix = list_tool_capabilities()
        names = {item["name"] for item in matrix}
        self.assertIn("search_library", names)
        self.assertIn("research_search", names)
        self.assertTrue(all("handler" not in item for item in matrix))


if __name__ == "__main__":
    unittest.main()
