from app.database.database import SessionLocal
from app.models.user import User

db = SessionLocal()

users = db.query(User).all()

print("\n===== USERS =====")

for u in users:
    print("---------------------")
    print("ID:", u.id)
    print("Username:", u.username)
    print("Email:", u.email)
    print("Role:", u.role)
    print("Active:", u.is_active)