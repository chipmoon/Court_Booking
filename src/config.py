"""Configuration settings for the booking system."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Google Sheets Configuration
    google_credentials_path: str = Field(
        default="src/courts-booking-486806-7c08bb58bd0e.json",
        validation_alias="GOOGLE_CREDENTIALS_PATH"
    )
    sheet_id: str = Field(
        default="1NA39HlBPM3pK7DKANCp12ZKPZgzgR_k6YqhN-rbqlyc",
        validation_alias="SHEET_ID"
    )
    bookings_sheet_name: str = "Bookings"
    dashboard_sheet_name: str = "Availability Dashboard"
    requests_sheet_name: str = "📥 Booking Requests"

    # Booking Rules
    max_advance_days: int = 14
    court_count: int = 4
    operating_hours_start: int = 8
    operating_hours_end: int = 22
    slot_duration_hours: int = 1
    max_bookings_per_user_per_week: int = 5

    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8",
        extra="ignore"
    )

def get_settings():
    return Settings()
