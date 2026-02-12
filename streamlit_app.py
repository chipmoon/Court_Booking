import os
import sys
import logging

# --- EXPERT RECOVERY: Environment Auditor ---
# Remove local shadowing and handle binary dependency conflicts
if os.path.exists(os.path.join(os.getcwd(), 'numpy')) or os.path.exists(os.path.join(os.getcwd(), 'pydantic')):
    sys.path = [p for p in sys.path if p != os.getcwd() and p != '']

def audit_environment():
    missing = []
    try:
        import numpy
    except ImportError: missing.append("numpy")
    try:
        import pandas
    except ImportError: missing.append("pandas")
    try:
        from pydantic_core import _pydantic_core
    except ImportError: missing.append("pydantic-core (binary extension)")
    try:
        import _cffi_backend
    except ImportError: missing.append("cffi (binary backend)")
    
    if missing:
        print(f"CRITICAL: Environment corruption detected for: {', '.join(missing)}")
        print("Tip: Use 'pip install --upgrade --force-reinstall pydantic pydantic-core' to repair.")
        # Attempt to continue regardless
    return missing

audit_environment()

try:
    import numpy as np
    import pandas as pd
except ImportError:
    # Silent fail as the Auditor already printed details
    pass

import streamlit as st
from datetime import datetime, timedelta
from src.config import get_settings
from src.sheets_client import SheetsClient
from src.booking_manager import BookingManager, Booking
from src.availability import AvailabilityDashboard
from dateutil import tz

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Page Configuration
st.set_page_config(
    page_title="Executive Badminton Court Manager",
    page_icon="🏸",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for Premium Look
st.markdown("""
<style>
    /* Main background */
    .stApp {
        background-color: #f8f9fa;
    }
    /* Headers */
    h1, h2, h3 {
        color: #1e3a5f;
        font-family: 'Outfit', sans-serif;
    }
    /* Metric styling */
    [data-testid="stMetricValue"] {
        font-size: 2rem;
        font-weight: 700;
        color: #2e7d32;
    }
    /* Card-like containers */
    .stCard {
        background-color: white;
        padding: 1.5rem;
        border-radius: 12px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        margin-bottom: 1rem;
    }
    /* Button styling */
    .stButton>button {
        border-radius: 8px;
        font-weight: 600;
        transition: all 0.3s ease;
    }
    .stButton>button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0,0,0,0.1);
    }
    /* Status indicators */
    .status-booked {
        color: #d32f2f;
        font-weight: bold;
    }
    .status-available {
        color: #388e3c;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# Initialization
@st.cache_resource
def get_components():
    settings = get_settings()
    
    # --- Expert Deploy: Secrets Management ---
    # On Streamlit Cloud, use Secrets. On local, fallback to JSON file.
    creds_info = None
    if "GOOGLE_CREDENTIALS" in st.secrets:
        creds_info = st.secrets["GOOGLE_CREDENTIALS"]
        # Streamlit secrets sometimes returns a string for multiline TOML or JSON
        if isinstance(creds_info, str):
            import json
            try:
                creds_info = json.loads(creds_info)
            except json.JSONDecodeError:
                st.error("❌ GOOGLE_CREDENTIALS secret is not a valid JSON string.")
                raise
    else:
        creds_info = settings.google_credentials_path

    sheets_client = SheetsClient(
        credentials_path=creds_info,
        sheet_id=settings.sheet_id
    )
    booking_manager = BookingManager(sheets_client)
    dashboard = AvailabilityDashboard(sheets_client, booking_manager)
    return settings, sheets_client, booking_manager, dashboard

settings, sheets_client, booking_manager, dashboard = get_components()

# Helper Functions
def get_taipei_now():
    return datetime.now(tz.gettz("Asia/Taipei"))

def format_availability_df(bookings, days=7):
    taiwan_now = get_taipei_now()
    start_date = taiwan_now.replace(hour=0, minute=0, second=0, microsecond=0)
    dates = [start_date + timedelta(days=i) for i in range(days)]
    
    # Create lookup map
    lookup = {}
    for b in bookings:
        if "Booked" in b.status:
            key = f"{b.date.strftime('%Y-%m-%d')}_{b.time_slot}_{b.court}"
            lookup[key] = b.customer_name

    data = []
    start_h = settings.operating_hours_start
    end_h = settings.operating_hours_end
    court_count = settings.court_count
    
    for h in range(start_h, end_h):
        time_slot = f"{h:02d}:00"
        for court in range(1, court_count + 1):
            row = {"Slot": f"Court {court} ({time_slot})"}
            for d in dates:
                date_str = d.strftime("%Y-%m-%d")
                col_name = d.strftime("%a %d/%m")
                key = f"{date_str}_{time_slot}_{court}"
                if key in lookup:
                    row[col_name] = f"🔴 {lookup[key]}"
                else:
                    row[col_name] = "✅ Available"
            data.append(row)
    
    return pd.DataFrame(data)

# Sidebar
with st.sidebar:
    st.image("https://img.icons8.com/isometric/512/badminton.png", width=100)
    st.title("Settings & Actions")
    
    if st.button("🔄 Sync with Google Sheets", use_container_width=True):
        with st.spinner("Synchronizing data..."):
            processed = booking_manager.process_requests()
            booking_manager.refresh_cache()
            dashboard.update_dashboard()
            st.success(f"Synced! Processed {processed} requests.")
            st.rerun()
            
    st.divider()
    st.info("System Status: Online ✅")
    st.caption(f"Last updated: {get_taipei_now().strftime('%H:%M:%S')}")

# Main Content
st.title("🏸 Executive Badminton Court Manager")
st.subheader("High-Performance Facility Control")

tabs = st.tabs(["📊 Occupancy Dashboard", "📝 Quick Booking", "⚙️ Management"])

# Tab 1: Dashboard
with tabs[0]:
    col1, col2, col3, col4 = st.columns(4)
    
    # Refresh cache for latest data
    bookings = booking_manager.get_all_bookings()
    
    # Metrics
    today_str = get_taipei_now().strftime("%Y-%m-%d")
    today_bookings = [b for b in bookings if b.date.strftime("%Y-%m-%d") == today_str and "Booked" in b.status]
    total_slots = (settings.operating_hours_end - settings.operating_hours_start) * settings.court_count
    occupancy = (len(today_bookings) / total_slots) * 100 if total_slots > 0 else 0
    
    with col1:
        st.metric("Today's Bookings", len(today_bookings))
    with col2:
        st.metric("Occupancy Rate", f"{occupancy:.1f}%")
    with col3:
        st.metric("Active Courts", settings.court_count)
    with col4:
        st.metric("Next 7 Days", sum(1 for b in bookings if b.date.date() >= get_taipei_now().date()))

    st.markdown("### 🗓️ Visual Availability Matrix")
    df = format_availability_df(bookings)
    
    # Display table with formatting
    def color_cells(val):
        if "🔴" in str(val):
            return 'background-color: #ffebee; color: #c62828;'
        elif "✅" in str(val):
            return 'background-color: #e8f5e9; color: #2e7d32;'
        return ''

    st.dataframe(
        df.style.applymap(color_cells, subset=df.columns[1:]),
        height=600,
        use_container_width=True,
        hide_index=True
    )

# Tab 2: Quick Booking
with tabs[1]:
    st.markdown("### 🆕 Create New Reservation")
    
    with st.form("booking_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            date = st.date_input("Select Date", min_value=get_taipei_now().date(), max_value=get_taipei_now().date() + timedelta(days=settings.max_advance_days))
            time_slot = st.selectbox("Select Time", [f"{h:02d}:00" for h in range(settings.operating_hours_start, settings.operating_hours_end)])
            court = st.number_input("Court Number", min_value=1, max_value=settings.court_count, value=1)
        
        with c2:
            name = st.text_input("Customer Name", placeholder="e.g. John Doe")
            phone = st.text_input("Phone Number", placeholder="e.g. 0912-345-678")
            email = st.text_input("Email", placeholder="john@example.com")
            
        notes = st.text_area("Notes", placeholder="Special requests...")
        
        submit = st.form_submit_button("Submit Request", use_container_width=True)
        
        if submit:
            if not name:
                st.error("Customer name is required.")
            else:
                new_booking = Booking(
                    date=datetime.combine(date, datetime.min.time()),
                    time_slot=time_slot,
                    court=court,
                    customer_name=name,
                    phone=phone,
                    email=email,
                    notes=notes,
                    status="🔴 Booked"
                )
                
                success, msg, _ = booking_manager.create_booking(new_booking)
                if success:
                    st.success(f"✅ Booking Confirmed: {name} at {time_slot} (Court {court})")
                    # Update local cache and dashboard
                    booking_manager.refresh_cache()
                    dashboard.update_dashboard()
                else:
                    st.error(f"❌ Failed: {msg}")

# Tab 3: Management
with tabs[2]:
    st.markdown("### 📋 Booking Registry")
    
    search = st.text_input("Search (Name, Phone, or Court)", "")
    
    # 1. Populate Registry Data first
    reg_data = []
    for b in bookings:
        if search.lower() in b.customer_name.lower() or search in b.phone or search in str(b.court):
            reg_data.append({
                "Date": b.date.strftime("%Y-%m-%d"),
                "Time": b.time_slot,
                "Court": b.court,
                "Customer": b.customer_name,
                "Phone": b.phone,
                "Status": b.status,
                "Notes": b.notes
            })

    # 2. Analytics Section (using reg_data)
    st.markdown("#### 📈 Utilization Analytics")
    if reg_data:
        import plotly.express as px
        reg_df = pd.DataFrame(reg_data)
        
        c1, c2 = st.columns(2)
        with c1:
            # Time slot popularity
            time_counts = reg_df[reg_df['Status'].str.contains("Booked")]['Time'].value_counts().reset_index()
            time_counts.columns = ['Time Slot', 'Bookings']
            fig_time = px.bar(time_counts, x='Time Slot', y='Bookings', title="Bookings by Time Slot", color_discrete_sequence=['#1e3a5f'])
            st.plotly_chart(fig_time, use_container_width=True)
            
        with c2:
            # Court popularity
            court_counts = reg_df[reg_df['Status'].str.contains("Booked")]['Court'].value_counts().reset_index()
            court_counts.columns = ['Court', 'Bookings']
            fig_court = px.pie(court_counts, names='Court', values='Bookings', title="Court Utilization", hole=0.4)
            st.plotly_chart(fig_court, use_container_width=True)

    if reg_data:
        st.dataframe(pd.DataFrame(reg_data), use_container_width=True, hide_index=True)
    else:
        st.write("No matching records found.")

    st.divider()
    
    st.markdown("### 🧹 Advanced Purge")
    st.warning("Archiving will move all processed or past-dated bookings to the Archive sheet.")
    if st.button("Archive Old Data", type="secondary"):
        with st.spinner("Archiving..."):
            count = booking_manager.archive_old_data()
            st.success(f"Successfully archived {count} records.")
            st.rerun()

# Footer
st.divider()
st.caption("Developed by AI Expert Framework | Version 2.0 Premium")
