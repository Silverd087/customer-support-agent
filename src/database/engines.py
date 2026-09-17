from sqlalchemy import create_engine

from config import settings

write_url = f"postgresql+psycopg2://{settings.write_role_user}:{settings.write_role_password}@{settings.db_host}/{settings.db_name}"
write_engine = create_engine(url=write_url)

read_url = f"postgresql+psycopg2://{settings.read_role_user}:{settings.read_role_password}@{settings.db_host}/{settings.db_name}"
read_engine = create_engine(url=read_url)

review_url = f"postgresql+psycopg2://{settings.human_reviewer_role_user}:{settings.human_reviewer_role_password}@{settings.db_host}/{settings.db_name}"
review_engine = create_engine(url=review_url)