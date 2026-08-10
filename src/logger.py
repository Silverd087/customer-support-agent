import logging
import json

class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "time": self.formatTime(record, "%Y-%m-%d %H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "extra_fields"):
            log_record.update(record.extra_fields)
        return json.dumps(log_record)

logger = logging.getLogger("agent_logs")
logger.setLevel(logging.INFO)
if not logger.handlers: 
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)

def log_query(question: str, intent: str, chunks: list[tuple[str, float]], thread_id: str | None = None):
    logger.info(
        "query_processed",
        extra={"extra_fields": {
            "thread_id": thread_id,
            "question": question,
            "intent": intent,
            "retrieved_chunks": [
                {"content": c, "similarity_score": score} for c, score in chunks
            ],
        }},
    )