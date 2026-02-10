"""Expert Dashboard rendering engine with strict data integrity checks."""

import logging
from datetime import datetime, timedelta
from typing import List, Dict
from .sheets_client import SheetsClient
from .booking_manager import BookingManager, Booking
from .config import get_settings

logger = logging.getLogger(__name__)

class AvailabilityDashboard:
    def __init__(self, client: SheetsClient, manager: BookingManager):
        self.client = client
        self.manager = manager
        self.settings = get_settings()
        self.sheet_name = self.settings.dashboard_sheet_name

    def update_dashboard(self):
        """Force a fresh sync of the visual center."""
        logger.info("Syncing CEO Dashboard with latest registry data...")
        try:
            # 1. FORCE REFRESH: Pull latest state from 'Bookings' Sheet
            all_bookings = self.manager.refresh_cache()
            
            # 2. Map data for high-speed lookup
            lookup_map = self._create_lookup_map(all_bookings)
            
            # 3. Generate View
            view = self._generate_view(lookup_map)
            
            # 4. Write to Sheet (Atomic operation)
            self.client.write_range(f"'{self.sheet_name}'!A1:H100", view)
            logger.info("✅ Dashboard updated successfully (100% Fresh State).")
            return True
        except Exception as e:
            logger.error(f"Critical Dashboard Repair Required: {e}")
            return False

    def _create_lookup_map(self, bookings: List[Booking]) -> Dict[str, str]:
        """Creates a high-performance hash map for the generator."""
        lookup = {}
        for b in bookings:
            # Logic: If it's a cancellation, it shouldn't show up as '🔴'
            if "Booked" in b.status:
                key = f"{b.date.strftime('%Y-%m-%d')}_{b.time_slot}_{b.court}"
                lookup[key] = b.customer_name
        return lookup

    def _generate_view(self, lookup: Dict[str, str]) -> List[List[str]]:
        """Generates the 7-day visual matrix using enterprise settings."""
        from dateutil import tz
        taiwan_tz = tz.gettz("Asia/Taipei")
        now_taiwan = datetime.now(taiwan_tz).strftime("%Y-%m-%d %H:%M")
        
        start_date = datetime.now()
        dates = [start_date + timedelta(days=i) for i in range(7)]
        headers = ["Time Slot & Court"] + [d.strftime("%a %d/%m") for d in dates]
        
        view = [
            [f"📅 Court Availability Dashboard - Updated: {now_taiwan} (Taipei Time)"] + [""] * 7,
            headers
        ]
        
        # Pull constraints from settings for professional alignment
        start_h = self.settings.operating_hours_start
        end_h = self.settings.operating_hours_end
        court_count = self.settings.court_count
        
        for h in range(start_h, end_h):
            time_slot = f"{h:02d}:00"
            for court in range(1, court_count + 1):
                row = [f"Court {court} - {time_slot}"]
                for d in dates:
                    key = f"{d.strftime('%Y-%m-%d')}_{time_slot}_{court}"
                    if key in lookup:
                        row.append(f"🔴 {lookup[key]}")
                    else:
                        row.append("✅ Available")
                view.append(row)
        
        # Padding for a clean CEO UI
        for _ in range(30): view.append([""] * (len(dates) + 1))
        return view
