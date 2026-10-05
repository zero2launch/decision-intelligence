from unittest.mock import MagicMock, patch

import pytest

from src.services.knowledge_graph import KGIngestResult, KnowledgeGraphService, MAX_EXTRACTION_CHARS
from src.utils.exception import AppException


@pytest.fixture()
def service(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    ontology_file = tmp_path / "ontology_context.md"
    ontology_file.write_text("## Schema\nDeal: deal_id:STRING!")
    with patch("src.services.knowledge_graph._ONTOLOGY_PATH", ontology_file):
        svc = KnowledgeGraphService.__new__(KnowledgeGraphService)
        svc._repo = MagicMock()
        svc._openai_api_key = "test-key"
        svc._openai_model = "gpt-4o-mini"
        svc._ontology = ontology_file.read_text()
        return svc


# --- _parse_llm_output ---

def test_parse_llm_output_valid(service):
    result = service._parse_llm_output('{"nodes": [], "relationships": []}', "f.pdf")
    assert result == {"nodes": [], "relationships": []}


def test_parse_llm_output_missing_relationships_key(service):
    result = service._parse_llm_output('{"nodes": []}', "f.pdf")
    assert result["relationships"] == []
    assert result["nodes"] == []


def test_parse_llm_output_invalid_json(service):
    with pytest.raises(AppException) as exc_info:
        service._parse_llm_output("not json", "f.pdf")
    assert exc_info.value.status_code == 500


def test_parse_llm_output_json_array(service):
    with pytest.raises(AppException) as exc_info:
        service._parse_llm_output("[]", "f.pdf")
    assert exc_info.value.status_code == 500


# --- _validate nodes ---

def test_validate_unknown_node_label(service):
    parsed = {"nodes": [{"label": "Unknown", "properties": {}}], "relationships": []}
    result = KGIngestResult()
    valid_nodes, valid_rels = service._validate(parsed, result)
    assert result.nodes_dropped == 1
    assert valid_nodes == []


def test_validate_missing_required_field(service):
    parsed = {
        "nodes": [{"label": "Deal", "properties": {"name": "x", "value": 100, "status": "Won"}}],
        "relationships": [],
    }
    result = KGIngestResult()
    valid_nodes, _ = service._validate(parsed, result)
    assert result.nodes_dropped == 1
    assert valid_nodes == []


def test_validate_invalid_enum_value(service):
    parsed = {
        "nodes": [{"label": "Deal", "properties": {"deal_id": "D1", "name": "x", "value": 100, "status": "Pending"}}],
        "relationships": [],
    }
    result = KGIngestResult()
    valid_nodes, _ = service._validate(parsed, result)
    assert result.nodes_dropped == 1
    assert valid_nodes == []


def test_validate_valid_node_passes(service):
    node = {"label": "Deal", "properties": {"deal_id": "D1", "name": "x", "value": 100, "status": "Won"}}
    parsed = {"nodes": [node], "relationships": []}
    result = KGIngestResult()
    valid_nodes, _ = service._validate(parsed, result)
    assert result.nodes_dropped == 0
    assert valid_nodes == [node]


# --- _validate relationships ---

def test_validate_invalid_relationship_triple(service):
    rel = {"from_label": "Deal", "from_value": "D1", "to_label": "Account", "to_value": "Acme", "type": "INVALID"}
    parsed = {"nodes": [], "relationships": [rel]}
    result = KGIngestResult()
    _, valid_rels = service._validate(parsed, result)
    assert result.relationships_dropped == 1
    assert valid_rels == []


def test_validate_relationship_missing_from_value(service):
    rel = {"from_label": "Deal", "to_label": "Account", "to_value": "ACC001", "type": "BELONGS_TO_ACCOUNT"}
    parsed = {"nodes": [], "relationships": [rel]}
    result = KGIngestResult()
    _, valid_rels = service._validate(parsed, result)
    assert result.relationships_dropped == 1
    assert valid_rels == []


def test_validate_valid_relationship_passes(service):
    rel = {"from_label": "Deal", "from_value": "D1", "to_label": "Account", "to_value": "ACC001", "type": "BELONGS_TO_ACCOUNT"}
    parsed = {"nodes": [], "relationships": [rel]}
    result = KGIngestResult()
    _, valid_rels = service._validate(parsed, result)
    assert result.relationships_dropped == 0
    assert valid_rels == [rel]


# --- _write_nodes ---

def test_write_nodes_created(service):
    service._repo.merge_node.return_value = True
    result = KGIngestResult()
    service._write_nodes(
        [{"label": "Deal", "properties": {"deal_id": "D1", "name": "x", "value": 100, "status": "Won"}}],
        result,
    )
    assert result.nodes_created == 1
    assert result.nodes_merged == 0


def test_write_nodes_merged(service):
    service._repo.merge_node.return_value = False
    result = KGIngestResult()
    service._write_nodes(
        [{"label": "Deal", "properties": {"deal_id": "D1", "name": "x", "value": 100, "status": "Won"}}],
        result,
    )
    assert result.nodes_merged == 1
    assert result.nodes_created == 0


def test_write_nodes_neo4j_error(service):
    service._repo.merge_node.side_effect = Exception("connection refused")
    result = KGIngestResult()
    with pytest.raises(AppException) as exc_info:
        service._write_nodes(
            [{"label": "Deal", "properties": {"deal_id": "D1", "name": "x", "value": 100, "status": "Won"}}],
            result,
        )
    assert exc_info.value.status_code == 500


# --- _write_relationships ---

def test_write_relationships_skipped(service):
    service._repo.relationship_exists.return_value = True
    result = KGIngestResult()
    service._write_relationships(
        [{"from_label": "Deal", "from_value": "D1", "to_label": "Account", "to_value": "ACC001", "type": "BELONGS_TO_ACCOUNT"}],
        result,
    )
    assert result.relationships_skipped == 1
    service._repo.create_relationship.assert_not_called()


def test_write_relationships_created(service):
    service._repo.relationship_exists.return_value = False
    result = KGIngestResult()
    service._write_relationships(
        [{"from_label": "Deal", "from_value": "D1", "to_label": "Account", "to_value": "ACC001", "type": "BELONGS_TO_ACCOUNT"}],
        result,
    )
    service._repo.create_relationship.assert_called_once()
    assert result.relationships_created == 1


def test_write_relationships_check_error(service):
    service._repo.relationship_exists.side_effect = Exception("timeout")
    result = KGIngestResult()
    with pytest.raises(AppException) as exc_info:
        service._write_relationships(
            [{"from_label": "Deal", "from_value": "D1", "to_label": "Account", "to_value": "ACC001", "type": "BELONGS_TO_ACCOUNT"}],
            result,
        )
    assert exc_info.value.status_code == 500


def test_write_relationships_create_error(service):
    service._repo.relationship_exists.return_value = False
    service._repo.create_relationship.side_effect = Exception("write failed")
    result = KGIngestResult()
    with pytest.raises(AppException) as exc_info:
        service._write_relationships(
            [{"from_label": "Deal", "from_value": "D1", "to_label": "Account", "to_value": "ACC001", "type": "BELONGS_TO_ACCOUNT"}],
            result,
        )
    assert exc_info.value.status_code == 500


# --- process_document ---

def test_process_document_happy_path(service):
    llm_response = (
        '{"nodes": ['
        '{"label": "Deal", "properties": {"deal_id": "D1", "name": "x", "value": 100, "status": "Won"}},'
        '{"label": "Account", "properties": {"account_id": "ACC001", "name": "Acme"}}'
        '], "relationships": ['
        '{"from_label": "Deal", "from_value": "D1", "to_label": "Account", "to_value": "ACC001", "type": "BELONGS_TO_ACCOUNT"}'
        ']}'
    )
    service._call_llm = MagicMock(return_value=llm_response)
    service._repo.merge_node.return_value = True
    service._repo.relationship_exists.return_value = False

    result = service.process_document("some text", "file.pdf")

    assert result.nodes_created == 2
    assert result.relationships_created == 1


def test_process_document_text_truncation(service):
    long_text = "x" * 60_000
    service._call_llm = MagicMock(return_value='{"nodes": [], "relationships": []}')
    service.process_document(long_text, "file.pdf")

    called_text = service._call_llm.call_args[0][0]
    assert len(called_text) == MAX_EXTRACTION_CHARS


def test_process_document_llm_failure_propagates(service):
    service._call_llm = MagicMock(side_effect=Exception("rate limit"))
    with pytest.raises(Exception, match="rate limit"):
        service.process_document("some text", "file.pdf")
