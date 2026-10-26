import uuid
from datetime import datetime, timedelta

from jose import jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities import AuthSession

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")
ALGORITHM = "HS256"

def hash_password(password):
    return pwd_context.hash(password)

def verify_password(password, hashed):
    return pwd_context.verify(password, hashed)

def create_access_token(db: Session, user_id):
    settings = get_settings()
    now = datetime.utcnow()
    expires = now + timedelta(minutes=settings.access_token_minutes)
    token_id = uuid.uuid4()
    # Expired rows are no longer needed for revocation checks.
    db.query(AuthSession).filter(AuthSession.expires_at <= now).delete(synchronize_session=False)
    db.add(AuthSession(id=token_id, user_id=user_id, expires_at=expires, created_at=now))
    return jwt.encode({"sub": str(user_id), "jti": str(token_id), "iat": now, "exp": expires},
                      settings.secret_key, algorithm=ALGORITHM)
