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
    initial_sidebar_state="collapsed", # Better for mobile first view
)

# Custom CSS for Premium Look & Mobile Optimization
st.markdown("""
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&family=Plus+Jakarta+Sans:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
    :root {
        --primary: #1e3a8a;
        --secondary: #3b82f6;
        --success: #10b981;
        --error: #ef4444;
        --bg: #f8fafc;
        --card-bg: rgba(255, 255, 255, 0.85);
        --text: #1e293b;
        --transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    }

    /* Main background */
    .stApp {
        background: radial-gradient(circle at top right, #e0e7ff 0%, #f8fafc 100%);
        font-family: 'Plus Jakarta Sans', sans-serif;
        color: var(--text);
    }

    /* Headers */
    h1, h2, h3 {
        font-family: 'Outfit', sans-serif !important;
        font-weight: 700 !important;
        letter-spacing: -0.02em;
    }

    /* Professional Card styling */
    .glass-card {
        background: var(--card-bg);
        backdrop-filter: blur(12px);
        -webkit-backdrop-filter: blur(12px);
        border: 1px solid rgba(255, 255, 255, 0.3);
        padding: 1.5rem;
        border-radius: 20px;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.05);
        margin-bottom: 1rem;
        transition: var(--transition);
    }
    .glass-card:hover {
        transform: translateY(-4px);
        box-shadow: 0 12px 48px rgba(0, 0, 0, 0.08);
    }

    /* Metric Customization */
    [data-testid="stMetricValue"] {
        font-family: 'Outfit', sans-serif;
        font-weight: 700;
        color: var(--primary);
    }
    [data-testid="stMetricLabel"] {
        font-weight: 500;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        font-size: 0.8rem;
    }

    /* Mobile adjustments */
    @media (max-width: 768px) {
        .stMetric {
            background: white;
            padding: 10px;
            border-radius: 15px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.03);
            margin-bottom: 10px;
        }
        h1 { font-size: 1.8rem !important; }
        .stTabs [data-baseweb="tab-list"] {
            gap: 10px;
        }
        .stTabs [data-baseweb="tab"] {
            padding: 8px 12px;
            font-size: 0.9rem;
        }
    }

    /* Button styling */
    div.stButton > button {
        background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 100%);
        color: white;
        border: none;
        padding: 0.6rem 1.2rem;
        border-radius: 12px;
        font-weight: 600;
        transition: var(--transition);
        width: 100%;
    }
    div.stButton > button:hover {
        opacity: 0.9;
        transform: scale(1.02);
    }

    /* Table/Dataframe overrides */
    .stDataFrame {
        border-radius: 15px;
        overflow: hidden;
    }

    /* ULTRA-SHARP TAB OPTIMIZATION */
    /* Target the tab text with extra-bold weight and high-definition rendering */
    div[data-baseweb="tab"] p {
        font-size: 1.1rem !important; /* Slightly larger for better tap targets */
        font-weight: 800 !important; /* Extra Bold for maximum sharpness */
        letter-spacing: 0.5px !important; /* Prevent letter crowding */
        color: #000000 !important; /* Absolute Black for extreme contrast */
        -webkit-font-smoothing: antialiased;
        -moz-osx-font-smoothing: grayscale;
        text-rendering: optimizeLegibility;
        transition: var(--transition);
    }

    /* Active tab text - Ultra Sharp Red */
    div[aria-selected="true"] p {
        color: #FF0000 !important; /* Pure High-Vis Red */
        text-shadow: 0 0 1px rgba(255,0,0,0.1); /* Subtle depth without blurring */
    }

    /* Active tab indicator (the line underneath) */
    div[data-baseweb="tab-highlight"] {
        background-color: #dc2626 !important;
    }

    /* Hover effect for tabs */
    div[data-baseweb="tab"]:hover p {
        color: #2563eb !important; /* Blue on hover */
    }

    /* Mobile tab adjustments */
    @media (max-width: 768px) {
        div[data-baseweb="tab"] {
            padding-left: 10px !important;
            padding-right: 10px !important;
        }
        div[data-baseweb="tab"] p {
            font-size: 0.85rem !important;
        }
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
# Professional Header with Status Badge
st.markdown(f"""
<div style="background: linear-gradient(90deg, #1e3a8a 0%, #3b82f6 100%); padding: 2rem; border-radius: 24px; color: white; margin-bottom: 2rem; box-shadow: 0 10px 25px rgba(30, 58, 138, 0.2);">
    <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 1rem;">
        <div>
            <h1 style="color: white !important; margin: 0; font-size: 2.2rem; display: flex; align-items: center; gap: 15px;">
                🏸 Executive Court <span style="font-weight: 300; opacity: 0.9;">Manager</span>
            </h1>
            <p style="margin: 5px 0 0 0; opacity: 0.8; font-family: 'Plus Jakarta Sans';">Elite Facility Intelligence & Orchestration</p>
        </div>
        <div style="background: rgba(255,255,255,0.2); backdrop-filter: blur(10px); padding: 8px 16px; border-radius: 50px; border: 1px solid rgba(255,255,255,0.3); display: flex; align-items: center; gap: 8px;">
            <div style="width: 10px; height: 10px; background: #10b981; border-radius: 50%; box-shadow: 0 0 10px #10b981;"></div>
            <span style="font-size: 0.85rem; font-weight: 600; letter-spacing: 0.5px;">SYSTEM LIVE</span>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

tabs = st.tabs(["📊 DASHBOARD", "📝 NEW BOOKING", "⚙️ OPERATIONS"])

# Tab 1: Dashboard
with tabs[0]:
    # Custom Metrics with Premium Look
    bookings = booking_manager.get_all_bookings()
    today_str = get_taipei_now().strftime("%Y-%m-%d")
    today_bookings = [b for b in bookings if b.date.strftime("%Y-%m-%d") == today_str and "Booked" in b.status]
    total_slots = (settings.operating_hours_end - settings.operating_hours_start) * settings.court_count
    occupancy = (len(today_bookings) / total_slots) * 100 if total_slots > 0 else 0
    
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("Today's Work", len(today_bookings), delta=f"{occupancy:.1f}% Use")
    with m2:
        st.metric("Total Courts", settings.court_count)
    with m3:
        st.metric("Upcoming", sum(1 for b in bookings if b.date.date() >= get_taipei_now().date()))
    with m4:
        st.metric("Status", "Online", delta="Stable")

    st.markdown("---")
    
    # MOBILE OPTIMIZATION: Day Selection
    st.markdown("### 🗓️ Availability Matrix")
    
    all_dates = [(get_taipei_now() + timedelta(days=i)).strftime("%a %d/%m") for i in range(7)]
    selected_day = st.selectbox(
        "📱 Mobile View: Select Day to Zoom In", 
        ["View All Days (Desktop)"] + all_dates,
        index=0
    )
    
    df = format_availability_df(bookings)
    
    # Filter DF if a specific day is selected
    display_df = df.copy()
    if selected_day != "View All Days (Desktop)":
        display_df = df[["Slot", selected_day]]

    # Display table with formatting
    def color_cells(val):
        if "🔴" in str(val):
            return 'background-color: #fee2e2; color: #991b1b; font-weight: bold; border-left: 4px solid #ef4444;'
        elif "✅" in str(val):
            return 'background-color: #f0fdf4; color: #166534; opacity: 0.9;'
        return ''

    st.dataframe(
        display_df.style.applymap(color_cells, subset=display_df.columns[1:]),
        height=550 if selected_day == "View All Days (Desktop)" else 400,
        use_container_width=True,
        hide_index=True
    )
    
    st.caption("💡 Tip: Click 'Slot' headings to sort. Cell-phone users should select a specific day for the best experience.")

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
st.markdown("---")
f1, f2 = st.columns([2, 1])
with f1:
    st.markdown("""
    <div style="opacity: 0.6; font-size: 0.85rem;">
        <strong>© 2024 Executive Facility Systems</strong><br>
        Built with High-Performance Python & Streamlit Resilience Engine
    </div>
    """, unsafe_allow_html=True)
with f2:
    st.markdown(f"""
    <div style="text-align: right; opacity: 0.6; font-size: 0.85rem;">
        v4.0.2 Premium Edition<br>
        Node Status: <span style="color: #10b981;">Online</span>
    </div>
    """, unsafe_allow_html=True)
