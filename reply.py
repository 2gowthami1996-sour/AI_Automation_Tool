# reply.py
import streamlit as st
import datetime, os, imaplib, email, smtplib, psycopg2
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from openai import OpenAI
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# ================================
# CONFIGURATION
# ================================
SCOPES = ["https://www.googleapis.com/auth/calendar"]
CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.json"

EMAIL = "thridorbit03@gmail.com"
PASSWORD = "ouhc mftv huww liru"

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
IMAP_SERVER = "imap.gmail.com"
IMAP_PORT = 993

POSTGRES_URL = "postgresql://neondb_owner:npg_onVe8gqWs4lm@ep-solitary-bush-addf9gpm-pooler.c-2.us-east-1.aws.neon.tech/neondb?sslmode=require"

WORK_START_HOUR = 10
WORK_END_HOUR = 18
SLOT_DURATION_MIN = 30
DAYS_AHEAD = 7
OTHER_SERVICES_LINK = "https://www.morphius.in/services"

try:
    client = OpenAI(api_key=st.secrets["openai"]["api_key"])
except:
    client = OpenAI(api_key="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")

# ================================
# GOOGLE CALENDAR
# ================================
def get_calendar_service():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                st.error("Missing credentials.json. Please upload.")
                return None
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())
    return build("calendar", "v3", credentials=creds)

def get_busy_slots(service):
    now = datetime.datetime.utcnow()
    end = now + datetime.timedelta(days=DAYS_AHEAD)
    events_result = service.events().list(
        calendarId="primary", timeMin=now.isoformat()+"Z", timeMax=end.isoformat()+"Z",
        singleEvents=True, orderBy="startTime"
    ).execute()
    busy = []
    for e in events_result.get("items", []):
        start = e["start"].get("dateTime")
        end = e["end"].get("dateTime")
        if start and end:
            busy.append((
                datetime.datetime.fromisoformat(start.replace("Z","+00:00")),
                datetime.datetime.fromisoformat(end.replace("Z","+00:00"))
            ))
    return busy

def get_available_slots(service):
    now = datetime.datetime.utcnow() + datetime.timedelta(hours=5, minutes=30)
    end_time = now + datetime.timedelta(days=DAYS_AHEAD)
    busy = get_busy_slots(service)
    slots = []
    current = now.replace(minute=0, second=0, microsecond=0)
    while current < end_time:
        if current.weekday() < 5 and WORK_START_HOUR <= current.hour < WORK_END_HOUR:
            slot_end = current + datetime.timedelta(minutes=SLOT_DURATION_MIN)
            if not any(s < slot_end and e > current for s, e in busy):
                slots.append(current)
        current += datetime.timedelta(minutes=SLOT_DURATION_MIN)
    return slots

def create_meeting(service, email_addr, start):
    end = start + datetime.timedelta(minutes=SLOT_DURATION_MIN)
    event = {
        "summary": f"Morphius AI Demo with {email_addr}",
        "description": "Discussion about AI Automation Solutions.",
        "start": {"dateTime": start.isoformat(), "timeZone": "Asia/Kolkata"},
        "end": {"dateTime": end.isoformat(), "timeZone": "Asia/Kolkata"},
        "attendees": [{"email": email_addr}, {"email": EMAIL}],
        "conferenceData": {"createRequest": {"requestId": f"meet-{datetime.datetime.now().timestamp()}"}}
    }
    created = service.events().insert(calendarId="primary", body=event, conferenceDataVersion=1).execute()
    return created.get("hangoutLink"), start

# ================================
# DATABASE
# ================================
def get_db_connection():
    try:
        return psycopg2.connect(POSTGRES_URL)
    except Exception as e:
        st.error(f"DB connection failed: {e}")
        return None

def setup_db(conn):
    with conn.cursor() as cur:
        cur.execute("""
        CREATE TABLE IF NOT EXISTS meetings (
            id SERIAL PRIMARY KEY,
            email TEXT,
            meet_time TIMESTAMPTZ,
            meet_link TEXT,
            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        );
        """)
    conn.commit()

def log_meeting(conn, email, meet_time, link):
    with conn.cursor() as cur:
        cur.execute("INSERT INTO meetings (email, meet_time, meet_link) VALUES (%s, %s, %s)", (email, meet_time, link))
    conn.commit()

# ================================
# STREAMLIT APP
# ================================
def main():
    st.set_page_config(page_title="Morphius Scheduler", page_icon="📅")
    st.title("📅 Morphius AI Smart Scheduler")

    conn = get_db_connection()
    if not conn:
        return
    setup_db(conn)

    # ✅ Correct query parameter handling (works on Streamlit Cloud)
    query_params = st.query_params
    email_param = query_params.get("email", None)

    if email_param:
        user_email = email_param[0] if isinstance(email_param, list) else email_param
        st.subheader(f"Welcome {user_email} 👋")
        st.write("Please choose an available meeting slot:")

        service = get_calendar_service()
        if not service:
            return
        slots = get_available_slots(service)
        if not slots:
            st.warning("No available slots this week. Please try later.")
            return

        grouped = {}
        for s in slots:
            d = s.strftime("%A, %d %B %Y")
            grouped.setdefault(d, []).append(s.strftime("%I:%M %p"))

        chosen_date = st.selectbox("Select Date", list(grouped.keys()))
        chosen_time = st.selectbox("Select Time", grouped[chosen_date])

        if st.button("Confirm Booking"):
            start_str = f"{chosen_date} {chosen_time}"
            start_dt = datetime.datetime.strptime(start_str, "%A, %d %B %Y %I:%M %p")
            meet_link, start = create_meeting(service, user_email, start_dt)
            log_meeting(conn, user_email, start, meet_link)
            st.success(f"✅ Meeting booked!\n\n🕓 {start.strftime('%A, %d %B %Y %I:%M %p')}\n📍 {meet_link}")
        return

    # Default (no email parameter)
    st.info("To book a meeting, open this link sent in your email.")
    st.caption("Example: https://aiautomationtool-9criyayngv3srzouygnaiy.streamlit.app/?email=client@gmail.com")

if __name__ == "__main__":
    main()
