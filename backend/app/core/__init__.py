from app.core.database import Base, engine
from app.core.models import Users, AuditRecord

def create_tables():
    Base.metadata.create_all(bind=engine)

if __name__ == "__main__":
    create_tables()
