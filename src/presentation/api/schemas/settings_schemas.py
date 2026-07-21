from pydantic import BaseModel


class UserSettingsResponse(BaseModel):
    display_name: str
    timezone: str
    language: str


class UserSettingsUpdateRequest(BaseModel):
    display_name: str | None = None
    timezone: str | None = None
    language: str | None = None
