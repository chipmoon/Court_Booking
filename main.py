"""Main entry point for the badminton booking system."""

import sys
import logging
from datetime import datetime
from typing import Optional

from .config import get_settings
from .sheets_client import SheetsClient
from .booking_manager import BookingManager, Booking
from .availability import AvailabilityDashboard

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def initialize_components():
    """Initialize all system components."""
    settings = get_settings()
    
    sheets_client = SheetsClient(
        credentials_path=settings.google_credentials_path,
        sheet_id=settings.sheet_id
    )
    
    booking_manager = BookingManager(sheets_client)
    dashboard = AvailabilityDashboard(sheets_client, booking_manager)
    
    return sheets_client, booking_manager, dashboard


def cmd_update():
    """Update dashboard and check for conflicts (scheduled task)."""
    logger.info("=== Starting scheduled update ===")
    
    try:
        _, booking_manager, dashboard = initialize_components()
        
        # Update dashboard
        logger.info("Updating availability dashboard...")
        success = dashboard.update_dashboard()
        
        if not success:
            logger.error("Dashboard update failed")
            sys.exit(1)
        
        # Check for conflicts
        logger.info("Checking for booking conflicts...")
        conflicts = booking_manager.find_conflicts()
        
        if conflicts:
            logger.warning(f"Found {len(conflicts)} conflicts:")
            for conflict in conflicts:
                logger.warning(f"  {conflict}")
        else:
            logger.info("No conflicts found")
        
        logger.info("=== Update completed successfully ===")
        
    except Exception as e:
        logger.error(f"Update failed: {e}", exc_info=True)
        sys.exit(1)


def cmd_create_booking(
    date_str: str,
    time_slot: str,
    court: int,
    name: str,
    phone: str,
    email: str,
    notes: str = ""
):
    """Create a new booking from command line."""
    try:
        _, booking_manager, _ = initialize_components()
        
        # Parse date
        date = datetime.strptime(date_str, "%Y-%m-%d")
        
        # Create booking object
        booking = Booking(
            date=date,
            time_slot=time_slot,
            court=court,
            customer_name=name,
            phone=phone,
            email=email,
            notes=notes
        )
        
        # Create booking
        success, message, booking_id = booking_manager.create_booking(booking)
        
        if success:
            logger.info(f"✅ {message} (ID: {booking_id})")
        else:
            logger.error(f"❌ {message}")
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"Failed to create booking: {e}", exc_info=True)
        sys.exit(1)


def cmd_check_availability(date_str: str, court: Optional[int] = None):
    """Check available slots for a date."""
    try:
        _, booking_manager, dashboard = initialize_components()
        
        date = datetime.strptime(date_str, "%Y-%m-%d")
        
        slots = dashboard.get_available_slots(date, court)
        
        if slots:
            logger.info(f"Found {len(slots)} available slots for {date_str}:")
            for slot in slots:
                logger.info(f"  Court {slot['court']} at {slot['time']}")
        else:
            logger.info(f"No available slots for {date_str}")
            
    except Exception as e:
        logger.error(f"Failed to check availability: {e}", exc_info=True)
        sys.exit(1)


def cmd_init_sheet():
    """Initialize the Google Sheet with headers."""
    try:
        settings = get_settings()
        sheets_client = SheetsClient(
            credentials_path=settings.google_credentials_path,
            sheet_id=settings.sheet_id
        )
        
        # Write headers to Bookings sheet
        headers = [
            ["Booking ID", "Date", "Time Slot", "Court", "Customer Name", 
             "Phone", "Email", "Status", "Created At", "Notes"]
        ]
        
        sheets_client.write_range(f"{settings.bookings_sheet_name}!A1:J1", headers)
        
        # Write header to Dashboard sheet
        from dateutil import tz
        taiwan_tz = tz.gettz("Asia/Taipei")
        now_taiwan = datetime.now(taiwan_tz).strftime("%Y-%m-%d %H:%M")
        dashboard_header = [[f"📅 Weekly Court Availability - Updated: {now_taiwan} (Taipei Time)"]]
        sheets_client.write_range(f"{settings.dashboard_sheet_name}!A1:A1", dashboard_header)
        
        logger.info("✅ Sheet initialized successfully")
        
    except Exception as e:
        logger.error(f"Failed to initialize sheet: {e}", exc_info=True)
        sys.exit(1)


def main():
    """Main CLI entry point."""
    if len(sys.argv) < 2:
        print("Usage: python -m src.main <command> [args]")
        print("\nCommands:")
        print("  update                        - Update dashboard (for scheduled task)")
        print("  create <date> <time> <court> <name> <phone> <email> [notes]")
        print("  check <date> [court]          - Check availability")
        print("  init                          - Initialize sheet headers")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "update":
        cmd_update()
    
    elif command == "create":
        if len(sys.argv) < 8:
            print("Usage: create <date> <time> <court> <name> <phone> <email> [notes]")
            sys.exit(1)
        
        cmd_create_booking(
            date_str=sys.argv[2],
            time_slot=sys.argv[3],
            court=int(sys.argv[4]),
            name=sys.argv[5],
            phone=sys.argv[6],
            email=sys.argv[7],
            notes=sys.argv[8] if len(sys.argv) > 8 else ""
        )
    
    elif command == "check":
        if len(sys.argv) < 3:
            print("Usage: check <date> [court]")
            sys.exit(1)
        
        court = int(sys.argv[3]) if len(sys.argv) > 3 else None
        cmd_check_availability(sys.argv[2], court)
    
    elif command == "init":
        cmd_init_sheet()
    
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
