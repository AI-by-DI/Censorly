from sqlalchemy import text
from sqlalchemy.orm import Session

class UserRepo:
    def __init__(self, db: Session):
        self.db = db

    def create_user(self, email: str, password_hash: str, country: str | None, birth_year: int | None):
        row = self.db.execute(
            text("""INSERT INTO users (email, password_hash, country, birth_year)
                    VALUES (:e,:p,:c,:b)
                    RETURNING id,email,country,birth_year,created_at,updated_at"""),
            {"e": email, "p": password_hash, "c": country, "b": birth_year}
        ).mappings().first()
        self.db.commit()
        return dict(row)

    def get_by_email(self, email: str):
        row = self.db.execute(
            text("""SELECT id,email,password_hash,country,birth_year,created_at,updated_at
                    FROM users WHERE email=:e"""),
            {"e": email}
        ).mappings().first()
        return dict(row) if row else None

    def store_refresh_jti(self, jti: str, user_id: str, expires_at):
        self.db.execute(
            text("INSERT INTO user_refresh_tokens (jti,user_id,expires_at) VALUES (:j,:u,:x)"),
            {"j": jti, "u": user_id, "x": expires_at}
        )
        self.db.commit()

    def revoke_refresh_jti(self, jti: str):
        self.db.execute(text("DELETE FROM user_refresh_tokens WHERE jti=:j"), {"j": jti})
        self.db.commit()

    def refresh_exists(self, jti: str) -> bool:
        return bool(self.db.execute(text("SELECT 1 FROM user_refresh_tokens WHERE jti=:j"), {"j": jti}).first())
