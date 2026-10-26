from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.models.entities import AuthSession, User

bearer = HTTPBearer(auto_error=False)

def current_session(credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
                    db: Session = Depends(get_db)) -> AuthSession:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = jwt.decode(credentials.credentials, get_settings().secret_key, algorithms=["HS256"] )
        user_id = UUID(payload.get("sub", ""))
        session_id = UUID(payload.get("jti", ""))
    except (JWTError, ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Invalid or expired access token", headers={"WWW-Authenticate": "Bearer"})
    session = db.query(AuthSession).filter(
        AuthSession.id == session_id, AuthSession.user_id == user_id,
        AuthSession.revoked_at.is_(None), AuthSession.expires_at > datetime.utcnow(),
    ).first()
    if session is None:
        raise HTTPException(status_code=401, detail="Session is invalid or has been revoked", headers={"WWW-Authenticate": "Bearer"})
    return session

def current_user(session: AuthSession = Depends(current_session), db: Session = Depends(get_db)) -> User:
    user = db.query(User).filter(User.id == session.user_id).first()
    if user is None:
        raise HTTPException(status_code=401, detail="User no longer exists", headers={"WWW-Authenticate": "Bearer"})
    return user
