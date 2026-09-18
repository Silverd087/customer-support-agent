from celery import Celery

from config import settings

app = Celery("customer-support-agent",broker=settings.broker_url,backend=settings.broker_url)

