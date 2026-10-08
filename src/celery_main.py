from celery import Celery

from src.config import settings

app = Celery("customer-support-agent",broker=settings.broker_url,backend=settings.broker_url)

