
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import func, inspect, text, update
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from backend.database import engine, Base, SessionLocal
from backend import models, schemas
from backend.security import (
    hash_password,
    verify_password,
    create_access_token,
    verify_access_token,
    ACCESS_TOKEN_EXPIRE_HOURS
)


Base.metadata.create_all(bind=engine)
if "photo_data" not in {
    column["name"] for column in inspect(engine).get_columns("students")
}:
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE students ADD COLUMN photo_data TEXT"))


app = FastAPI(title="Student Management System")


security = HTTPBearer()


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5500",
        "http://localhost:5500",
        "http://127.0.0.1:5501",
        "http://localhost:5501",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


# Get currently logged-in user
def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    token = credentials.credentials

    payload = verify_access_token(token)

    if payload is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token"
        )

    user_id = payload.get("user_id")

    user = db.query(models.User).filter(
        models.User.id == user_id
    ).first()

    if user is None:
        raise HTTPException(
            status_code=401,
            detail="User not found"
        )

    return user



@app.get("/")
def welcome():
    return {
        "message": "Welcome to Student Management System"
    }


@app.post("/register")
def register_user(
    user: schemas.UserCreate,
    db: Session = Depends(get_db)
):
    existing_user = db.query(models.User).filter(
        models.User.email == user.email
    ).first()

    if existing_user:
        raise HTTPException(
            status_code=409,
            detail="Email already registered"
        )

    hashed_password = hash_password(user.password)

    new_user = models.User(
        name=user.name,
        email=user.email,
        password=hashed_password
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {
        "message": "User registered successfully",
        "user_id": new_user.id
    }



@app.post("/login")
def login_user(
    user: schemas.UserLogin,
    db: Session = Depends(get_db)
):
    existing_user = db.query(models.User).filter(
        models.User.email == user.email
    ).first()

    if existing_user is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password"
        )

    password_correct = verify_password(
        user.password,
        existing_user.password
    )

    if not password_correct:
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password"
        )

    access_token = create_access_token(
        existing_user.id,
        existing_user.email
    )

    return {
        "message": "Login successful",
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_HOURS * 60 * 60,
        "user_id": existing_user.id,
        "name": existing_user.name,
        "email": existing_user.email
    }



@app.get("/students")
def get_students(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    return db.query(models.Student).order_by(models.Student.id.asc()).all()



@app.post("/students")
def create_student(
    student: schemas.StudentCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("LOCK TABLE students IN EXCLUSIVE MODE"))

    existing_student = db.query(models.Student).filter(
        models.Student.email == student.email
    ).first()

    if existing_student is not None:
        raise HTTPException(
            status_code=409,
            detail="This email already exists. Please use a different email."
        )

    new_student = models.Student(
        name=student.name,
        email=student.email,
        age=student.age,
        course=student.course,
        photo_data=student.photo_data
    )

    try:
        db.add(new_student)
        db.commit()
        db.refresh(new_student)

        return new_student

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=409,
            detail="This email already exists. Please use a different email."
        )



@app.get("/students/{student_id}")
def get_student(
    student_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    student = db.query(models.Student).filter(
        models.Student.id == student_id
    ).first()

    if student is None:
        raise HTTPException(
            status_code=404,
            detail="Student not found"
        )

    return student


@app.put("/students/{student_id}")
def update_student(
    student_id: int,
    student_data: schemas.StudentCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    student = db.query(models.Student).filter(
        models.Student.id == student_id
    ).first()

    if student is None:
        raise HTTPException(
            status_code=404,
            detail="Student not found"
        )

    student.name = student_data.name
    student.email = student_data.email
    student.age = student_data.age
    student.course = student_data.course
    student.photo_data = student_data.photo_data

    try:
        db.commit()
        db.refresh(student)
        return student
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="This email already exists. Please use a different email."
        )



@app.delete("/students/{student_id}")
def delete_student(
    student_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    student = db.query(models.Student).filter(
        models.Student.id == student_id
    ).first()

    if student is None:
        raise HTTPException(
            status_code=404,
            detail="Student not found"
        )

    try:
        deleted_id = student.id
        highest_id = db.query(func.max(models.Student.id)).scalar() or deleted_id
        id_offset = highest_id + 1

        db.delete(student)
        db.flush()

        db.execute(
            update(models.Student)
            .where(models.Student.id > deleted_id)
            .values(id=models.Student.id + id_offset)
            .execution_options(synchronize_session=False)
        )
        db.execute(
            update(models.Student)
            .where(models.Student.id > deleted_id + id_offset)
            .values(id=models.Student.id - id_offset - 1)
            .execution_options(synchronize_session=False)
        )

        if db.get_bind().dialect.name == "postgresql":
            db.execute(text(
                "SELECT setval("
                "pg_get_serial_sequence('students', 'id'), "
                "COALESCE(MAX(id), 1), "
                "MAX(id) IS NOT NULL"
                ") FROM students"
            ))

        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise

    return {
        "message": "Student deleted successfully",
        "student_id": student_id
    }
