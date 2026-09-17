from google.api_core.exceptions import DeadlineExceeded, ServiceUnavailable
from sqlalchemy.exc import DBAPIError, OperationalError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10), retry=retry_if_exception_type((DeadlineExceeded,ServiceUnavailable)))
def invoke_with_retry(llm, messages):
    return llm.invoke(messages)

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10),retry=retry_if_exception_type((OperationalError, DBAPIError)))
def run_query_with_retry(fn):
    return fn()
