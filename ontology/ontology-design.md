### About the project

```md

  ## Project Scope
The **IT Services & Consulting Revenue Intelligence** platform is an advanced AI system designed to help consulting firms uncover the "why" behind their critical business metrics. By securely ingesting internal business documents—such as CRM reports, project proposals, HR records, and financial statements—the system builds a dynamic Knowledge Graph. This platform allows business leaders to ask complex, plain-English questions (e.g., "Why did sales drop last quarter?" or "Why are senior engineers leaving?") and receive precise, data-backed answers synthesized from across the organization's siloed data.

---

## Competency Questions (CQs) for Ontology Design

1. Why did revenue drop this quarter?
2. Which industries contribute the most revenue?
3. Which regions are underperforming?
4. Which service offerings generate the highest revenue?
5. Which technologies generate the highest revenue?
6. What is the expected revenue next quarter?
7. Which accounts contribute most to revenue?
8. Which industries are growing fastest?
9. Why are deals being lost?
10. Which stage has the highest pipeline leakage?
11. Why has the win rate decreased?
12. Which sales reps are underperforming?
13. What factors correlate with successful deals?
14. Which technologies have the highest win rate?
15. What are the top reasons for deal loss?
16. Are delivery issues causing revenue loss?
17. Which projects are delayed?
18. Which projects exceed budget?
19. Are skill shortages affecting deal wins?
20. Which technologies are associated with project delays?




## Design Ontology Prompt

```
Read the project scope and all 20 Competency Questions (CQs) from this file. Read the Neo4j connection details from .env.

Task:
Create the ontology for this Knowledge Graph inside ontology/seed/ontology_seed.py using the Neo4j Python driver.

What "ontology" means here:
An ontology is the schema of the knowledge graph. It defines:

Node classes — entity types (e.g. Deal, Quarter) with their property names, data types, and whether each property is required
Relationship types — directed edges between node classes (e.g. (Deal)-[:IN_QUARTER]->(Quarter)) with their own properties if any
Constraints — uniqueness rules on key properties of each node class
Indexes — on properties that will be frequently filtered or sorted
Do not insert any actual data records (no sample deals, no example quarters, no mock employees). The ontology only defines the structure — what can exist, not what does exist.

Design rules:

Every node class and relationship type must be traceable to at least one CQ
Every node class must have a unique identifier property that gets a uniqueness constraint
Relationship types must be named with uppercase verbs (e.g. USES_TECHNOLOGY, LOST_DUE_TO)
Properties must specify: name, data_type (STRING / INTEGER / FLOAT / BOOLEAN / LIST), required (true/false), and a one-line description
Represent the ontology as a meta-graph inside Neo4j: create (:NodeClass) nodes, (:PropertyDef) nodes linked via [:HAS_PROPERTY], and (:RelationshipType) nodes linked via [:FROM_CLASS] and [:TO_CLASS]
All Cypher statements must use MERGE so the script is idempotent (safe to re-run)
Use src.logging.logger.setup_logging() for logging; load env vars via python-dotenv
Output:
A single ontology_seed.py file with:

NODE_CLASSES — Python list defining all node classes and their property schemas
RELATIONSHIP_TYPES — Python list defining all relationship types
CONSTRAINTS and INDEXES — Cypher strings for the data labels
seed_node_classes(session), seed_relationship_types(session), apply_constraints_and_indexes(session) functions
A main() entry point that connects to Neo4j using .env values and runs all three functions in order


```