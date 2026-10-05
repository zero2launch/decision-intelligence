import logging
from src.agents.graph import graph
from src.utils.exception import AppException

logger = logging.getLogger(__name__)


class ChatService:

    def ask(self, question: str, username: str) -> str:
        logger.info(f"Chat request from '{username}': {question[:80]}")
        config = {"configurable": {"thread_id": username}}
        try:
            result = graph.invoke({"question": question}, config=config)
        except Exception as e:
            logger.error(f"Graph invocation failed for '{username}': {e}")
            raise AppException("Chat workflow failed", status_code=500)
        answer = result.get("answer", "")
        if not answer:
            logger.warning(f"Graph returned empty answer for '{username}'")
            raise AppException("Chat workflow failed", status_code=500)
        return answer
