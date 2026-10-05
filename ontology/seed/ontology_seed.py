import logging
import os
import sys

from dotenv import load_dotenv
from neo4j import GraphDatabase

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from src.logging.logger import setup_logging

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# NODE CLASSES
# Every node class is traceable to at least one CQ (see cq_refs).
# unique_key receives a uniqueness constraint on the data label.
# ─────────────────────────────────────────────────────────────────────────────

NODE_CLASSES = [
    {
        "name": "Deal",
        "label": "Deal",
        "cq_refs": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 19],
        "unique_key": "deal_id",
        "properties": [
            {"name": "deal_id",      "data_type": "STRING",  "required": True,  "description": "Unique identifier for the deal"},
            {"name": "name",         "data_type": "STRING",  "required": True,  "description": "Name or title of the deal"},
            {"name": "stage",        "data_type": "STRING",  "required": True,  "description": "Current pipeline stage (e.g. Prospecting, Closed Won)"},
            {"name": "status",       "data_type": "STRING",  "required": True,  "description": "Outcome status: Won, Lost, or Active"},
            {"name": "value",        "data_type": "FLOAT",   "required": True,  "description": "Total contract value in USD"},
            {"name": "close_date",   "data_type": "STRING",  "required": True,  "description": "Actual or expected close date (ISO 8601)"},
            {"name": "created_date", "data_type": "STRING",  "required": True,  "description": "Date the deal record was created (ISO 8601)"},
        ],
    },
    {
        "name": "Quarter",
        "label": "Quarter",
        "cq_refs": [1, 6, 8, 11],
        "unique_key": "quarter_id",
        "properties": [
            {"name": "quarter_id",     "data_type": "STRING",  "required": True,  "description": "Unique ID in format YYYY-QN (e.g. 2024-Q1)"},
            {"name": "year",           "data_type": "INTEGER", "required": True,  "description": "Calendar year of the quarter"},
            {"name": "quarter_number", "data_type": "INTEGER", "required": True,  "description": "Quarter number within the year (1–4)"},
            {"name": "total_revenue",  "data_type": "FLOAT",   "required": False, "description": "Actual total revenue closed in this quarter"},
            {"name": "revenue_target", "data_type": "FLOAT",   "required": False, "description": "Revenue target set for this quarter"},
        ],
    },
    {
        "name": "Industry",
        "label": "Industry",
        "cq_refs": [2, 8, 13],
        "unique_key": "industry_id",
        "properties": [
            {"name": "industry_id", "data_type": "STRING", "required": True,  "description": "Unique identifier for the industry"},
            {"name": "name",        "data_type": "STRING", "required": True,  "description": "Industry name (e.g. Banking, Healthcare, Retail)"},
            {"name": "sector",      "data_type": "STRING", "required": False, "description": "Broader sector grouping (e.g. Financial Services, Life Sciences)"},
            {"name": "growth_rate", "data_type": "FLOAT",  "required": False, "description": "YoY revenue growth rate observed for deals in this industry"},
        ],
    },
    {
        "name": "Region",
        "label": "Region",
        "cq_refs": [3, 12],
        "unique_key": "region_id",
        "properties": [
            {"name": "region_id",  "data_type": "STRING", "required": True,  "description": "Unique identifier for the region"},
            {"name": "name",       "data_type": "STRING", "required": True,  "description": "Region name (e.g. North America, APAC, EMEA)"},
            {"name": "country",    "data_type": "STRING", "required": False, "description": "Country if this region maps to a single country"},
            {"name": "territory",  "data_type": "STRING", "required": False, "description": "Sub-territory or sales zone within the region"},
        ],
    },
    {
        "name": "ServiceOffering",
        "label": "ServiceOffering",
        "cq_refs": [4, 13],
        "unique_key": "service_id",
        "properties": [
            {"name": "service_id",  "data_type": "STRING", "required": True,  "description": "Unique identifier for the service offering"},
            {"name": "name",        "data_type": "STRING", "required": True,  "description": "Service name (e.g. Cloud Migration, ERP Implementation)"},
            {"name": "category",    "data_type": "STRING", "required": False, "description": "High-level category (Consulting, Managed Services, Implementation)"},
            {"name": "description", "data_type": "STRING", "required": False, "description": "Short description of what the service delivers"},
        ],
    },
    {
        "name": "Technology",
        "label": "Technology",
        "cq_refs": [5, 13, 14, 20],
        "unique_key": "technology_id",
        "properties": [
            {"name": "technology_id", "data_type": "STRING", "required": True,  "description": "Unique identifier for the technology"},
            {"name": "name",          "data_type": "STRING", "required": True,  "description": "Technology name (e.g. AWS, SAP S/4HANA, Salesforce)"},
            {"name": "category",      "data_type": "STRING", "required": False, "description": "Technology category (Cloud, AI/ML, ERP, CRM, Data & Analytics)"},
        ],
    },
    {
        "name": "Account",
        "label": "Account",
        "cq_refs": [7],
        "unique_key": "account_id",
        "properties": [
            {"name": "account_id",     "data_type": "STRING", "required": True,  "description": "Unique identifier for the customer account"},
            {"name": "name",           "data_type": "STRING", "required": True,  "description": "Account or company name"},
            {"name": "tier",           "data_type": "STRING", "required": False, "description": "Account tier (Platinum, Gold, Silver, Bronze)"},
            {"name": "annual_revenue", "data_type": "FLOAT",  "required": False, "description": "Account's annual revenue in USD"},
        ],
    },
    {
        "name": "LossReason",
        "label": "LossReason",
        "cq_refs": [9, 15],
        "unique_key": "reason_id",
        "properties": [
            {"name": "reason_id",   "data_type": "STRING", "required": True,  "description": "Unique identifier for the loss reason"},
            {"name": "description", "data_type": "STRING", "required": True,  "description": "Human-readable description of why the deal was lost"},
            {"name": "category",    "data_type": "STRING", "required": False, "description": "Loss category (Price, Competition, Timing, Technical, Relationship)"},
        ],
    },
    {
        "name": "PipelineStage",
        "label": "PipelineStage",
        "cq_refs": [10],
        "unique_key": "stage_id",
        "properties": [
            {"name": "stage_id",            "data_type": "STRING",  "required": True,  "description": "Unique identifier for the pipeline stage"},
            {"name": "name",                "data_type": "STRING",  "required": True,  "description": "Stage name (e.g. Qualification, Proposal, Negotiation)"},
            {"name": "order",               "data_type": "INTEGER", "required": True,  "description": "Numeric position of this stage in the funnel (lower = earlier)"},
            {"name": "avg_conversion_rate", "data_type": "FLOAT",   "required": False, "description": "Average rate at which deals progress past this stage"},
        ],
    },
    {
        "name": "SalesRep",
        "label": "SalesRep",
        "cq_refs": [11, 12, 13],
        "unique_key": "rep_id",
        "properties": [
            {"name": "rep_id", "data_type": "STRING", "required": True,  "description": "Unique identifier for the sales representative"},
            {"name": "name",   "data_type": "STRING", "required": True,  "description": "Full name of the sales representative"},
            {"name": "quota",  "data_type": "FLOAT",  "required": False, "description": "Annual or quarterly revenue quota assigned to this rep"},
            {"name": "level",  "data_type": "STRING", "required": False, "description": "Seniority level (Junior, Senior, Principal, Director)"},
        ],
    },
    {
        "name": "Project",
        "label": "Project",
        "cq_refs": [16, 17, 18, 20],
        "unique_key": "project_id",
        "properties": [
            {"name": "project_id",     "data_type": "STRING",  "required": True,  "description": "Unique identifier for the delivery project"},
            {"name": "name",           "data_type": "STRING",  "required": True,  "description": "Project name"},
            {"name": "status",         "data_type": "STRING",  "required": True,  "description": "Delivery status (On Track, Delayed, At Risk, Completed)"},
            {"name": "budget",         "data_type": "FLOAT",   "required": False, "description": "Approved project budget in USD"},
            {"name": "actual_cost",    "data_type": "FLOAT",   "required": False, "description": "Actual spend to date in USD"},
            {"name": "start_date",     "data_type": "STRING",  "required": False, "description": "Project start date (ISO 8601)"},
            {"name": "end_date",       "data_type": "STRING",  "required": False, "description": "Planned or actual end date (ISO 8601)"},
            {"name": "is_delayed",     "data_type": "BOOLEAN", "required": False, "description": "True if delivery is behind schedule"},
            {"name": "exceeds_budget", "data_type": "BOOLEAN", "required": False, "description": "True if actual cost has exceeded the approved budget"},
        ],
    },
    {
        "name": "DeliveryIssue",
        "label": "DeliveryIssue",
        "cq_refs": [16, 17, 18],
        "unique_key": "issue_id",
        "properties": [
            {"name": "issue_id",    "data_type": "STRING", "required": True,  "description": "Unique identifier for the delivery issue"},
            {"name": "type",        "data_type": "STRING", "required": True,  "description": "Issue type (Resource Gap, Scope Creep, Technical Debt, Staffing)"},
            {"name": "severity",    "data_type": "STRING", "required": False, "description": "Severity level (High, Medium, Low)"},
            {"name": "description", "data_type": "STRING", "required": False, "description": "Detailed description of the issue and its impact"},
        ],
    },
    {
        "name": "Employee",
        "label": "Employee",
        "cq_refs": [19],
        "unique_key": "employee_id",
        "properties": [
            {"name": "employee_id", "data_type": "STRING", "required": True,  "description": "Unique identifier for the employee"},
            {"name": "name",        "data_type": "STRING", "required": True,  "description": "Full name of the employee"},
            {"name": "level",       "data_type": "STRING", "required": False, "description": "Seniority level (Junior, Senior, Lead, Principal)"},
            {"name": "department",  "data_type": "STRING", "required": False, "description": "Department or practice area the employee belongs to"},
        ],
    },
    {
        "name": "Skill",
        "label": "Skill",
        "cq_refs": [19],
        "unique_key": "skill_id",
        "properties": [
            {"name": "skill_id",  "data_type": "STRING", "required": True,  "description": "Unique identifier for the skill"},
            {"name": "name",      "data_type": "STRING", "required": True,  "description": "Skill name (e.g. Python, SAP FICO, Cloud Architecture)"},
            {"name": "category",  "data_type": "STRING", "required": False, "description": "Skill category (Technical, Domain, Soft Skills)"},
        ],
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# RELATIONSHIP TYPES
# type_id is the meta-graph unique key: "{from_class}__{name}__{to_class}".
# Relationship type names use uppercase verbs per design rules.
# ─────────────────────────────────────────────────────────────────────────────

RELATIONSHIP_TYPES = [
    {
        "type_id": "Deal__IN_QUARTER__Quarter",
        "name": "IN_QUARTER",
        "from_class": "Deal",
        "to_class": "Quarter",
        "cq_refs": [1, 6, 8, 11],
        "description": "Links a deal to the fiscal quarter in which it closed or is projected to close",
        "properties": [],
    },
    {
        "type_id": "Deal__IN_INDUSTRY__Industry",
        "name": "IN_INDUSTRY",
        "from_class": "Deal",
        "to_class": "Industry",
        "cq_refs": [2, 8, 13],
        "description": "Links a deal directly to the target industry vertical",
        "properties": [],
    },
    {
        "type_id": "Deal__IN_REGION__Region",
        "name": "IN_REGION",
        "from_class": "Deal",
        "to_class": "Region",
        "cq_refs": [3],
        "description": "Links a deal to the geographic region where it was pursued",
        "properties": [],
    },
    {
        "type_id": "Deal__USES_SERVICE__ServiceOffering",
        "name": "USES_SERVICE",
        "from_class": "Deal",
        "to_class": "ServiceOffering",
        "cq_refs": [4, 13],
        "description": "Links a deal to the service offering included in the proposal",
        "properties": [],
    },
    {
        "type_id": "Deal__USES_TECHNOLOGY__Technology",
        "name": "USES_TECHNOLOGY",
        "from_class": "Deal",
        "to_class": "Technology",
        "cq_refs": [5, 13, 14],
        "description": "Links a deal to a technology that is part of the proposed solution",
        "properties": [],
    },
    {
        "type_id": "Deal__BELONGS_TO_ACCOUNT__Account",
        "name": "BELONGS_TO_ACCOUNT",
        "from_class": "Deal",
        "to_class": "Account",
        "cq_refs": [7],
        "description": "Links a deal to the customer account it is associated with",
        "properties": [],
    },
    {
        "type_id": "Deal__LOST_DUE_TO__LossReason",
        "name": "LOST_DUE_TO",
        "from_class": "Deal",
        "to_class": "LossReason",
        "cq_refs": [9, 15],
        "description": "Links a lost deal to the reason(s) it was not won",
        "properties": [],
    },
    {
        "type_id": "Deal__AT_STAGE__PipelineStage",
        "name": "AT_STAGE",
        "from_class": "Deal",
        "to_class": "PipelineStage",
        "cq_refs": [10],
        "description": "Links a deal to its last known or current pipeline stage at exit",
        "properties": [],
    },
    {
        "type_id": "Deal__OWNED_BY__SalesRep",
        "name": "OWNED_BY",
        "from_class": "Deal",
        "to_class": "SalesRep",
        "cq_refs": [11, 12, 13],
        "description": "Links a deal to the sales representative who owns it",
        "properties": [],
    },
    {
        "type_id": "Deal__LED_TO_PROJECT__Project",
        "name": "LED_TO_PROJECT",
        "from_class": "Deal",
        "to_class": "Project",
        "cq_refs": [16],
        "description": "Links a won deal to the delivery project it created",
        "properties": [],
    },
    {
        "type_id": "Account__OPERATES_IN__Industry",
        "name": "OPERATES_IN",
        "from_class": "Account",
        "to_class": "Industry",
        "cq_refs": [2, 7, 8],
        "description": "Links a customer account to the industry it operates in",
        "properties": [],
    },
    {
        "type_id": "SalesRep__COVERS_REGION__Region",
        "name": "COVERS_REGION",
        "from_class": "SalesRep",
        "to_class": "Region",
        "cq_refs": [3, 12],
        "description": "Links a sales rep to the geographic region(s) they are responsible for",
        "properties": [],
    },
    {
        "type_id": "Project__HAS_ISSUE__DeliveryIssue",
        "name": "HAS_ISSUE",
        "from_class": "Project",
        "to_class": "DeliveryIssue",
        "cq_refs": [16, 17, 18],
        "description": "Links a project to a delivery issue that affected it",
        "properties": [],
    },
    {
        "type_id": "Project__USES_TECHNOLOGY__Technology",
        "name": "USES_TECHNOLOGY",
        "from_class": "Project",
        "to_class": "Technology",
        "cq_refs": [20],
        "description": "Links a delivery project to a technology used in its implementation",
        "properties": [],
    },
    {
        "type_id": "Project__REQUIRES_SKILL__Skill",
        "name": "REQUIRES_SKILL",
        "from_class": "Project",
        "to_class": "Skill",
        "cq_refs": [19],
        "description": "Links a project to a skill required to deliver it",
        "properties": [
            {"name": "proficiency_level", "data_type": "STRING", "required": False, "description": "Minimum required proficiency level for this skill on the project"},
        ],
    },
    {
        "type_id": "Employee__HAS_SKILL__Skill",
        "name": "HAS_SKILL",
        "from_class": "Employee",
        "to_class": "Skill",
        "cq_refs": [19],
        "description": "Links an employee to a skill they possess",
        "properties": [
            {"name": "proficiency_level", "data_type": "STRING", "required": False, "description": "Employee's proficiency level in this skill (Beginner, Intermediate, Expert)"},
            {"name": "years_of_experience", "data_type": "FLOAT", "required": False, "description": "Number of years the employee has used this skill"},
        ],
    },
    {
        "type_id": "Employee__WORKS_ON__Project",
        "name": "WORKS_ON",
        "from_class": "Employee",
        "to_class": "Project",
        "cq_refs": [19],
        "description": "Links an employee to a project they are or were assigned to",
        "properties": [
            {"name": "role",       "data_type": "STRING", "required": False, "description": "Role the employee plays on the project (e.g. Tech Lead, Consultant)"},
            {"name": "start_date", "data_type": "STRING", "required": False, "description": "Date the employee joined the project (ISO 8601)"},
            {"name": "end_date",   "data_type": "STRING", "required": False, "description": "Date the employee left the project (ISO 8601)"},
        ],
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# CONSTRAINTS AND INDEXES (applied to actual data labels, not meta-graph labels)
# ─────────────────────────────────────────────────────────────────────────────

CONSTRAINTS = [
    "CREATE CONSTRAINT deal_id_unique IF NOT EXISTS FOR (n:Deal) REQUIRE n.deal_id IS UNIQUE",
    "CREATE CONSTRAINT quarter_id_unique IF NOT EXISTS FOR (n:Quarter) REQUIRE n.quarter_id IS UNIQUE",
    "CREATE CONSTRAINT industry_id_unique IF NOT EXISTS FOR (n:Industry) REQUIRE n.industry_id IS UNIQUE",
    "CREATE CONSTRAINT region_id_unique IF NOT EXISTS FOR (n:Region) REQUIRE n.region_id IS UNIQUE",
    "CREATE CONSTRAINT service_id_unique IF NOT EXISTS FOR (n:ServiceOffering) REQUIRE n.service_id IS UNIQUE",
    "CREATE CONSTRAINT technology_id_unique IF NOT EXISTS FOR (n:Technology) REQUIRE n.technology_id IS UNIQUE",
    "CREATE CONSTRAINT account_id_unique IF NOT EXISTS FOR (n:Account) REQUIRE n.account_id IS UNIQUE",
    "CREATE CONSTRAINT reason_id_unique IF NOT EXISTS FOR (n:LossReason) REQUIRE n.reason_id IS UNIQUE",
    "CREATE CONSTRAINT stage_id_unique IF NOT EXISTS FOR (n:PipelineStage) REQUIRE n.stage_id IS UNIQUE",
    "CREATE CONSTRAINT rep_id_unique IF NOT EXISTS FOR (n:SalesRep) REQUIRE n.rep_id IS UNIQUE",
    "CREATE CONSTRAINT project_id_unique IF NOT EXISTS FOR (n:Project) REQUIRE n.project_id IS UNIQUE",
    "CREATE CONSTRAINT issue_id_unique IF NOT EXISTS FOR (n:DeliveryIssue) REQUIRE n.issue_id IS UNIQUE",
    "CREATE CONSTRAINT employee_id_unique IF NOT EXISTS FOR (n:Employee) REQUIRE n.employee_id IS UNIQUE",
    "CREATE CONSTRAINT skill_id_unique IF NOT EXISTS FOR (n:Skill) REQUIRE n.skill_id IS UNIQUE",
]

INDEXES = [
    # Deal — frequently filtered by status, stage, value, and close date
    "CREATE INDEX deal_status_idx IF NOT EXISTS FOR (n:Deal) ON (n.status)",
    "CREATE INDEX deal_stage_idx IF NOT EXISTS FOR (n:Deal) ON (n.stage)",
    "CREATE INDEX deal_value_idx IF NOT EXISTS FOR (n:Deal) ON (n.value)",
    "CREATE INDEX deal_close_date_idx IF NOT EXISTS FOR (n:Deal) ON (n.close_date)",
    # Quarter — filtered by year and quarter number for time-series queries
    "CREATE INDEX quarter_year_idx IF NOT EXISTS FOR (n:Quarter) ON (n.year)",
    "CREATE INDEX quarter_number_idx IF NOT EXISTS FOR (n:Quarter) ON (n.quarter_number)",
    # Project — filtered by status, delay, and budget flags
    "CREATE INDEX project_status_idx IF NOT EXISTS FOR (n:Project) ON (n.status)",
    "CREATE INDEX project_is_delayed_idx IF NOT EXISTS FOR (n:Project) ON (n.is_delayed)",
    "CREATE INDEX project_exceeds_budget_idx IF NOT EXISTS FOR (n:Project) ON (n.exceeds_budget)",
    # Lookup indexes for named entities
    "CREATE INDEX industry_name_idx IF NOT EXISTS FOR (n:Industry) ON (n.name)",
    "CREATE INDEX region_name_idx IF NOT EXISTS FOR (n:Region) ON (n.name)",
    "CREATE INDEX technology_name_idx IF NOT EXISTS FOR (n:Technology) ON (n.name)",
    "CREATE INDEX salesrep_name_idx IF NOT EXISTS FOR (n:SalesRep) ON (n.name)",
    "CREATE INDEX account_name_idx IF NOT EXISTS FOR (n:Account) ON (n.name)",
    "CREATE INDEX skill_name_idx IF NOT EXISTS FOR (n:Skill) ON (n.name)",
]


# ─────────────────────────────────────────────────────────────────────────────
# SEEDING FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def seed_node_classes(session) -> None:
    logger.info("Seeding NodeClass and PropertyDef nodes into the meta-graph")
    for nc in NODE_CLASSES:
        session.run(
            """
            MERGE (nc:NodeClass {name: $name})
            SET nc.label    = $label,
                nc.cq_refs  = $cq_refs,
                nc.unique_key = $unique_key
            """,
            name=nc["name"],
            label=nc["label"],
            cq_refs=nc["cq_refs"],
            unique_key=nc["unique_key"],
        )
        logger.info("  NodeClass '%s' merged", nc["name"])

        for prop in nc["properties"]:
            prop_id = f"NodeClass_{nc['name']}__{prop['name']}"
            session.run(
                """
                MERGE (pd:PropertyDef {prop_id: $prop_id})
                SET pd.name        = $name,
                    pd.data_type   = $data_type,
                    pd.required    = $required,
                    pd.description = $description
                WITH pd
                MATCH (nc:NodeClass {name: $class_name})
                MERGE (nc)-[:HAS_PROPERTY]->(pd)
                """,
                prop_id=prop_id,
                name=prop["name"],
                data_type=prop["data_type"],
                required=prop["required"],
                description=prop["description"],
                class_name=nc["name"],
            )
        logger.info("  Seeded %d properties for NodeClass '%s'", len(nc["properties"]), nc["name"])

    logger.info("NodeClass seeding complete — %d classes processed", len(NODE_CLASSES))


def seed_relationship_types(session) -> None:
    logger.info("Seeding RelationshipType nodes into the meta-graph")
    for rt in RELATIONSHIP_TYPES:
        session.run(
            """
            MERGE (r:RelationshipType {type_id: $type_id})
            SET r.name        = $name,
                r.cq_refs     = $cq_refs,
                r.description = $description
            WITH r
            MATCH (from_nc:NodeClass {name: $from_class})
            MATCH (to_nc:NodeClass   {name: $to_class})
            MERGE (r)-[:FROM_CLASS]->(from_nc)
            MERGE (r)-[:TO_CLASS]->(to_nc)
            """,
            type_id=rt["type_id"],
            name=rt["name"],
            cq_refs=rt["cq_refs"],
            description=rt["description"],
            from_class=rt["from_class"],
            to_class=rt["to_class"],
        )
        logger.info("  RelationshipType '%s' merged", rt["type_id"])

        for prop in rt.get("properties", []):
            prop_id = f"RelType_{rt['type_id']}__{prop['name']}"
            session.run(
                """
                MERGE (pd:PropertyDef {prop_id: $prop_id})
                SET pd.name        = $name,
                    pd.data_type   = $data_type,
                    pd.required    = $required,
                    pd.description = $description
                WITH pd
                MATCH (r:RelationshipType {type_id: $type_id})
                MERGE (r)-[:HAS_PROPERTY]->(pd)
                """,
                prop_id=prop_id,
                name=prop["name"],
                data_type=prop["data_type"],
                required=prop["required"],
                description=prop["description"],
                type_id=rt["type_id"],
            )

        if rt["properties"]:
            logger.info(
                "  Seeded %d properties for RelationshipType '%s'",
                len(rt["properties"]),
                rt["type_id"],
            )

    logger.info("RelationshipType seeding complete — %d types processed", len(RELATIONSHIP_TYPES))


def apply_constraints_and_indexes(session) -> None:
    logger.info("Applying constraints and indexes on data labels")
    for cypher in CONSTRAINTS:
        session.run(cypher)
        logger.info("  Applied: %s", cypher.split("FOR")[0].strip())

    for cypher in INDEXES:
        session.run(cypher)
        logger.info("  Applied: %s", cypher.split("FOR")[0].strip())

    logger.info(
        "Constraints and indexes complete — %d constraints, %d indexes",
        len(CONSTRAINTS),
        len(INDEXES),
    )


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    setup_logging()
    load_dotenv()

    neo4j_url = os.environ["NEO4J_URL"]
    neo4j_user = os.environ["NEO4J_USERNAME"]
    neo4j_password = os.environ["NEO4J_PASSWORD"]
    neo4j_database = os.environ.get("NEO4J_DATABASE", "neo4j")

    logger.info(
        "Connecting to Neo4j at %s (database: %s)", neo4j_url, neo4j_database
    )

    driver = GraphDatabase.driver(neo4j_url, auth=(neo4j_user, neo4j_password))
    try:
        driver.verify_connectivity()
        logger.info("Neo4j connection verified")

        with driver.session(database=neo4j_database) as session:
            seed_node_classes(session)
            seed_relationship_types(session)
            apply_constraints_and_indexes(session)

        logger.info("Ontology seeding finished successfully")
    finally:
        driver.close()


if __name__ == "__main__":
    main()
