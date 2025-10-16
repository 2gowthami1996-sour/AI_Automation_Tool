import imaplib, email, smtplib, time, datetime, psycopg2
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

EMAIL = "thridorbit03@gmail.com"
PASSWORD = "ouhc mftv huww liru"
SMTP_SERVER = "smtp.gmail.com"
IMAP_SERVER = "imap.gmail.com"
SMTP_PORT = 587

POSTGRES_URL = "postgresql://neondb_owner:npg_onVe8gqWs4lm@ep-solitary-bush-addf9gpm-pooler.c-2.us-east-1.aws.neon.tech/neondb?sslmode=require"
BOOKING_URL_BASE = "https://aiautomationtool-9criyayngv3srzouygnaiy.streamlit.app/?email="
OTHER_SERVICES_URL = "https://www.morphius.in/services"

# ================================
# DATABASE SETUP
# ================================
def get_db_connection():
    return psycopg2.connect(POSTGRES_URL)

def setup_db(conn):
    with conn.cursor() as cur:
        cur.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id SERIAL PRIMARY KEY,
            email TEXT UNIQUE,
            last_contacted TIMESTAMP,
            followups_sent INT DEFAULT 0,
            status TEXT DEFAULT 'pending'  -- pending / booked / not_interested / unsubscribed
        );
        """)
    conn.commit()

# ================================
# EMAIL UTILITIES
# ================================
def send_email(to_email, subject, body):
    msg = MIMEMultipart()
    msg["From"] = EMAIL
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "html"))

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(EMAIL, PASSWORD)
        server.send_message(msg)
    print(f"✅ Sent email to {to_email}: {subject}")

def fetch_replies():
    mail = imaplib.IMAP4_SSL(IMAP_SERVER)
    mail.login(EMAIL, PASSWORD)
    mail.select("inbox")
    status, data = mail.search(None, '(UNSEEN)')
    emails = []
    for num in data[0].split():
        status, msg_data = mail.fetch(num, '(RFC822)')
        msg = email.message_from_bytes(msg_data[0][1])
        sender = email.utils.parseaddr(msg["From"])[1]
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    body += part.get_payload(decode=True).decode()
        else:
            body = msg.get_payload(decode=True).decode()
        emails.append((sender, body.lower()))
    return emails

# ================================
# LOGIC
# ================================
def process_leads():
    conn = get_db_connection()
    setup_db(conn)

    replies = fetch_replies()
    for sender, body in replies:
        with conn.cursor() as cur:
            cur.execute("SELECT followups_sent, status FROM leads WHERE email=%s", (sender,))
            row = cur.fetchone()

        if not row:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO leads (email) VALUES (%s)", (sender,))
                conn.commit()

        # Detect intent
        if any(word in body for word in ["yes", "interested", "book", "meeting"]):
            send_email(
                sender,
                "Book your AI Automation Meeting",
                f"Great! Click below to schedule your slot:<br><a href='{BOOKING_URL_BASE}{sender}'>Book Meeting</a>"
            )
            with conn.cursor() as cur:
                cur.execute("UPDATE leads SET status='booked' WHERE email=%s", (sender,))
            conn.commit()

        elif any(word in body for word in ["no", "not interested", "later"]):
            send_email(
                sender,
                "Explore Our Other AI Services",
                f"Thanks for your response. You can explore our other services here:<br><a href='{OTHER_SERVICES_URL}'>View Services</a>"
            )
            with conn.cursor() as cur:
                cur.execute("UPDATE leads SET status='not_interested' WHERE email=%s", (sender,))
            conn.commit()

        else:
            # Follow-up logic
            with conn.cursor() as cur:
                cur.execute("SELECT followups_sent FROM leads WHERE email=%s", (sender,))
                row = cur.fetchone()
                count = row[0] if row else 0

                if count < 5:
                    send_email(
                        sender,
                        f"Follow-up #{count + 1}: Let's Connect on AI Automation",
                        "Just checking in! Would you like to explore AI-powered automation for your business?"
                    )
                    cur.execute(
                        "UPDATE leads SET followups_sent=%s, last_contacted=NOW() WHERE email=%s",
                        (count + 1, sender)
                    )
                else:
                    send_email(
                        sender,
                        "You’ve been unsubscribed",
                        "We noticed you haven’t responded to our previous emails. You’ve been unsubscribed from our mailing list."
                    )
                    cur.execute("UPDATE leads SET status='unsubscribed' WHERE email=%s", (sender,))
            conn.commit()

    conn.close()

# ================================
# MAIN LOOP
# ================================
if __name__ == "__main__":
    print("📬 Monitoring inbox for replies...")
    while True:
        process_leads()
        time.sleep(300)  # check every 5 minutes
