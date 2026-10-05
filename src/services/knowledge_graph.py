import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from src.repository.knowledge_graph import KnowledgeGraphRepository
from src.utils.exception import AppException

logger = logging.getLogger(__name__)

MAX_EXTRACTION_CHARS = 50_000

_ONTOLOGY_PATH = Path(__file__).parent.parent.parent / "ontology" / "ontology_context.md"

_UNIQUE_KEYS: dict[str, str] = {
    "Deal": "deal_id",
    "Quarter": "quarter_id",
    "Industry": "name",
    "Region": "name",
    "ServiceOffering": "name",
    "Technology": "name",
    "Account": "account_id",
    "SalesRep": "rep_id",
    "PipelineStage": "name",
    "LossReason": "reason_id",
    "Project": "project_id",
    "DeliveryIssue": "issue_id",
    "Skill": "name",
    "Employee": "employee_id",
}

_REQUIRED_FIELDS: dict[str, set[str]] = {
    "Deal": {"deal_id", "name", "value", "status"},
    "Quarter": {"quarter_id", "year", "quarter_number"},
    "Industry": {"industry_id", "name"},
    "Region": {"region_id", "name"},
    "ServiceOffering": {"service_id", "name"},
    "Technology": {"technology_id", "name"},
    "Account": {"account_id", "name"},
    "SalesRep": {"rep_id", "name"},
    "PipelineStage": {"stage_id", "name"},
    "LossReason": {"reason_id", "description"},
    "Project": {"project_id", "name"},
    "DeliveryIssue": {"issue_id", "type"},
    "Skill": {"skill_id", "name"},
    "Employee": {"employee_id", "name"},
}

_ENUM_CONSTRAINTS: dict[tuple[str, str], set[str]] = {
    ("Deal", "status"): {"Won", "Lost", "Active"},
    ("Account", "tier"): {"Platinum", "Gold", "Silver", "Bronze"},
    ("SalesRep", "level"): {"Junior", "Senior", "Principal", "Director"},
    ("DeliveryIssue", "severity"): {"High", "Medium", "Low"},
    ("Employee", "level"): {"Junior", "Mid", "Senior", "Lead", "Principal"},
}

_VALID_RELATIONSHIPS: set[tuple[str, str, str]] = {
    ("Deal", "IN_QUARTER", "Quarter"),
    ("Deal", "IN_INDUSTRY", "Industry"),
    ("Deal", "IN_REGION", "Region"),
    ("Deal", "USES_SERVICE", "ServiceOffering"),
    ("Deal", "USES_TECHNOLOGY", "Technology"),
    ("Deal", "BELONGS_TO_ACCOUNT", "Account"),
    ("Deal", "OWNED_BY", "SalesRep"),
    ("Deal", "AT_STAGE", "PipelineStage"),
    ("Deal", "LOST_DUE_TO", "LossReason"),
    ("Deal", "LED_TO_PROJECT", "Project"),
    ("Account", "OPERATES_IN", "Industry"),
    ("SalesRep", "COVERS_REGION", "Region"),
    ("Project", "HAS_ISSUE", "DeliveryIssue"),
    ("Project", "USES_TECHNOLOGY", "Technology"),
    ("Project", "REQUIRES_SKILL", "Skill"),
    ("Employee", "HAS_SKILL", "Skill"),
    ("Employee", "WORKS_ON", "Project"),
}


@dataclass
class KGIngestResult:
    nodes_created: int = 0
    nodes_merged: int = 0
    relationships_created: int = 0
    relationships_skipped: int = 0
    nodes_dropped: int = 0
    relationships_dropped: int = 0


class KnowledgeGraphService:
    def __init__(self):
        self._repo = KnowledgeGraphRepository()
        self._openai_api_key = os.environ["OPENAI_API_KEY"]
        self._openai_model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        self._ontology = _ONTOLOGY_PATH.read_text(encoding="utf-8")

    def process_document(self, extracted_text: str, filename: str) -> KGIngestResult:
        logger.info(f"KG pipeline started for '{filename}'")
        text = extracted_text[:MAX_EXTRACTION_CHARS]

        raw = self._call_llm(text)
        parsed = self._parse_llm_output(raw, filename)
        result = KGIngestResult()
        valid_nodes, valid_rels = self._validate(parsed, result)
        self._write_nodes(valid_nodes, result)
        self._write_relationships(valid_rels, result)

        logger.info(
            f"KG pipeline complete for '{filename}': "
            f"nodes created={result.nodes_created} merged={result.nodes_merged} "
            f"dropped={result.nodes_dropped}; "
            f"rels created={result.relationships_created} "
            f"skipped={result.relationships_skipped} dropped={result.relationships_dropped}"
        )
        return result

    def _call_llm(self, text: str) -> str:
        from openai import OpenAI
        client = OpenAI(api_key=self._openai_api_key)
        response = client.chat.completions.create(
            model=self._openai_model,
            max_completion_tokens=4096,
            messages=[
                {"role": "system", "content": self._build_system_prompt()},
                {"role": "user", "content": text},
            ],
        )
        return response.choices[0].message.content

    def _build_system_prompt(self) -> str:
        uk_lines = "\n".join(
            f"  {label}: {key}" for label, key in _UNIQUE_KEYS.items()
        )
        return f"""You are a knowledge graph extraction assistant.

Given document text, extract entities and relationships that match the following ontology:

{self._ontology}

Return ONLY valid JSON in this exact format — no markdown fences, no explanation:
{{
  "nodes": [
    {{"label": "<NodeLabel>", "properties": {{"<field>": "<value>", ...}}}}
  ],
  "relationships": [
    {{
      "from_label": "<Label>",
      "from_value": "<unique_key_value>",
      "to_label": "<Label>",
      "to_value": "<unique_key_value>",
      "type": "<RELATIONSHIP_TYPE>"
    }}
  ]
}}

Rules:
- Only extract entities and relationships explicitly present in the document text.
- Only use node labels and relationship types defined in the ontology.
- Every node must include all required fields (marked with ! in the ontology).
- Respect enum constraints exactly as specified (case-sensitive).
- CRITICAL — enum-constrained optional fields: for any field shown as [v1|v2|...] in the
  ontology, ONLY include it when one of those exact enum strings appears verbatim in the
  source text for that specific entity. NEVER infer, map, or approximate the value from a
  different column or field (e.g. do NOT set Account.tier from an industry or region column).
  When in doubt, omit the field entirely.
- If an optional field value cannot be determined from the text, omit the field entirely.
- Columnar data (CSV / spreadsheet rows): when a column references another entity type
  (e.g. an 'industry' column on an Account row, or a 'region' column), emit that referenced
  value as a SEPARATE node of the correct label AND add the corresponding relationship entry.
  Do not store cross-entity values as properties on the primary node.
- Do not invent or hallucinate values not present in the document.
- CRITICAL — from_value / to_value in relationships must be the value of the unique-key field
  for that label. The unique-key field for each label is:
{uk_lines}"""

    def _parse_llm_output(self, raw: str, filename: str) -> dict:
        logger.debug(f"LLM raw output for '{filename}': {raw[:1000]}")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.error(
                f"LLM returned non-JSON for '{filename}': {e}. "
                f"Raw (first 200 chars): {raw[:200]}"
            )
            raise AppException("KG extraction failed: LLM returned invalid JSON", status_code=500)
        if not isinstance(parsed, dict):
            raise AppException("KG extraction failed: LLM JSON is not an object", status_code=500)
        parsed.setdefault("nodes", [])
        parsed.setdefault("relationships", [])
        return parsed

    def _validate(
        self, parsed: dict, result: KGIngestResult
    ) -> tuple[list[dict], list[dict]]:
        valid_nodes: list[dict] = []
        for node in parsed.get("nodes", []):
            label = node.get("label")
            props = node.get("properties", {})

            if label not in _UNIQUE_KEYS:
                logger.warning(f"Dropping node: unknown label '{label}'")
                result.nodes_dropped += 1
                continue

            required = _REQUIRED_FIELDS.get(label, set())
            missing = [f for f in required if not props.get(f)]
            if missing:
                logger.warning(f"Dropping {label} node: missing required fields {missing}")
                result.nodes_dropped += 1
                continue

            invalid_enum = False
            for (lbl, field), allowed in _ENUM_CONSTRAINTS.items():
                if lbl == label and field in props and props[field] not in allowed:
                    logger.warning(
                        f"Dropping {label} node: '{field}' value '{props[field]}' "
                        f"not in {allowed}"
                    )
                    invalid_enum = True
                    break
            if invalid_enum:
                result.nodes_dropped += 1
                continue

            valid_nodes.append(node)

        valid_rels: list[dict] = []
        for rel in parsed.get("relationships", []):
            from_label = rel.get("from_label")
            to_label = rel.get("to_label")
            rel_type = rel.get("type")
            from_value = rel.get("from_value")
            to_value = rel.get("to_value")

            if not all([from_label, to_label, rel_type, from_value is not None, to_value is not None]):
                logger.warning(f"Dropping relationship: missing required fields in {rel}")
                result.relationships_dropped += 1
                continue

            if (from_label, rel_type, to_label) not in _VALID_RELATIONSHIPS:
                logger.warning(
                    f"Dropping relationship: ({from_label})-[:{rel_type}]->({to_label}) "
                    f"not in ontology"
                )
                result.relationships_dropped += 1
                continue

            valid_rels.append(rel)

        return valid_nodes, valid_rels

    def _write_nodes(self, nodes: list[dict], result: KGIngestResult) -> None:
        for node in nodes:
            label = node["label"]
            props = node["properties"]
            unique_key = _UNIQUE_KEYS[label]
            try:
                created = self._repo.merge_node(label, unique_key, props)
            except Exception as e:
                logger.error(f"Neo4j node MERGE failed for {label}: {e}")
                raise AppException("KG write failed", status_code=500)
            if created:
                result.nodes_created += 1
            else:
                result.nodes_merged += 1

    def _write_relationships(self, rels: list[dict], result: KGIngestResult) -> None:
        for rel in rels:
            from_label = rel["from_label"]
            to_label = rel["to_label"]
            rel_type = rel["type"]
            from_key = _UNIQUE_KEYS[from_label]
            to_key = _UNIQUE_KEYS[to_label]
            from_value = rel["from_value"]
            to_value = rel["to_value"]
            try:
                exists = self._repo.relationship_exists(
                    from_label, from_key, from_value,
                    to_label, to_key, to_value,
                    rel_type,
                )
            except Exception as e:
                logger.error(f"Neo4j relationship check failed: {e}")
                raise AppException("KG write failed", status_code=500)
            if exists:
                result.relationships_skipped += 1
                continue
            try:
                self._repo.create_relationship(
                    from_label, from_key, from_value,
                    to_label, to_key, to_value,
                    rel_type,
                )
                result.relationships_created += 1
            except Exception as e:
                logger.error(f"Neo4j relationship create failed: {e}")
                raise AppException("KG write failed", status_code=500)
