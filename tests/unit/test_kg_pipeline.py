import os
os.environ.setdefault("OPENAI_API_KEY", "sk-test-placeholder")

import pytest
import json
from unittest.mock import MagicMock, patch, mock_open
from src.agents.kg_pipeline import (
    load_ontology, parse_dsl, validate_dsl, build_ast,
    compile_cypher, serialise_records, generate_answer,
    run_graph_search, QueryAST,
)
from src.repository.knowledge_graph import KnowledgeGraphRepository
from src.utils.exception import AppException


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def sample_schema():
    return {
        "labels": {"Deal", "SalesRep", "Account", "Quarter"},
        "relationships": {"MANAGED_BY", "FOR_ACCOUNT", "IN_QUARTER"},
        "properties": {
            "Deal": {"deal_id", "name", "value", "status"},
            "SalesRep": {"name", "region", "quota", "performance_score"},
            "Account": {"name", "tier", "annual_revenue"},
            "Quarter": {"name", "year", "quarter", "total_revenue"},
        },
    }


@pytest.fixture()
def simple_dsl():
    return {
        "match": [{"label": "Deal", "alias": "d"}],
        "traversals": [{"rel": "MANAGED_BY", "to_label": "SalesRep", "to_alias": "s"}],
        "where": [{"field": "d.status", "op": "=", "value": "Won"}],
        "return": ["d.name", "d.value", "s.name"],
    }


@pytest.fixture()
def simple_ast():
    return QueryAST(
        anchor_label="Deal",
        anchor_alias="d",
        traversals=[{"rel": "MANAGED_BY", "to_label": "SalesRep", "to_alias": "s"}],
        filters=[{"field": "d.status", "op": "=", "value": "Won"}],
        return_fields=["d.name", "d.value", "s.name"],
    )


# ---------------------------------------------------------------------------
# OL — Ontology Loading
# ---------------------------------------------------------------------------

class TestOntologyLoading:
    def test_OL01_returns_tuple_of_str_and_dict(self):
        text, schema = load_ontology()
        assert type(text) == str
        assert type(schema) == dict

    def test_OL02_text_is_non_empty(self):
        text, _ = load_ontology()
        assert len(text) > 0

    def test_OL03_schema_has_labels_key(self):
        _, schema = load_ontology()
        assert "labels" in schema

    def test_OL04_schema_has_relationships_key(self):
        _, schema = load_ontology()
        assert "relationships" in schema

    def test_OL05_schema_has_properties_key(self):
        _, schema = load_ontology()
        assert "properties" in schema

    def test_OL06_labels_contains_known_node_labels(self):
        _, schema = load_ontology()
        assert "Deal" in schema["labels"]
        assert "SalesRep" in schema["labels"]
        assert "Employee" in schema["labels"]

    def test_OL07_relationships_contains_known_rel_types(self):
        _, schema = load_ontology()
        assert "MANAGED_BY" in schema["relationships"]
        assert "HAS_SKILL" in schema["relationships"]

    def test_OL08_deal_properties_complete(self):
        _, schema = load_ontology()
        assert {"deal_id", "name", "value", "status"}.issubset(schema["properties"]["Deal"])

    def test_OL09_salesrep_properties_present(self):
        _, schema = load_ontology()
        assert {"name", "region", "quota"}.issubset(schema["properties"]["SalesRep"])

    def test_OL10_missing_file_raises_app_exception_500(self):
        with patch("pathlib.Path.open", side_effect=FileNotFoundError):
            with pytest.raises(AppException) as exc:
                load_ontology()
        assert exc.value.status_code == 500


# ---------------------------------------------------------------------------
# SP — Semantic Parser
# ---------------------------------------------------------------------------

class TestSemanticParser:
    _valid_dsl = {
        "match": [{"label": "Deal", "alias": "d"}],
        "traversals": [],
        "where": [],
        "return": ["d.name"],
    }

    def _mock_llm(self, content: str):
        mock = MagicMock()
        mock.invoke.return_value.content = content
        return mock

    def test_SP01_returns_dict_on_valid_json(self):
        with patch("src.agents.kg_pipeline._llm", self._mock_llm(json.dumps(self._valid_dsl))):
            result = parse_dsl("Who are the top deals?", "ontology")
        assert isinstance(result, dict)

    def test_SP02_result_has_all_required_dsl_keys(self):
        with patch("src.agents.kg_pipeline._llm", self._mock_llm(json.dumps(self._valid_dsl))):
            result = parse_dsl("Who are the top deals?", "ontology")
        for key in ("match", "traversals", "where", "return"):
            assert key in result

    def test_SP03_passes_question_in_prompt(self):
        mock_llm = self._mock_llm(json.dumps(self._valid_dsl))
        question = "What deals were won in Q1?"
        with patch("src.agents.kg_pipeline._llm", mock_llm):
            parse_dsl(question, "ontology")
        call_arg = mock_llm.invoke.call_args[0][0]
        assert question in call_arg

    def test_SP04_passes_ontology_text_in_prompt(self):
        mock_llm = self._mock_llm(json.dumps(self._valid_dsl))
        ontology_snippet = "Deal: deal_id:STRING!"
        with patch("src.agents.kg_pipeline._llm", mock_llm):
            parse_dsl("query", ontology_snippet)
        call_arg = mock_llm.invoke.call_args[0][0]
        assert ontology_snippet in call_arg

    def test_SP05_invalid_json_raises_app_exception_500(self):
        with patch("src.agents.kg_pipeline._llm", self._mock_llm("not valid json {{{")):
            with pytest.raises(AppException) as exc:
                parse_dsl("query", "ontology")
        assert exc.value.status_code == 500

    def test_SP06_non_dict_json_raises_app_exception_500(self):
        with patch("src.agents.kg_pipeline._llm", self._mock_llm("[1, 2, 3]")):
            with pytest.raises(AppException) as exc:
                parse_dsl("query", "ontology")
        assert exc.value.status_code == 500

    def test_SP07_llm_called_exactly_once(self):
        mock_llm = self._mock_llm(json.dumps(self._valid_dsl))
        with patch("src.agents.kg_pipeline._llm", mock_llm):
            parse_dsl("query", "ontology")
        assert mock_llm.invoke.call_count == 1


# ---------------------------------------------------------------------------
# OV — Ontology Validator
# ---------------------------------------------------------------------------

class TestOntologyValidator:
    def test_OV01_valid_dsl_passes(self, simple_dsl, sample_schema):
        validate_dsl(simple_dsl, sample_schema)  # no exception

    def test_OV02_unknown_match_label_raises_400(self, simple_dsl, sample_schema):
        simple_dsl["match"] = [{"label": "Unknown", "alias": "x"}]
        with pytest.raises(AppException) as exc:
            validate_dsl(simple_dsl, sample_schema)
        assert exc.value.status_code == 400
        assert "Unknown" in exc.value.message

    def test_OV03_unknown_traversal_to_label_raises_400(self, simple_dsl, sample_schema):
        simple_dsl["traversals"] = [{"rel": "MANAGED_BY", "to_label": "Ghost", "to_alias": "g"}]
        with pytest.raises(AppException) as exc:
            validate_dsl(simple_dsl, sample_schema)
        assert exc.value.status_code == 400
        assert "Ghost" in exc.value.message

    def test_OV04_unknown_relationship_raises_400(self, simple_dsl, sample_schema):
        simple_dsl["traversals"] = [{"rel": "FAKE_REL", "to_label": "SalesRep", "to_alias": "s"}]
        with pytest.raises(AppException) as exc:
            validate_dsl(simple_dsl, sample_schema)
        assert exc.value.status_code == 400
        assert "FAKE_REL" in exc.value.message

    def test_OV05_unknown_property_in_filter_raises_400(self, simple_dsl, sample_schema):
        simple_dsl["where"] = [{"field": "d.phantom", "op": "=", "value": "x"}]
        with pytest.raises(AppException) as exc:
            validate_dsl(simple_dsl, sample_schema)
        assert exc.value.status_code == 400
        assert "phantom" in exc.value.message

    def test_OV06_empty_traversals_is_valid(self, simple_dsl, sample_schema):
        simple_dsl["traversals"] = []
        validate_dsl(simple_dsl, sample_schema)  # no exception

    def test_OV07_empty_where_is_valid(self, simple_dsl, sample_schema):
        simple_dsl["where"] = []
        validate_dsl(simple_dsl, sample_schema)  # no exception

    def test_OV08_multiple_valid_traversals_passes(self, sample_schema):
        dsl = {
            "match": [{"label": "Deal", "alias": "d"}],
            "traversals": [
                {"rel": "MANAGED_BY", "to_label": "SalesRep", "to_alias": "s"},
                {"rel": "FOR_ACCOUNT", "to_label": "Account", "to_alias": "a"},
            ],
            "where": [],
            "return": ["d.name"],
        }
        validate_dsl(dsl, sample_schema)  # no exception

    def test_OV09_first_invalid_term_raises_single_exception(self, sample_schema):
        dsl = {
            "match": [{"label": "BadLabel1", "alias": "x"}],
            "traversals": [{"rel": "BAD_REL", "to_label": "BadLabel2", "to_alias": "y"}],
            "where": [],
            "return": ["x.name"],
        }
        raised = []
        try:
            validate_dsl(dsl, sample_schema)
        except AppException as e:
            raised.append(e)
        assert len(raised) == 1

    def test_OV10_alias_from_traversal_resolves_property(self, sample_schema):
        dsl = {
            "match": [{"label": "Deal", "alias": "d"}],
            "traversals": [{"rel": "MANAGED_BY", "to_label": "SalesRep", "to_alias": "s"}],
            "where": [{"field": "s.name", "op": "=", "value": "Alice"}],
            "return": ["d.name"],
        }
        validate_dsl(dsl, sample_schema)  # no exception — "name" belongs to SalesRep


# ---------------------------------------------------------------------------
# QP — Query Planner / AST Builder
# ---------------------------------------------------------------------------

class TestQueryPlanner:
    def test_QP01_returns_query_ast(self, simple_dsl):
        result = build_ast(simple_dsl)
        assert isinstance(result, QueryAST)

    def test_QP02_anchor_label_from_first_match(self, simple_dsl):
        result = build_ast(simple_dsl)
        assert result.anchor_label == "Deal"

    def test_QP03_anchor_alias_from_first_match(self, simple_dsl):
        result = build_ast(simple_dsl)
        assert result.anchor_alias == "d"

    def test_QP04_traversals_match_dsl(self, simple_dsl):
        result = build_ast(simple_dsl)
        assert len(result.traversals) == 1
        assert result.traversals[0]["rel"] == "MANAGED_BY"

    def test_QP05_filters_match_dsl_where(self, simple_dsl):
        result = build_ast(simple_dsl)
        assert len(result.filters) == 1
        assert result.filters[0]["value"] == "Won"

    def test_QP06_return_fields_match_dsl(self, simple_dsl):
        result = build_ast(simple_dsl)
        assert result.return_fields == ["d.name", "d.value", "s.name"]

    def test_QP07_empty_traversals_produces_empty_list(self, simple_dsl):
        simple_dsl["traversals"] = []
        result = build_ast(simple_dsl)
        assert result.traversals == []

    def test_QP08_empty_where_produces_empty_filters(self, simple_dsl):
        simple_dsl["where"] = []
        result = build_ast(simple_dsl)
        assert result.filters == []

    def test_QP09_multiple_traversals_all_captured(self):
        dsl = {
            "match": [{"label": "Deal", "alias": "d"}],
            "traversals": [
                {"rel": "MANAGED_BY", "to_label": "SalesRep", "to_alias": "s"},
                {"rel": "FOR_ACCOUNT", "to_label": "Account", "to_alias": "a"},
            ],
            "where": [],
            "return": ["d.name"],
        }
        result = build_ast(dsl)
        assert len(result.traversals) == 2


# ---------------------------------------------------------------------------
# CC — Cypher Compiler
# ---------------------------------------------------------------------------

class TestCypherCompiler:
    def test_CC01_returns_tuple_of_str_and_dict(self, simple_ast):
        cypher, params = compile_cypher(simple_ast)
        assert isinstance(cypher, str)
        assert isinstance(params, dict)

    def test_CC02_match_includes_anchor_node(self, simple_ast):
        cypher, _ = compile_cypher(simple_ast)
        assert "MATCH (d:Deal)" in cypher

    def test_CC03_match_includes_relationship_pattern(self, simple_ast):
        cypher, _ = compile_cypher(simple_ast)
        assert "[:MANAGED_BY]" in cypher
        assert "(s:SalesRep)" in cypher

    def test_CC04_where_present_when_filters_exist(self, simple_ast):
        cypher, _ = compile_cypher(simple_ast)
        assert "WHERE" in cypher

    def test_CC05_where_absent_when_no_filters(self):
        ast = QueryAST("Deal", "d", [], [], ["d.name"])
        cypher, _ = compile_cypher(ast)
        assert "WHERE" not in cypher

    def test_CC06_filter_value_parameterised(self, simple_ast):
        cypher, params = compile_cypher(simple_ast)
        assert "$p0" in cypher
        assert params["p0"] == "Won"

    def test_CC07_multiple_filters_use_sequential_keys(self):
        ast = QueryAST(
            "Deal", "d", [],
            [
                {"field": "d.status", "op": "=", "value": "Won"},
                {"field": "d.value", "op": ">", "value": 50000},
            ],
            ["d.name"],
        )
        cypher, params = compile_cypher(ast)
        assert "$p0" in cypher
        assert "$p1" in cypher
        assert "p0" in params
        assert "p1" in params

    def test_CC08_return_includes_all_fields(self, simple_ast):
        cypher, _ = compile_cypher(simple_ast)
        assert "RETURN d.name, d.value, s.name" in cypher

    def test_CC09_no_traversals_produces_single_node_match(self):
        ast = QueryAST("Deal", "d", [], [], ["d.name"])
        cypher, _ = compile_cypher(ast)
        assert "MATCH (d:Deal)" in cypher
        assert "-[" not in cypher

    def test_CC10_gt_operator_used_correctly(self):
        ast = QueryAST(
            "Deal", "d", [],
            [{"field": "d.value", "op": ">", "value": 50000}],
            ["d.value"],
        )
        cypher, _ = compile_cypher(ast)
        assert "d.value > $p0" in cypher

    def test_CC11_user_value_not_in_cypher_string(self, simple_ast):
        cypher, _ = compile_cypher(simple_ast)
        assert "Won" not in cypher


# ---------------------------------------------------------------------------
# RQ — Repository run_query
# ---------------------------------------------------------------------------

class TestRunQuery:
    def _make_mock_session(self, records_data: list[dict]):
        mock_records = []
        for data in records_data:
            rec = MagicMock()
            rec.data.return_value = data
            mock_records.append(rec)

        mock_session = MagicMock()
        mock_session.run.return_value = mock_records

        mock_ctx = MagicMock()
        mock_ctx.__enter__.return_value = mock_session
        mock_ctx.__exit__.return_value = False
        return mock_ctx, mock_session

    def test_RQ01_returns_list(self):
        mock_ctx, _ = self._make_mock_session([{"name": "A"}, {"name": "B"}])
        with patch("src.repository.knowledge_graph.Neo4jConnection") as mock_neo4j:
            mock_neo4j.get_session.return_value = mock_ctx
            result = KnowledgeGraphRepository().run_query("MATCH (n) RETURN n", {})
        assert isinstance(result, list)

    def test_RQ02_each_item_is_dict(self):
        mock_ctx, _ = self._make_mock_session([{"name": "Alice"}, {"name": "Bob"}])
        with patch("src.repository.knowledge_graph.Neo4jConnection") as mock_neo4j:
            mock_neo4j.get_session.return_value = mock_ctx
            result = KnowledgeGraphRepository().run_query("MATCH (n) RETURN n", {})
        assert all(isinstance(r, dict) for r in result)

    def test_RQ03_returns_all_records(self):
        mock_ctx, _ = self._make_mock_session([{"name": "A"}, {"name": "B"}, {"name": "C"}])
        with patch("src.repository.knowledge_graph.Neo4jConnection") as mock_neo4j:
            mock_neo4j.get_session.return_value = mock_ctx
            result = KnowledgeGraphRepository().run_query("MATCH (n) RETURN n", {})
        assert len(result) == 3

    def test_RQ04_returns_empty_list_when_no_records(self):
        mock_ctx, _ = self._make_mock_session([])
        with patch("src.repository.knowledge_graph.Neo4jConnection") as mock_neo4j:
            mock_neo4j.get_session.return_value = mock_ctx
            result = KnowledgeGraphRepository().run_query("MATCH (n) RETURN n", {})
        assert result == []

    def test_RQ05_passes_cypher_to_session_run(self):
        cypher = "MATCH (d:Deal) RETURN d.name"
        mock_ctx, mock_session = self._make_mock_session([])
        with patch("src.repository.knowledge_graph.Neo4jConnection") as mock_neo4j:
            mock_neo4j.get_session.return_value = mock_ctx
            KnowledgeGraphRepository().run_query(cypher, {})
        mock_session.run.assert_called_once_with(cypher)

    def test_RQ06_passes_params_as_kwargs(self):
        cypher = "MATCH (d:Deal) WHERE d.status = $p0 RETURN d.name"
        params = {"p0": "Won"}
        mock_ctx, mock_session = self._make_mock_session([])
        with patch("src.repository.knowledge_graph.Neo4jConnection") as mock_neo4j:
            mock_neo4j.get_session.return_value = mock_ctx
            KnowledgeGraphRepository().run_query(cypher, params)
        mock_session.run.assert_called_once_with(cypher, p0="Won")

    def test_RQ07_uses_context_manager(self):
        mock_ctx, _ = self._make_mock_session([])
        with patch("src.repository.knowledge_graph.Neo4jConnection") as mock_neo4j:
            mock_neo4j.get_session.return_value = mock_ctx
            KnowledgeGraphRepository().run_query("MATCH (n) RETURN n", {})
        mock_ctx.__enter__.assert_called()


# ---------------------------------------------------------------------------
# GA — Answer Generator
# ---------------------------------------------------------------------------

class TestAnswerGenerator:
    def _mock_llm(self, content: str):
        mock = MagicMock()
        mock.invoke.return_value.content = content
        return mock

    def test_GA01_returns_non_empty_string(self):
        with patch("src.agents.kg_pipeline._llm", self._mock_llm("The top rep is Alice.")):
            result = generate_answer("Who is the top rep?", "records...")
        assert result == "The top rep is Alice."

    def test_GA02_question_appears_in_prompt(self):
        question = "Who closed the most deals?"
        mock_llm = self._mock_llm("answer")
        with patch("src.agents.kg_pipeline._llm", mock_llm):
            generate_answer(question, "data")
        call_arg = mock_llm.invoke.call_args[0][0]
        assert question in call_arg

    def test_GA03_raw_result_appears_in_prompt(self):
        raw_result = "...records from neo4j..."
        mock_llm = self._mock_llm("answer")
        with patch("src.agents.kg_pipeline._llm", mock_llm):
            generate_answer("question", raw_result)
        call_arg = mock_llm.invoke.call_args[0][0]
        assert raw_result in call_arg

    def test_GA04_llm_called_exactly_once(self):
        mock_llm = self._mock_llm("answer")
        with patch("src.agents.kg_pipeline._llm", mock_llm):
            generate_answer("question", "data")
        assert mock_llm.invoke.call_count == 1

    def test_GA05_empty_raw_result_no_error(self):
        mock_llm = self._mock_llm("No data was found.")
        with patch("src.agents.kg_pipeline._llm", mock_llm):
            generate_answer("question", "No results found.")
        assert mock_llm.invoke.call_count == 1


# ---------------------------------------------------------------------------
# SR — Serialise Records
# ---------------------------------------------------------------------------

class TestSerialiseRecords:
    def test_SR01_non_empty_returns_non_empty_string(self):
        result = serialise_records([{"name": "Alice", "value": 100}])
        assert isinstance(result, str) and len(result) > 0

    def test_SR02_empty_list_returns_no_results_message(self):
        result = serialise_records([])
        assert result == "No results found."

    def test_SR03_result_contains_record_data(self):
        result = serialise_records([{"name": "Alice"}])
        assert "Alice" in result

    def test_SR04_multiple_records_all_represented(self):
        result = serialise_records([{"name": "Alice"}, {"name": "Bob"}])
        assert "Alice" in result
        assert "Bob" in result


# ---------------------------------------------------------------------------
# GS — Graph Search End-to-End
# ---------------------------------------------------------------------------

class TestGraphSearch:
    _sample_dsl = {
        "match": [{"label": "Deal", "alias": "d"}],
        "traversals": [],
        "where": [],
        "return": ["d.name"],
    }
    _sample_ast = QueryAST("Deal", "d", [], [], ["d.name"])
    _sample_cypher = "MATCH (d:Deal)\nRETURN d.name"
    _sample_params: dict = {}
    _sample_records = [{"d.name": "Alpha Deal"}]
    _sample_raw = '[{"d.name": "Alpha Deal"}]'
    _sample_answer = "Alice led Won deals."
    _ontology_text = "sample ontology"
    _sample_schema = {
        "labels": {"Deal"},
        "relationships": set(),
        "properties": {"Deal": {"name"}},
    }

    def _patch_all(self):
        return (
            patch("src.agents.kg_pipeline.load_ontology", return_value=(self._ontology_text, self._sample_schema)),
            patch("src.agents.kg_pipeline.parse_dsl", return_value=self._sample_dsl),
            patch("src.agents.kg_pipeline.validate_dsl", return_value=None),
            patch("src.agents.kg_pipeline.build_ast", return_value=self._sample_ast),
            patch("src.agents.kg_pipeline.compile_cypher", return_value=(self._sample_cypher, self._sample_params)),
            patch("src.agents.kg_pipeline._repo") ,
            patch("src.agents.kg_pipeline.serialise_records", return_value=self._sample_raw),
            patch("src.agents.kg_pipeline.generate_answer", return_value=self._sample_answer),
        )

    def test_GS01_returns_answer_string(self):
        patches = self._patch_all()
        with patches[0], patches[1], patches[2], patches[3], patches[4], \
             patches[5] as mock_repo, patches[6], patches[7]:
            mock_repo.run_query.return_value = self._sample_records
            result = run_graph_search("Who won deals?")
        assert result == self._sample_answer

    def test_GS02_load_ontology_called_once(self):
        patches = self._patch_all()
        with patches[0] as mock_lo, patches[1], patches[2], patches[3], patches[4], \
             patches[5] as mock_repo, patches[6], patches[7]:
            mock_repo.run_query.return_value = self._sample_records
            run_graph_search("query")
        mock_lo.assert_called_once()

    def test_GS03_parse_dsl_receives_question_and_ontology(self):
        patches = self._patch_all()
        with patches[0], patches[1] as mock_pd, patches[2], patches[3], patches[4], \
             patches[5] as mock_repo, patches[6], patches[7]:
            mock_repo.run_query.return_value = self._sample_records
            run_graph_search("Who won deals?")
        mock_pd.assert_called_once_with("Who won deals?", self._ontology_text)

    def test_GS04_validate_dsl_called_with_dsl_and_schema(self):
        patches = self._patch_all()
        with patches[0], patches[1], patches[2] as mock_vd, patches[3], patches[4], \
             patches[5] as mock_repo, patches[6], patches[7]:
            mock_repo.run_query.return_value = self._sample_records
            run_graph_search("query")
        mock_vd.assert_called_once_with(self._sample_dsl, self._sample_schema)

    def test_GS05_build_ast_called_with_dsl(self):
        patches = self._patch_all()
        with patches[0], patches[1], patches[2], patches[3] as mock_ba, patches[4], \
             patches[5] as mock_repo, patches[6], patches[7]:
            mock_repo.run_query.return_value = self._sample_records
            run_graph_search("query")
        mock_ba.assert_called_once_with(self._sample_dsl)

    def test_GS06_compile_cypher_called_with_ast(self):
        patches = self._patch_all()
        with patches[0], patches[1], patches[2], patches[3], patches[4] as mock_cc, \
             patches[5] as mock_repo, patches[6], patches[7]:
            mock_repo.run_query.return_value = self._sample_records
            run_graph_search("query")
        mock_cc.assert_called_once_with(self._sample_ast)

    def test_GS07_run_query_called_with_cypher_and_params(self):
        patches = self._patch_all()
        with patches[0], patches[1], patches[2], patches[3], patches[4], \
             patches[5] as mock_repo, patches[6], patches[7]:
            mock_repo.run_query.return_value = self._sample_records
            run_graph_search("query")
        mock_repo.run_query.assert_called_once_with(self._sample_cypher, self._sample_params)

    def test_GS08_generate_answer_receives_question_and_serialised(self):
        patches = self._patch_all()
        with patches[0], patches[1], patches[2], patches[3], patches[4], \
             patches[5] as mock_repo, patches[6], patches[7] as mock_ga:
            mock_repo.run_query.return_value = self._sample_records
            run_graph_search("Who won deals?")
        mock_ga.assert_called_once_with("Who won deals?", self._sample_raw)

    def test_GS09_app_exception_from_validate_propagates(self):
        patches = self._patch_all()
        with patches[0], patches[1], patches[2] as mock_vd, patches[3], patches[4], \
             patches[5] as mock_repo, patches[6], patches[7]:
            mock_repo.run_query.return_value = self._sample_records
            mock_vd.side_effect = AppException("bad label", 400)
            with pytest.raises(AppException) as exc:
                run_graph_search("query")
        assert exc.value.status_code == 400

    def test_GS10_app_exception_from_parse_dsl_propagates(self):
        patches = self._patch_all()
        with patches[0], patches[1] as mock_pd, patches[2], patches[3], patches[4], \
             patches[5] as mock_repo, patches[6], patches[7]:
            mock_repo.run_query.return_value = self._sample_records
            mock_pd.side_effect = AppException("parse failed", 500)
            with pytest.raises(AppException) as exc:
                run_graph_search("query")
        assert exc.value.status_code == 500

    def test_GS11_unexpected_exception_becomes_app_exception_500(self):
        patches = self._patch_all()
        with patches[0], patches[1], patches[2], patches[3], patches[4], \
             patches[5] as mock_repo, patches[6], patches[7]:
            mock_repo.run_query.side_effect = RuntimeError("neo4j down")
            with pytest.raises(AppException) as exc:
                run_graph_search("query")
        assert exc.value.status_code == 500

    def test_GS12_empty_neo4j_result_uses_no_results_raw(self):
        patches = self._patch_all()
        with patches[0], patches[1], patches[2], patches[3], patches[4], \
             patches[5] as mock_repo, patches[6] as mock_sr, patches[7] as mock_ga:
            mock_repo.run_query.return_value = []
            mock_sr.return_value = "No results found."
            mock_ga.return_value = "Nothing was found."
            run_graph_search("query")
        mock_ga.assert_called_once_with("query", "No results found.")
