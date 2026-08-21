from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from config import settings


human_reviewer_url = f"postgresql+psycopg2://{settings.read_role_user}:{settings.read_role_password}@localhost/lumen_support"
human_engine = create_engine(url=read_url)
def get_db(engine):
    Session = sessionmaker(bind=engine,expire_on_commit=False)
    return Session()