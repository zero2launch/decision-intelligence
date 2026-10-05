import os
import re
import json
import logging
from dataclasses import dataclass
from pathlib import Path

from langchain_openai import ChatOpenAI

from src.repository.knowledge_graph import KnowledgeGraphRepository
from src.utils.exception import AppException

logger = logging.getLogger(__name__)

_llm = ChatOpenAI(model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"))
_repo = KnowledgeGraphRepository()
_ONTOLOGY_PATH = Path(__file__).parent.parent.parent / "ontology" / "ontology_context.md"


@dataclass
class QueryAST:
    anchor_label: str
    anchor_alias: str
    traversals: list[dict]
    filters: list[dict]
    return_fields: list[str]


def _parse_ontology(text: str) -> dict:
    labels: set[str] = set()
    relationships: set[str] = set()
    properties: dict[str, set[str]] = {}
    in_nodes = False
    in_rels = False

    for line in text.splitlines():
        stripped = line.strip()

        if stripped.startswith("### Nodes"):
            in_nodes, in_rels = True, False
            continue
        if stripped.startswith("### Relationships"):
            in_nodes, in_rels = False, True
            continue
        if stripped.startswith("###"):
            in_nodes = in_rels = False
            continue
        if not stripped or stripped.startswith("#"):
            continue

        if in_nodes:
            colon_idx = stripped.find(":")
            if colon_idx == -1:
                continue
            label = stripped[:colon_idx].strip()
            if not label or not label[0].isupper():
                continue
            rest = stripped[colon_idx + 1:]
            props = set(re.findall(r"\b(\w+):[A-Z]+", rest))
            labels.add(label)
            properties[label] = props

        elif in_rels:
            m = re.search(r"\[:([A-Z_]+)\]", stripped)
            if m:
                relationships.add(m.group(1))

    return {"labels": labels, "relationships": relationships, "properties": properties}


def load_ontology() -> tuple[str, dict]:
    """Read ontology file; return (raw_text, schema_dict)."""
    try:
        with _ONTOLOGY_PATH.open(encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        raise AppException("Ontology file not found", 500)
    return text, _parse_ontology(text)


def parse_dsl(question: str, ontology_text: str) -> dict:
    """Call LLM with question + ontology; parse JSON response into DSL dict."""
    from datetime import date
    today = date.today()
    quarter_number = (today.month - 1) // 3 + 1
    prompt = (
        "You are a graph query DSL generator. Given a natural language question and a Neo4j schema ontology, "
        "output ONLY a valid JSON object (no markdown, no explanation) describing the query using the ontology terms.\n\n"
        f"## Current Date\nToday is {today.isoformat()}. The current quarter is Q{quarter_number} {today.year} "
        f"(year={today.year}, quarter_number={quarter_number}). Use these values when the question refers to "
        "'this quarter', 'current quarter', etc.\n\n"
        f"## Ontology\n{ontology_text}\n\n"
        f"## Question\n{question}\n\n"
        "## Output Format\n"
        'Return a single JSON object with these keys:\n'
        '- "match": list of {"label": str, "alias": str} — the anchor node(s) to start traversal from\n'
        '- "traversals": list of {"rel": str, "to_label": str, "to_alias": str, "direction": str} — '
        'each hop from the current chain tail. "direction" is "out" (default, follows arrow as shown in ontology) '
        'or "in" (reverse arrow). Example: to reach Deal from Project via LED_TO_PROJECT, use '
        '{"rel": "LED_TO_PROJECT", "to_label": "Deal", "to_alias": "d", "direction": "in"}.\n'
        '- "where": list of {"field": str, "op": str, "value": any} — filter conditions (op: =, >, <, >=, <=)\n'
        '- "return": list of str — dot-notation fields to return, e.g. "d.name". '
        'Aggregates are allowed, e.g. "COUNT(d)", "SUM(d.value)".\n\n'
        "## Critical Rules\n"
        "1. Every alias used in 'where' fields and 'return' MUST first be introduced in 'match' or 'traversals'. "
        "Never reference an alias that is not defined.\n"
        "2. To traverse against an arrow (e.g. from Project back to Deal via LED_TO_PROJECT), set "
        '"direction": "in" on that traversal step.\n'
        "3. Use only labels, relationship types, and properties that exist in the ontology above.\n"
        "4. If a field alias appears in 'where' or 'return' but not in 'match' or 'traversals', add the "
        "missing node as a traversal — do not leave aliases undefined."
    )
    response = _llm.invoke(prompt)
    try:
        result = json.loads(response.content)
    except (json.JSONDecodeError, ValueError):
        raise AppException("Failed to parse LLM DSL output", 500)
    if not isinstance(result, dict):
        raise AppException("Failed to parse LLM DSL output", 500)
    return result


def _extract_alias(field: str) -> str | None:
    """Return the alias from a dot-notation field, stripping any aggregate wrapper.
    Returns None if the field has no dot (e.g. bare 'COUNT(*)' or a plain label)."""
    inner = re.sub(r"^\w+\((.+)\)$", r"\1", field.strip())
    parts = inner.split(".", 1)
    return parts[0] if len(parts) == 2 else None


def validate_dsl(dsl: dict, schema: dict) -> None:
    """Validate DSL labels, rels, and properties against schema.
    Raises AppException(400) on first unknown term."""
    if not dsl.get("match"):
        raise AppException("DSL 'match' must contain at least one node", 400)

    alias_to_label: dict[str, str] = {}
    for entry in dsl.get("match", []):
        alias_to_label[entry["alias"]] = entry["label"]
    for trav in dsl.get("traversals", []):
        alias_to_label[trav["to_alias"]] = trav["to_label"]

    for entry in dsl.get("match", []):
        label = entry["label"]
        if label not in schema["labels"]:
            raise AppException(f"Unknown label: {label}", 400)

    for trav in dsl.get("traversals", []):
        to_label = trav["to_label"]
        if to_label not in schema["labels"]:
            raise AppException(f"Unknown label: {to_label}", 400)
        rel = trav["rel"]
        if rel not in schema["relationships"]:
            raise AppException(f"Unknown relationship: {rel}", 400)

    for f in dsl.get("where", []):
        parts = f["field"].split(".", 1)
        if len(parts) != 2:
            continue
        alias, prop = parts
        if alias not in alias_to_label:
            raise AppException(f"Undefined alias in WHERE clause: '{alias}'", 400)
        label = alias_to_label.get(alias)
        if label and prop not in schema["properties"].get(label, set()):
            raise AppException(f"Unknown property: {prop} on {label}", 400)

    for field in dsl.get("return", []):
        alias = _extract_alias(field)
        if alias is None:
            continue
        if alias not in alias_to_label:
            raise AppException(f"Undefined alias in RETURN clause: '{alias}'", 400)


def build_ast(dsl: dict) -> QueryAST:
    """Convert validated DSL dict into a QueryAST dataclass."""
    first = dsl["match"][0]
    return QueryAST(
        anchor_label=first["label"],
        anchor_alias=first["alias"],
        traversals=dsl.get("traversals", []),
        filters=dsl.get("where", []),
        return_fields=dsl["return"],
    )


def compile_cypher(ast: QueryAST) -> tuple[str, dict]:
    """Walk AST; emit parameterised Cypher string and params dict.
    No user-value string interpolation."""
    match_str = f"({ast.anchor_alias}:{ast.anchor_label})"
    for trav in ast.traversals:
        direction = trav.get("direction", "out")
        node = f"({trav['to_alias']}:{trav['to_label']})"
        rel = f"[:{trav['rel']}]"
        if direction == "in":
            match_str += f"<-{rel}-{node}"
        else:
            match_str += f"-{rel}->{node}"

    parts = [f"MATCH {match_str}"]
    params: dict = {}

    if ast.filters:
        conditions = []
        for i, f in enumerate(ast.filters):
            key = f"p{i}"
            params[key] = f["value"]
            conditions.append(f"{f['field']} {f['op']} ${key}")
        parts.append(f"WHERE {' AND '.join(conditions)}")

    parts.append(f"RETURN {', '.join(ast.return_fields)}")
    parts.append("LIMIT 100")
    return "\n".join(parts), params


def serialise_records(records: list[dict]) -> str:
    """Convert raw Neo4j records list to a compact JSON/text string."""
    if not records:
        return "No results found."
    return json.dumps(records, ensure_ascii=False, default=str)


def generate_answer(question: str, raw_result: str) -> str:
    """Call LLM with question + raw_result; return natural-language answer."""
    prompt = (
        "You are an expert business analyst. Answer the user's question using only the data provided.\n\n"
        f"## Question\n{question}\n\n"
        f"## Data from Knowledge Graph\n{raw_result}\n\n"
        "Provide a concise, accurate answer. If no data was returned, state that clearly."
    )
    response = _llm.invoke(prompt)
    return response.content


def run_graph_search(question: str) -> str:
    """Orchestrate all steps. Return final answer string."""
    try:
        ontology_text, schema = load_ontology()
        dsl = parse_dsl(question, ontology_text)
        validate_dsl(dsl, schema)
        ast = build_ast(dsl)
        cypher, params = compile_cypher(ast)
        records = _repo.run_query(cypher, params)
        raw_result = serialise_records(records)
        return generate_answer(question, raw_result)
    except AppException:
        raise
    except Exception as e:
        logger.error(f"Knowledge graph query failed: {e}")
        raise AppException("Knowledge graph query failed", 500)
