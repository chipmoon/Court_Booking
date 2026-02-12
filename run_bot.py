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

            # --- PREMIUM DECORATION (Mobile Friendly) ---
            req_sheet = self.settings.requests_sheet_name
            # 1. Header Styling
            header_bg = {"red": 0.17, "green": 0.24, "blue": 0.31} # Dark Blue/Grey
            header_text = {"red": 1.0, "green": 1.0, "blue": 1.0}
            self.client.format_cells(req_sheet, "A1:I1", bg_color=header_bg, text_color=header_text, bold=True, font_size=12, horizontal_alignment="CENTER")
            
            # 2. Touch-Friendly Rows (Larger selection area)
            self.client.set_row_height(req_sheet, 0, 300, 45)
            self.client.set_column_width(req_sheet, 0, 9, 120) # Standard width
            self.client.set_column_width(req_sheet, 8, 9, 200) # Status Notes wider
            
            # 3. Conditional Color Branding
            rules = [
                {"text": "🆕 BOOKING", "bg_color": {"red": 0.82, "green": 0.94, "blue": 0.85}, "text_color": {"red": 0.1, "green": 0.4, "blue": 0.1}},
                {"text": "🚫 CANCEL", "bg_color": {"red": 0.98, "green": 0.85, "blue": 0.85}, "text_color": {"red": 0.6, "green": 0.1, "blue": 0.1}},
                {"text": "✅", "bg_color": {"red": 0.8, "green": 1.0, "blue": 0.8}},
                {"text": "❌", "bg_color": {"red": 1.0, "green": 0.8, "blue": 0.8}},
                {"text": "DONE", "bg_color": {"red": 0.85, "green": 1.0, "blue": 0.85}},
                {"text": "ERROR", "bg_color": {"red": 1.0, "green": 0.85, "blue": 0.85}}
            ]
            self.client.add_conditional_formatting(req_sheet, "A2:A300", rules[:2]) # Actions
            self.client.add_conditional_formatting(req_sheet, "I2:I300", rules[2:]) # Status

            logger.info("✅ Workspace is standardized with Premium UI.")
        except Exception as e:
            logger.error(f"Setup Warning: {e}")

    def process_unified_requests(self):
        """Atomic Transaction Processing using centralized manager logic."""
        return self.manager.process_requests()

    def run(self):
        print("\n" + "="*40)
        print("EXECUTIVE FACILITY SYNC: ACTIVE")
        print("="*40)
        try:
            # 1. Standardize Environment
            self.initialize_sheet_structure()
            # 2. Execute Transactions
            count = self.process_unified_requests()
            # 3. CRITICAL: Refresh memory one more time before Dashboard update
            self.manager.refresh_cache()
            
            # 4. Archive old processed data (Elon Musk: Global Cleanup)
            logger.info("Archiving old data (Global Purge)...")
            self.manager.archive_old_data()
            
            # 5. Render Fresh Dashboard
            self.dashboard.update_dashboard()
            
            print("="*40)
            print(f"COMPLETED: {count} OPERATIONS SYNCED")
            print("="*40 + "\n")
        except Exception as e:
            logger.error(f"Sync Failure: {e}")
            sys.exit(1)

if __name__ == "__main__":
    bot = CourtBookingBot()
    bot.run()
