import streamlit as st
import pandas as pd
import os
from datetime import datetime
from pymongo import MongoClient
from openai import OpenAI
import yagmail
from dotenv import load_dotenv

# ======================================
# CONFIGURATION
# ======================================
load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = "ai_email_automation"
CLEANED_CONTACTS_COLLECTION = "cleaned_contacts"
EMAIL_LOGS_COLLECTION = "email_logs"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
SCHEDULING_LINK = "https://calendar.google.com/calendar/u/0/appointments/schedules/AcZssZ1NrFLLqMavHAp5kvtxWiscTQBiWZB1wpJmhwp9JkSSudjC9DWY8b0HXZntjh4rEtHZvLaxLAdR"

FOLLOW_UP_GRACE_PERIOD_MINUTES = 60 * 24  # 24 hours

client_ai = OpenAI(api_key=OPENAI_API_KEY)


# ======================================
# HELPER FUNCTIONS
# ======================================
def connect_mongo():
    return MongoClient(MONGO_URI)[DB_NAME]


def log_event_to_db(db, event_type, recipient_email, subject, body, status):
    db[EMAIL_LOGS_COLLECTION].insert_one(
        {
            "timestamp": datetime.now(),
            "event_type": event_type,
            "recipient_email": recipient_email,
            "subject": subject,
            "body": body,
            "status": status,
        }
    )


def send_email_smtp_direct(to_email, subject, body):
    yag = yagmail.SMTP(SMTP_USER, SMTP_PASS)
    yag.send(to=to_email, subject=subject, contents=body)


def add_footer(body):
    footer = f"""
    
---
💡 *Automated message from Morphius AI.*
📅 Book a meeting: [{SCHEDULING_LINK}]({SCHEDULING_LINK})  
🚫 To unsubscribe: reply with "unsubscribe"
"""
    return body + footer


def analyze_sentiment(text):
    try:
        response = client_ai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Classify this email as positive, negative, or neutral."},
                {"role": "user", "content": text},
            ],
        )
        return response.choices[0].message.content.strip().lower()
    except Exception:
        return "neutral"


def generate_followup_email(name):
    subject = f"Following up on our previous message, {name}"
    body = f"""
Hi {name},

Just checking in to see if you had a chance to look at our earlier email.
Would love to hear your thoughts and explore how Morphius AI can help automate your outreach and workflows.

Best,  
Morphius AI Team
"""
    return subject, body


def generate_meeting_link_reply(name):
    subject = f"Let's schedule a quick chat, {name}"
    body = f"""
Hi {name},

Great to hear that you're interested!  
You can book a time directly on our calendar here 👇  
{SCHEDULING_LINK}

Looking forward to connecting soon!  
Best,  
Morphius AI Team
"""
    return subject, body


def generate_alternative_offer_reply(name):
    subject = f"Thank you for your response, {name}"
    body = f"""
Hi {name},

Thank you for getting back to us.  
No worries — we appreciate your time. If you'd ever like to revisit AI-driven email automation or lead generation, Morphius AI will be here.

Wishing you continued success!  
Best,  
Morphius AI Team
"""
    return subject, body


def add_to_unsubscribe_list(db, email, reason="User requested unsubscribe"):
    db["unsubscribe_list"].update_one(
        {"email": email},
        {"$set": {"unsubscribed_at": datetime.now(), "reason": reason}},
        upsert=True,
    )


def get_contacts_for_followup(db):
    pipeline = [
        {
            "$lookup": {
                "from": EMAIL_LOGS_COLLECTION,
                "localField": "work_emails",
                "foreignField": "recipient_email",
                "as": "email_logs",
            }
        },
        {
            "$match": {
                "$and": [
                    {"email_logs.event_type": {"$ne": "replied_positive"}},
                    {"email_logs.event_type": {"$ne": "auto_unsubscribe_from_reply"}},
                ]
            }
        },
    ]
    contacts = list(db[CLEANED_CONTACTS_COLLECTION].aggregate(pipeline))
    return pd.DataFrame(contacts)


# ======================================
# AUTOMATED REPLY + FOLLOW-UP PROCESS
# ======================================
def process_replies_and_followups():
    db = connect_mongo()
    now = datetime.now()
    processed_replies = 0
    sent_followups = 0

    st.title("🤖 Morphius AI – Automated Replies & Follow-ups")

    # ===============================
    # STEP 1: Handle Incoming Replies
    # ===============================
    replied_cursor = db[EMAIL_LOGS_COLLECTION].find(
        {"event_type": {"$regex": "^replied_"}, "auto_processed": {"$ne": True}}
    )
    replied_df = pd.DataFrame(list(replied_cursor))

    if not replied_df.empty:
        st.subheader("📨 Processing New Replies...")
        for _, reply in replied_df.iterrows():
            email = reply["recipient_email"]
            body = reply.get("body", "")
            sentiment = analyze_sentiment(body)
            name = "there"

            contact = db[CLEANED_CONTACTS_COLLECTION].find_one(
                {"$or": [{"work_emails": email}, {"personal_emails": email}]}
            )
            if contact and contact.get("name"):
                name = contact["name"].split(" ")[0]

            if "unsubscribe" in body.lower() or "remove me" in body.lower():
                add_to_unsubscribe_list(db, email, "User replied with unsubscribe request")
                log_event_to_db(db, "auto_unsubscribe_from_reply", email, "N/A", body, "success")
                st.warning(f"🚫 {email} unsubscribed.")
            elif sentiment == "positive":
                subject, auto_body = generate_meeting_link_reply(name)
                send_email_smtp_direct(email, subject, add_footer(auto_body))
                log_event_to_db(db, "auto_reply_positive", email, subject, auto_body, "success")
                st.success(f"✅ Meeting link sent to {email}")
            elif sentiment == "negative":
                subject, auto_body = generate_alternative_offer_reply(name)
                send_email_smtp_direct(email, subject, add_footer(auto_body))
                log_event_to_db(db, "auto_reply_negative", email, subject, auto_body, "success")
                st.warning(f"⚠️ Polite decline message sent to {email}")
            else:
                st.info(f"ℹ️ Skipped {email} (neutral sentiment)")

            db[EMAIL_LOGS_COLLECTION].update_one(
                {"_id": reply["_id"]}, {"$set": {"auto_processed": True}}
            )
            processed_replies += 1
    else:
        st.info("📭 No new replies found.")

    # ===============================
    # STEP 2: Send Follow-ups Automatically
    # ===============================
    st.markdown("---")
    st.subheader("📧 Sending Follow-ups Automatically...")

    no_reply_contacts = get_contacts_for_followup(db)
    if not no_reply_contacts.empty:
        for _, contact in no_reply_contacts.iterrows():
            ts = contact.get("timestamp", now)
            try:
                ts = pd.to_datetime(ts)
            except Exception:
                ts = now

            if (now - ts).total_seconds() / 60 >= FOLLOW_UP_GRACE_PERIOD_MINUTES:
                email = (
                    contact.get("work_emails")
                    or contact.get("personal_emails")
                    or None
                )
                if not email:
                    continue

                subject, body = generate_followup_email(contact["name"])
                body = add_footer(body)
                send_email_smtp_direct(email, subject, body)
                log_event_to_db(db, "followup_sent", email, subject, body, "success")
                sent_followups += 1

        st.success(f"✅ Sent {sent_followups} follow-ups successfully.")
    else:
        st.info("🎉 Everyone has replied or unsubscribed.")

    # ===============================
    # FINAL SUMMARY
    # ===============================
    st.markdown("---")
    st.write(f"**Replies Processed:** {processed_replies}")
    st.write(f"**Follow-ups Sent:** {sent_followups}")
    st.success("✅ Morphius AI automation completed!")


# ======================================
# RUN APP
# ======================================
if __name__ == "__main__":
    process_replies_and_followups()
