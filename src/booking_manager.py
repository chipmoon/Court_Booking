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

    def process_requests(self) -> int:
        """Process pending requests from the '📥 Booking Requests' sheet."""
        logger.info(f"Scanning '{settings.requests_sheet_name}' for new transactions...")
        
        # 1. Fetch data from requests sheet
        # Format: [ACTION, Date, Time, Court, Name, Phone, Email, Notes, BOOKING_STATUS]
        range_name = f"'{settings.requests_sheet_name}'!A2:I"
        rows = self.client.read_range(range_name)
        
        if not rows:
            logger.info("No requests found to process.")
            return 0

        processed_count = 0
        for i, row in enumerate(rows):
            row_idx = i + 2  # A2 is index 0
            if not row or not row[0]: continue

            action = str(row[0]).upper()
            status = str(row[8]) if len(row) >= 9 else ""
            
            # Skip already processed rows
            if "✅" in status: continue

            # FEEDBACK LOGIC: Provide status for incomplete rows
            if len(row) < 5 or not str(row[4]).strip(): 
                logger.warning(f"Row {row_idx} is missing required data (Name).")
                self.client.update_cell(settings.requests_sheet_name, row_idx, 9, "❌ MISSING NAME")
                continue
            
            try:
                # ROBUST PARSING: Handle potential float/string/empty variations
                raw_date = str(row[1]).strip()
                raw_time = str(row[2]).strip()
                raw_court = str(row[3]).strip()
                name_attr = str(row[4]).strip()

                # 1. Date Parsing
                try:
                    date_obj = datetime.strptime(raw_date, "%Y-%m-%d")
                except ValueError:
                    # Fallback for common spreadsheet formats
                    from dateutil import parser
                    date_obj = parser.parse(raw_date)

                # 2. Time Parsing (Handle Google Sheets time decimals)
                if ":" not in raw_time:
                    try:
                        # If it's a float duration (e.g. 0.5 for 12:00)
                        hours = float(raw_time) * 24
                        time_str = f"{int(hours):02d}:00"
                    except ValueError:
                        time_str = f"{raw_time}:00"
                else:
                    time_str = raw_time

                # 3. Court Parsing
                court_num = int(float(raw_court))

                if "BOOK" in action or "🆕" in action:
                    new_booking = Booking(
                        date=date_obj,
                        time_slot=time_str,
                        court=court_num,
                        customer_name=name_attr,
                        phone=str(row[5]) if len(row) > 5 else "N/A",
                        email=str(row[6]) if len(row) > 6 else "N/A",
                        notes=str(row[7]) if len(row) > 7 else ""
                    )
                    success, msg, _ = self.create_booking(new_booking)
                    final_status = f"✅ BOOKED" if success else f"❌ {msg}"
                
                elif "CANCEL" in action or "🚫" in action:
                    success, msg = self.cancel_booking(date_obj, time_str, court_num, name_attr)
                    final_status = f"✅ CANCELLED" if success else f"❌ {msg}"
                
                else:
                    final_status = "❌ UNKNOWN ACTION"
                    success = False

                # Update row status in sheet
                self.client.update_cell(settings.requests_sheet_name, row_idx, 9, final_status)
                if success: processed_count += 1

            except Exception as e:
                logger.error(f"Error processing row {row_idx}: {e}")
                self.client.update_cell(settings.requests_sheet_name, row_idx, 9, f"❌ DATA ERROR")

        return processed_count

    def archive_old_data(self) -> int:
        """Global Purge: Move past-date data from Registry and Requests to Archive."""
        archive_tab = "📜 Archive"
        self.client.ensure_sheets_exist([archive_tab])
        
        from dateutil import tz
        taiwan_tz = tz.gettz("Asia/Taipei")
        today = datetime.now(taiwan_tz).date()
        total_archived = 0

        # --- PHASE 1: Purge '📥 Booking Requests' ---
        logger.info(f"Phase 1: Purging {settings.requests_sheet_name}...")
        rows = self.client.read_range(f"'{settings.requests_sheet_name}'!A2:I")
        if rows:
            to_archive, to_keep = [], []
            for row in rows:
                if not row or not row[0]: continue
                status = str(row[8]) if len(row) >= 9 else ""
                try:
                    req_date = datetime.strptime(str(row[1]).strip(), "%Y-%m-%d").date()
                except:
                    req_date = today

                is_past = req_date < today
                is_success = "✅" in status
                
                if is_past or (is_success and is_past):
                    to_archive.append(row)
                else:
                    to_keep.append(row)

            if to_archive:
                self._batch_archive(archive_tab, to_archive)
                self.client.clear_range(f"'{settings.requests_sheet_name}'!A2:J500")
                if to_keep:
                    self.client.write_range(f"'{settings.requests_sheet_name}'!A2:I{len(to_keep) + 1}", to_keep)
                total_archived += len(to_archive)

        # --- PHASE 2: Purge 'Bookings' Registry ---
        logger.info(f"Phase 2: Purging {settings.bookings_sheet_name} Registry...")
        bookings = self.client.read_range(f"'{settings.bookings_sheet_name}'!A2:I")
        if bookings:
            to_archive_b, to_keep_b = [], []
            for b_row in bookings:
                if not b_row or not b_row[0]: continue
                try:
                    b_date = datetime.strptime(str(b_row[0]).strip(), "%Y-%m-%d").date()
                except:
                    b_date = today
                
                if b_date < today:
                    to_archive_b.append(b_row)
                else:
                    to_keep_b.append(b_row)

            if to_archive_b:
                self._batch_archive(archive_tab, to_archive_b)
                self.client.clear_range(f"'{settings.bookings_sheet_name}'!A2:I2000")
                if to_keep_b:
                    self.client.write_range(f"'{settings.bookings_sheet_name}'!A2:I{len(to_keep_b) + 1}", to_keep_b)
                total_archived += len(to_archive_b)

        return total_archived

    def _batch_archive(self, archive_tab: str, rows: list):
        """Helper to batch write rows into Archive."""
        try:
            archive_rows = self.client.read_range(f"'{archive_tab}'!A:A")
            next_row = len(archive_rows) + 1
            self.client.write_range(f"'{archive_tab}'!A{next_row}:I{next_row + len(rows) - 1}", rows)
        except Exception as e:
            logger.error(f"Batch archive failed: {e}")
            for row in rows: self.client.append_row(f"'{archive_tab}'!A:I", row)
