
import re

from pydantic import BaseModel, EmailStr, Field, validator

class StudentCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    age: int = Field(gt=0, le=120)
    course: str = Field(min_length=2, max_length=100)
    photo_data: str | None = Field(
        default=None,
        max_length=700_000
    )

    @validator("photo_data")
    def validate_photo_data(cls, value):
        if value is not None and not re.fullmatch(
            r"data:image/jpeg;base64,[A-Za-z0-9+/]+={0,2}", value
        ):
            raise ValueError("Photo must be a base64-encoded JPEG image")
        return value

class UserCreate(BaseModel):
    name: str
    email: str
    password: str

class UserLogin(BaseModel):
    email: str
    password: str