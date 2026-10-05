import logging

from src.db.neo4j_connection import Neo4jConnection

logger = logging.getLogger(__name__)


class KnowledgeGraphRepository:

    @property
    def _driver(self):
        return Neo4jConnection.get_driver()

    def merge_node(self, label: str, unique_key: str, properties: dict) -> bool:
        """MERGE node by unique key; set all properties on create, merge on match.
        Returns True if the node was newly created, False if it already existed."""
        logger.info(f"Merging node label={label} {unique_key}={properties.get(unique_key)}")
        query = (
            f"MERGE (n:{label} {{{unique_key}: $key_value}}) "
            f"ON CREATE SET n = $props "
            f"ON MATCH SET n += $props "
            f"RETURN n"
        )
        with Neo4jConnection.get_session() as session:
            result = session.run(query, key_value=properties[unique_key], props=properties)
            summary = result.consume()
            return summary.counters.nodes_created > 0

    def relationship_exists(
        self,
        from_label: str,
        from_key: str,
        from_value,
        to_label: str,
        to_key: str,
        to_value,
        rel_type: str,
    ) -> bool:
        logger.info(
            f"Checking ({from_label})-[:{rel_type}]->({to_label}) "
            f"{from_key}={from_value} -> {to_key}={to_value}"
        )
        query = (
            f"MATCH (a:{from_label} {{{from_key}: $from_value}})"
            f"-[r:{rel_type}]->"
            f"(b:{to_label} {{{to_key}: $to_value}}) "
            f"RETURN count(r) AS cnt"
        )
        with Neo4jConnection.get_session() as session:
            result = session.run(query, from_value=from_value, to_value=to_value)
            record = result.single()
            return (record["cnt"] > 0) if record else False

    def run_query(self, cypher: str, params: dict) -> list[dict]:
        """Execute a read query and return all records as plain dicts."""
        logger.info(f"Running read query: {cypher[:120]}")
        with Neo4jConnection.get_session() as session:
            result = session.run(cypher, **params)
            return [record.data() for record in result]

    def create_relationship(
        self,
        from_label: str,
        from_key: str,
        from_value,
        to_label: str,
        to_key: str,
        to_value,
        rel_type: str,
    ) -> None:
        logger.info(f"Creating ({from_label})-[:{rel_type}]->({to_label})")
        query = (
            f"MATCH (a:{from_label} {{{from_key}: $from_value}}) "
            f"MATCH (b:{to_label} {{{to_key}: $to_value}}) "
            f"MERGE (a)-[:{rel_type}]->(b)"
        )
        with Neo4jConnection.get_session() as session:
            session.run(query, from_value=from_value, to_value=to_value)
