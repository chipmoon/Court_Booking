"""Core booking management logic with Lean validation."""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional
import logging

from .sheets_client import SheetsClient
from .config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

@dataclass
class Booking:
    date: datetime
    time_slot: str
    court: int
    customer_name: str
    phone: str
    email: str
    status: str = "🔴 Booked"
    created_at: Optional[datetime] = None
    notes: str = ""

    def to_row(self) -> List[str]:
        return [
            self.date.strftime("%Y-%m-%d"),
            self.time_slot,
            str(self.court),
            self.customer_name,
            self.phone,
            self.email,
            self.status,
            (self.created_at or datetime.now()).strftime("%Y-%m-%d %H:%M:%S"),
            self.notes,
        ]

    @classmethod
    def from_row(cls, row: List[str]) -> "Booking":
        return cls(
            date=datetime.strptime(str(row[0]).strip(), "%Y-%m-%d"),
            time_slot=str(row[1]).strip(),
            court=int(float(row[2])),
            customer_name=str(row[3]).strip(),
            phone=str(row[4]).strip() if len(row) > 4 else "N/A",
            email=str(row[5]).strip() if len(row) > 5 else "N/A",
            status=str(row[6]).strip() if len(row) > 6 else "🔴 Booked",
            created_at=datetime.strptime(str(row[7]).strip(), "%Y-%m-%d %H:%M:%S") if len(row) > 7 else None,
            notes=str(row[8]).strip() if len(row) > 8 else "",
        )

class BookingManager:
    def __init__(self, sheets_client: SheetsClient):
        self.client = sheets_client
        self.sheet_name = settings.bookings_sheet_name
        self._cached_bookings = []

    def refresh_cache(self):
        """Fetch rows and update local memory."""
        range_name = f"'{self.sheet_name}'!A2:I"
        rows = self.client.read_range(range_name)
        self._cached_bookings = []
        for row in rows:
            if len(row) >= 4 and row[0]:
                try:
                    self._cached_bookings.append(Booking.from_row(row))
                except Exception:
                    continue
        return self._cached_bookings

    def get_all_bookings(self) -> List[Booking]:
        """Compatibility method for Availability Dashboard."""
        if not self._cached_bookings:
            return self.refresh_cache()
        return self._cached_bookings

    def check_availability(self, date: datetime, time_slot: str, court: int) -> bool:
        """Atomic check against local cache."""
        for b in self._cached_bookings:
            if (b.date.date() == date.date() and 
                b.time_slot == time_slot and 
                b.court == court and 
                "Booked" in b.status):
                return False
        return True

    def create_booking(self, booking: Booking) -> tuple[bool, str, Optional[int]]:
        if not self.check_availability(booking.date, booking.time_slot, booking.court):
            return False, "ALREADY RESERVED", None
        
        try:
            row_num = self.client.append_row(f"'{self.sheet_name}'!A:I", booking.to_row())
            self._cached_bookings.append(booking)
            return True, "BOOKED", row_num
        except Exception as e:
            return False, f"DB ERROR: {str(e)}", None

    def cancel_booking(self, date: datetime, time_slot: str, court: int, name: str) -> tuple[bool, str]:
        self.refresh_cache()
        target_date = date.date()
        target_name = str(name).lower().strip()
        
        for i, b in enumerate(self._cached_bookings):
            if (b.date.date() == target_date and 
                b.time_slot == str(time_slot).strip() and 
                b.court == int(float(court)) and 
                b.customer_name.lower().strip() == target_name and
                "Booked" in b.status):
                
                row_idx = i + 2
                self.client.update_cell(self.sheet_name, row_idx, 7, "⚪ Cancelled")
                return True, "RELEASED"
        return False, "BOOKING NOT FOUND"

    def find_conflicts(self) -> List[str]:
        """Identify overbooked slots in the current registry."""
        conflicts = []
        schedule = {}
        
        for b in self._cached_bookings:
            if "Booked" in b.status:
                key = f"{b.date.strftime('%Y-%m-%d')}_{b.time_slot}_{b.court}"
                if key in schedule:
                    conflicts.append(f"Conflict on {key}: {schedule[key]} and {b.customer_name}")
                else:
                    schedule[key] = b.customer_name
        return conflicts
