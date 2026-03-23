from app.db.session import engine
from sqlalchemy import text

head_revision = "49d94bae5339"

with engine.connect() as connection:
    # Use connection.execute with text() and commit explicitly if needed
    # In newer SQLAlchemy, connection.execute(text(...)) requires commit
    connection.execute(text(f"UPDATE alembic_version SET version_num = '{head_revision}'"))
    connection.commit()
    print(f"Successfully updated alembic_version to {head_revision} using app engine.")
