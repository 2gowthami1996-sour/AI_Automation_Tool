# reply.py
import streamlit as st
import pandas as pd
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure
import os
from dotenv import load_dotenv
import datetime
from openai import OpenAI
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ===============================
# CONFIGURATION
# ===============================
load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD")

EMAIL_LOGS_COLLECTION = "email_logs"
CLEANED_CONTACTS_COLLECTION = "cleaned_contacts"
UNSUBSCRIBE_COLLECTION = "unsubscribe_list"

FOLLOW_UP_GRACE_PERIOD_MINUTES = 1
MAX_FOLLOW_UPS_BEFORE_UNSUBSCRIBE = 4

SCHEDULING_LINK = "https://calendar.google.com/calendar/u/0/appointments/schedules/AcZssZ1NrFLLqMavHAp5kvtxWiscTQBiWZB1wpJmhwp9JkSSudjC9DWY8b0HXZntjh4rEtHZvLaxLAdR"

client_ai = OpenAI(api_key=OPENAI_API_KEY)

# ===============================
# DATABASE FUNCTIONS
# ===============================
def get_db_connection():
    try:
        client = MongoClient(MONGO_URI)
        client.admin.command("ping")
        db = client[MONGO_DB_NAME]
        return client, db
    except ConnectionFailure as e:
        st.error("❌ Database connection failed.")
        st.error(e)
        return None, None


def setup_db_indexes(db):
    try:
        db[UNSUBSCRIBE_COLLECTION].create_index("email", unique=True)
    except OperationFailure:
        pass


def log_event_to_db(db, event_type, recipient_email, subject, body, status, **kwargs):
    entry = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc),
        "event_type": event_type,
        "recipient_email": recipient_email,
        "subject": subject,
        "body": body,
        "status": status,
        **kwargs,
    }
    db[EMAIL_LOGS_COLLECTION].insert_one(entry)


def is_unsubscribed(db, email):
    return db[UNSUBSCRIBE_COLLECTION].find_one({"email": email}) is not None


def add_to_unsubscribe_list(db, email, reason):
    db[UNSUBSCRIBE_COLLECTION].update_one(
        {"email": email},
        {"$setOnInsert": {
            "email": email,
            "reason": reason,
            "unsubscribed_at": datetime.datetime.now(datetime.timezone.utc),
        }},
        upsert=True
    )


# ===============================
# EMAIL FUNCTIONS
# ===============================
def add_footer(email_body):
    footer = f"""
    
---
💡 *Automated message from Morphius AI.*
📅 Schedule a meeting: {SCHEDULING_LINK}  
🚫 To unsubscribe, reply with "unsubscribe".
"""
    return email_body.strip() + footer


def send_email_smtp_direct(to_email, subject, body):
    if not all([SMTP_SERVER, SMTP_PORT, SENDER_EMAIL, SENDER_PASSWORD]):
        st.error("⚠️ SMTP credentials missing in .env file.")
        return False
    try:
        msg = MIMEMultipart()
        msg["From"] = SENDER_EMAIL
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(add_footer(body), "plain"))

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.sendmail(SENDER_EMAIL, to_email, msg.as_string())
        return True
    except Exception as e:
        st.error(f"❌ Failed to send email: {e}")
        return False


# ===============================
# AI UTILITIES
# ===============================
def generate_ai_response(prompt, system_message, max_tokens=200, temperature=0.7):
    try:
        response = client_ai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        st.error(f"OpenAI API Error: {e}")
        return None


def analyze_sentiment(email_body):
    system_message = """
Classify the sentiment of this email as one of:
positive → shows interest
negative → rejects or not interested
neutral → polite but no intent
unknown → unclear or irrelevant
Reply with only one word: positive, negative, neutral, or unknown.
"""
    result = generate_ai_response(email_body, system_message, max_tokens=20, temperature=0.2)
    result = (result or "").lower().strip()
    return result if result in ["positive", "negative", "neutral", "unknown"] else "unknown"


# ===============================
# EMAIL GENERATION
# ===============================
def generate_meeting_link_reply(name):
    subject = "Let's Schedule a Chat – Morphius AI"
    body = f"""Great to hear from you, {name}!

I'd love to connect and discuss how Morphius AI can help.
Please pick a time that works best for you here:
{SCHEDULING_LINK}

Looking forward to our conversation!

Best regards,  
Gowthami  
Morphius AI"""
    return subject, body


def generate_alternative_offer_reply(name):
    subject = "Other Solutions from Morphius AI"
    body = f"""Hi {name},

Thanks for your time and honesty.

Even if our initial proposal wasn't a fit, Morphius AI also offers:
- Workflow automation  
- AI-powered chatbots  
- Real-time analytics dashboards  

Would you be open to exploring one of these areas?

Best regards,  
Gowthami  
Morphius AI"""
    return subject, body


def generate_follow_up_email(name, previous_subject, count):
    subject = f"Following Up: {previous_subject}"
    body = f"""Hi {name},

Just checking in regarding my previous email about '{previous_subject}'.
I'd love to show how Morphius AI can streamline your business processes.

If you're free, please book a time here:
{SCHEDULING_LINK}

Best,  
Gowthami  
Morphius AI"""
    return subject, body


# ===============================
# MAIN APP
# ===============================
def main():
    st.set_page_config(page_title="Email Reply & Follow-Up Automation", page_icon="📧", layout="wide")
    st.title("📧 Morphius AI - Handle Replies & Follow-ups")

    client, db = get_db_connection()
    if not client:
        return
    setup_db_indexes(db)

    st.header("1️⃣ Pending Follow-ups")
    sent_emails_cursor = db[EMAIL_LOGS_COLLECTION].aggregate([
        {"$match": {"event_type": {"$in": ["initial_outreach", "follow_up_sent"]}}},
        {"$group": {
            "_id": "$recipient_email",
            "last_sent_subject": {"$last": "$subject"},
            "last_sent_timestamp": {"$last": "$timestamp"},
            "follow_up_count": {"$sum": {"$cond": [{"$eq": ["$event_type", "follow_up_sent"]}, 1, 0]}}
        }}
    ])

    sent_df = pd.DataFrame(list(sent_emails_cursor))
    if sent_df.empty:
        st.info("No sent emails found.")
    else:
        now = datetime.datetime.now(datetime.timezone.utc)
        actions = []
        for _, row in sent_df.iterrows():
            email = row["_id"]
            if is_unsubscribed(db, email):
                continue
            ts = row["last_sent_timestamp"]
            if not isinstance(ts, datetime.datetime):
                continue
            if (now - ts).total_seconds() / 60 >= FOLLOW_UP_GRACE_PERIOD_MINUTES:
                if row["follow_up_count"] < MAX_FOLLOW_UPS_BEFORE_UNSUBSCRIBE:
                    actions.append({
                        "email": email,
                        "next_action": "send_follow_up",
                        "follow_up_no": row["follow_up_count"] + 1,
                        "subject": row["last_sent_subject"]
                    })
                else:
                    actions.append({
                        "email": email,
                        "next_action": "unsubscribe",
                        "reason": "Max follow-ups reached"
                    })
        if actions:
            st.table(pd.DataFrame(actions))
            if st.button("Process Follow-ups"):
                for a in actions:
                    if a["next_action"] == "send_follow_up":
                        subject, body = generate_follow_up_email("there", a["subject"], a["follow_up_no"])
                        if send_email_smtp_direct(a["email"], subject, body):
                            log_event_to_db(db, "follow_up_sent", a["email"], subject, body, "success", follow_up_no=a["follow_up_no"])
                            st.success(f"✅ Sent follow-up to {a['email']}")
                    else:
                        add_to_unsubscribe_list(db, a["email"], a["reason"])
                        log_event_to_db(db, "auto_unsubscribe", a["email"], "N/A", a["reason"], "success")
                        st.warning(f"🚫 Unsubscribed {a['email']}")
                st.experimental_rerun()
        else:
            st.info("No pending follow-ups right now.")

    # ===========================
    # HANDLE REPLIES
    # ===========================
    st.header("2️⃣ Handle Incoming Replies")
    replies = list(db[EMAIL_LOGS_COLLECTION].find({
        "event_type": {"$regex": "^replied_"},
        "auto_processed": {"$ne": True}
    }))
    if not replies:
        st.info("No new replies for auto-processing.")
    else:
        df = pd.DataFrame(replies)[["recipient_email", "event_type", "body", "timestamp"]]
        st.dataframe(df, use_container_width=True)
        if st.button("Process Replies"):
            for r in replies:
                email = r["recipient_email"]
                text = r.get("body", "")
                sentiment = analyze_sentiment(text)
                contact = db[CLEANED_CONTACTS_COLLECTION].find_one(
                    {"$or": [{"work_emails": email}, {"personal_emails": email}]}
                )
                name = (contact.get("name", "there") if contact else "there").split(" ")[0]

                if "unsubscribe" in text.lower():
                    add_to_unsubscribe_list(db, email, "User replied unsubscribe")
                    log_event_to_db(db, "auto_unsubscribe_from_reply", email, "N/A", text, "success")
                    st.warning(f"🚫 {email} unsubscribed manually.")
                elif sentiment == "positive":
                    subject, body = generate_meeting_link_reply(name)
                    send_email_smtp_direct(email, subject, body)
                    log_event_to_db(db, "auto_reply_positive", email, subject, body, "success")
                    st.success(f"✅ Sent meeting link to {email}")
                elif sentiment == "negative":
                    subject, body = generate_alternative_offer_reply(name)
                    send_email_smtp_direct(email, subject, body)
                    log_event_to_db(db, "auto_reply_negative", email, subject, body, "success")
                    st.warning(f"⚠️ Sent alternative offer to {email}")
                else:
                    log_event_to_db(db, "auto_skip_neutral", email, "N/A", text, "skipped")
                    st.info(f"ℹ️ No action for {email} (sentiment: {sentiment})")

                db[EMAIL_LOGS_COLLECTION].update_one({"_id": r["_id"]}, {"$set": {"auto_processed": True}})
            st.success("✅ Replies processed successfully!")
            st.experimental_rerun()

    client.close()


if __name__ == "__main__":
    main()
