from sqlalchemy.orm import sessionmaker

def get_db(engine):
    Session = sessionmaker(bind=engine,expire_on_commit=False)
    return Session()