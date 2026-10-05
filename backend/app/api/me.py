from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.schemas import envelope
from app.core.db import get_db
from app.models.core import Profile, User

router = APIRouter(tags=["me"])


@router.get("/me")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Profile and roles of the authenticated user (roles arrive with B04)."""
    profile = db.get(Profile, user.id)
    return envelope(
        data={
            "id": str(user.id),
            "phone": user.phone_e164,
            "status": user.status,
            "roles": [],
            "profile": {
                "first_name": profile.first_name if profile else None,
                "last_name": profile.last_name if profile else None,
            },
        }
    )
