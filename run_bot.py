import logging
import sys
from datetime import datetime, timedelta
from src.config import get_settings
from src.sheets_client import SheetsClient
from src.booking_manager import BookingManager, Booking
from src.availability import AvailabilityDashboard

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("BookingBot")

class CourtBookingBot:
    def __init__(self):
        self.settings = get_settings()
        self.client = SheetsClient(
            credentials_path=self.settings.google_credentials_path,
            sheet_id=self.settings.sheet_id
        )
        self.manager = BookingManager(self.client)
        self.dashboard = AvailabilityDashboard(self.client, self.manager)

    def initialize_sheet_structure(self):
        """Standardize Lean Facility Interface."""
        logger.info("Initializing Lean Facility Workspace...")
        try:
            # 1. Main Tabs
            required_tabs = [
                self.settings.bookings_sheet_name,
                self.settings.dashboard_sheet_name,
                self.settings.requests_sheet_name
            ]
            self.client.ensure_sheets_exist(required_tabs)
            
            # 2. Cleanup Junk
            for trash in ["⚙️ System Data", "⏳ Waiting List", "📁 Booking Archive", "🚫 Cancel My Booking", "Sheet1"]:
                self.client.delete_sheet_by_name(trash)

            # 3. Registry Headers
            db_headers = [["Date", "Time Slot", "Court", "Customer Name", "Phone", "Email", "Status", "Created At", "Notes"]]
            self.client.write_range(f"'{self.settings.bookings_sheet_name}'!A1:I1", db_headers)
            
            # 4. Input Headers
            req_headers = [["ACTION", "Date", "Time", "Court", "Name", "Phone", "Email", "Notes", "BOOKING_STATUS"]]
            self.client.write_range(f"'{self.settings.requests_sheet_name}'!A1:I1", req_headers)
            
            # 5. UI Controls
            dates = [(datetime.now() + timedelta(days=d)).strftime("%Y-%m-%d") for d in range(14)]
            times = [f"{h:02d}:00" for h in range(self.settings.operating_hours_start, self.settings.operating_hours_end)]
            courts = [str(c) for c in range(1, self.settings.court_count + 1)]
            actions = ["🆕 BOOKING", "🚫 CANCEL"]
            
            self.client.set_dropdown(self.settings.requests_sheet_name, "A2:A300", actions)
            self.client.set_dropdown(self.settings.requests_sheet_name, "B2:B300", dates)
            self.client.set_dropdown(self.settings.requests_sheet_name, "C2:C300", times)
            self.client.set_dropdown(self.settings.requests_sheet_name, "D2:D300", courts)

            logger.info("✅ Workspace is standardized.")
        except Exception as e:
            logger.error(f"Setup Warning: {e}")

    def process_unified_requests(self):
        """Atomic Transaction Processing with state-aware feedback."""
        self.manager.refresh_cache()
        rows = self.client.read_range(f"'{self.settings.requests_sheet_name}'!A2:I")
        
        if not rows: return 0

        processed = 0
        for i, row in enumerate(rows):
            row_idx = i + 2
            if not row: continue

            # State Logic
            action = str(row[0]).upper()
            status = str(row[8]) if len(row) >= 9 else ""
            
            if ("BOOK" in action or "🆕" in action) and "✅ BOOKED" in status:
                continue
            if ("CANCEL" in action or "🚫" in action) and "✅ CANCELLED" in status:
                continue

            if len(row) < 5: continue
            
            try:
                date_obj = datetime.strptime(str(row[1]).strip(), "%Y-%m-%d")
                time_str = str(row[2]).strip()
                court_num = int(float(row[3]))
                name_attr = str(row[4]).strip()

                if "BOOK" in action or "🆕" in action:
                    new_b = Booking(
                        date=date_obj, time_slot=time_str if ":" in time_str else f"{time_str}:00",
                        court=court_num, customer_name=name_attr,
                        phone=str(row[5]) if len(row) > 5 else "N/A",
                        email=str(row[6]) if len(row) > 6 else "N/A",
                        notes=str(row[7]) if len(row) > 7 else ""
                    )
                    success, msg = self.manager.create_booking(new_b)
                    final_status = f"✅ BOOKED" if success else f"❌ {msg}"
                
                elif "CANCEL" in action or "🚫" in action:
                    success, msg = self.manager.cancel_booking(date_obj, time_str, court_num, name_attr)
                    final_status = f"✅ CANCELLED" if success else f"❌ {msg}"
                
                else:
                    final_status = "❌ ACTION REQUIRED"

                self.client.update_cell(self.settings.requests_sheet_name, row_idx, 9, final_status)
                if success: processed += 1

            except Exception as e:
                self.client.update_cell(self.settings.requests_sheet_name, row_idx, 9, f"❌ DATA ERROR")

        return processed

    def run(self):
        print("\n" + "="*40)
        print("🏟️ EXECUTIVE FACILITY SYNC: ACTIVE")
        print("="*40)
        try:
            # 1. Standardize Environment
            self.initialize_sheet_structure()
            # 2. Execute Transactions
            count = self.process_unified_requests()
            # 3. CRITICAL: Refresh memory one more time before Dashboard update
            self.manager.refresh_cache()
            # 4. Render Fresh Dashboard
            self.dashboard.update_dashboard()
            
            print("="*40)
            print(f"✨ COMPLETED: {count} OPERATIONS SYNCED")
            print("="*40 + "\n")
        except Exception as e:
            logger.error(f"Sync Failure: {e}")
            sys.exit(1)

if __name__ == "__main__":
    bot = CourtBookingBot()
    bot.run()
