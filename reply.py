import streamlit as st
import pandas as pd
from datetime import datetime
from pymongo import MongoClient
import yagmail
import os

# ==================================
# CONFIG
# ==================================
FOLLOW_UP_GRACE_PERIOD_MINUTES = 1440  # 24 hours
SCHEDULING_LINK = "https://calendar.google.com/calendar/u/0/appointments/schedules/AcZssZ1NrFLLqMavHAp5kvtxWiscTQBiWZB1wpJmhwp9JkSSudjC9DWY8b0HXZntjh4rEtHZvLaxLAdR"

# MongoDB setup
MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client["morphius_ai"]

# ==================================
# HELPER FUNCTIONS
# ==================================
def send_email_smtp_direct(recipient, subject, body):
    """Send email using yagmail"""
    sender = os.getenv("EMAIL_USER")
    password = os.getenv("EMAIL_PASS")

    yag = yagmail.SMTP(sender, password)
    yag.send(to=recipient, subject=subject, contents=body)


def add_footer(body):
    """Adds meeting and unsubscribe link to all emails"""
    footer_html = f"""
    <br><br>
    <hr>
    <p style="font-size:14px;">
        📅 <b>Schedule a Meeting:</b> 
        <a href="{SCHEDULING_LINK}" target="_blank">Click here to pick a time</a>
    </p>
    <p style="font-size:13px; color:gray;">
        If you are not interested, click <a href="#" style="color:#888;">unsubscribe</a>.
    </p>
    """
    return body + footer_html


def log_event_to_db(db, event_type, email, subject, body, status):
    db.logs.insert_one({
        "event": event_type,
        "email": email,
        "subject": subject,
        "body": body,
        "status": status,
        "timestamp": datetime.now()
    })


def get_contacts_for_followup(db):
    """Fetch contacts who have not replied and not unsubscribed"""
    contacts = list(db.contacts.find({"reply_status": {"$in": ["no_reply", None]}, "unsubscribed": {"$ne": True}}))
    return pd.DataFrame(contacts)


def generate_followup_email(name):
    subject = f"Following up, {name} 👋"
    body = f"""
    <p>Hi {name},</p>
    <p>Just wanted to follow up on my earlier email. Have you had a chance to review it?</p>
    <p>I’d love to schedule a quick chat if you’re interested.</p>
    """
    return subject, body


def process_replies(db):
    """Automatically checks and updates reply statuses"""
    st.subheader("📥 Checking Email Replies...")

    # For now, simulate replies (you can later connect to Gmail API)
    simulated_replies = [
        {"email": "example1@gmail.com", "reply": "interested"},
        {"email": "example2@gmail.com", "reply": "not interested"},
        {"email": "example3@gmail.com", "reply": "no reply"}
    ]

    for r in simulated_replies:
        email = r["email"]
        reply = r["reply"].lower()

        if reply == "interested":
            db.contacts.update_one({"work_emails": email}, {"$set": {"reply_status": "interested"}})
        elif reply == "not interested":
            db.contacts.update_one({"work_emails": email}, {"$set": {"reply_status": "not_interested"}})
        else:
            db.contacts.update_one({"work_emails": email}, {"$set": {"reply_status": "no_reply"}})

    st.success("✅ Replies processed successfully!")


# ==================================
# MAIN FUNCTION
# ==================================
def main():
    st.title("📧 Morphius AI - Handle Replies & Follow-ups")

    # 1️⃣ Step: Handle replies first
    process_replies(db)

    # 2️⃣ Step: Then automatically handle follow-ups
    st.markdown("---")
    st.subheader("📬 Pending Follow-ups")

    no_reply_contacts = get_contacts_for_followup(db)

    if no_reply_contacts.empty:
        st.info("🎉 No pending follow-ups! All contacts have replied or unsubscribed.")
    else:
        st.dataframe(
            no_reply_contacts[["name", "work_emails", "personal_emails", "timestamp"]],
            use_container_width=True
        )

        now = datetime.now()
        sent_count = 0

        for _, contact in no_reply_contacts.iterrows():
            ts = contact.get("timestamp", now)

            # ✅ Ensure timestamp is datetime
            try:
                ts = pd.to_datetime(ts)
            except Exception:
                ts = now

            # ✅ Check follow-up delay
            if (now - ts).total_seconds() / 60 >= FOLLOW_UP_GRACE_PERIOD_MINUTES:
                email = contact.get("work_emails") or contact.get("personal_emails")
                if not email:
                    continue

                subject, body = generate_followup_email(contact["name"])
                body = add_footer(body)

                send_email_smtp_direct(email, subject, body)
                log_event_to_db(db, "followup_sent", email, subject, body, "success")
                sent_count += 1

        st.success(f"✅ Sent {sent_count} follow-up emails successfully!")


# ==================================
# ENTRY POINT
# ==================================
if __name__ == "__main__":
    main()
