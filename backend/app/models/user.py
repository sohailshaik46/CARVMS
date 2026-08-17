from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import relationship

from app.auth.roles import ALL_ROLES
from app.database.database import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            f"role IN {tuple(ALL_ROLES)}",
            name="ck_users_role_valid",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)

    username = Column(
        String,
        unique=True,
        nullable=False,
        index=True,
    )

    email = Column(
        String,
        unique=True,
        nullable=False,
    )

    # Per-user mobile number -- where THIS user's own OTP (password reset)
    # and disciplinary-escalation SMS alerts go, never a shared/org number.
    # Nullable so existing rows created before this field don't break;
    # new self-registrations require it (see schemas/auth.py UserRegister).
    phone_number = Column(
        String,
        nullable=True,
    )

    password_hash = Column(
        String,
        nullable=False,
    )

    role = Column(
        String,
        nullable=False,
        default="Auditor",
    )

    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
        server_default="1",
    )

    # The org unit this user is anchored to -- e.g. a Center Manager's
    # assigned center, a Zonal Manager's assigned zone. Nullable
    # because Admin/Finance/Auditor are not scoped to a single node. Used
    # by audit_service to restrict what scoped roles can see (see
    # audit_service.py for the exact scoping rule).
    org_node_id = Column(Integer, ForeignKey("org_nodes.id"), nullable=True, index=True)
    org_node = relationship("OrgNode")

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
