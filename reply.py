# reply.py
import streamlit as st
import pandas as pd
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure
import os
from dotenv import load_dotenv
import datetime
from openai import OpenAI
import time
import pytz  # For accurate timezone handling

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

FOLLOW_UP_GRACE_PERIOD_MINUTES = 1  # Testing mode
MAX_FOLLOW_UPS_BEFORE_UNSUBSCRIBE = 4

SCHEDULING_LINK = "https://calendar.google.com/calendar/u/0/appointments/schedules/AcZssZ1NrFLLqMavHAp5kvtxWiscTQBiWZB1wpJmhwp9JkSSudjC9DWY8b0HXZntjh4rEtHZvLaxLAdR"

# Initialize OpenAI Client
client_ai = OpenAI(api_key=OPENAI_API_KEY)

# ===============================
# DATABASE FUNCTIONS
# ===============================
def get_db_connection():
    try:
        client = MongoClient(MONGO_URI)
        client.admin.command("ismaster")
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
    try:
        log_entry = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc),
            "event_type": event_type,
            "recipient_email": recipient_email,
            "subject": subject,
            "body": body,
            "status": status,
            **kwargs,
        }
        db[EMAIL_LOGS_COLLECTION].insert_one(log_entry)
        return True
    except Exception as e:
        st.error(f"❌ Log error: {e}")
        return False


def send_email_smtp_direct(to_email, subject, body):
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    if not all([SMTP_SERVER, SMTP_PORT, SENDER_EMAIL, SENDER_PASSWORD]):
        st.error("SMTP details missing in .env file.")
        return False

    try:
        msg = MIMEMultipart()
        msg["From"] = SENDER_EMAIL
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.sendmail(SENDER_EMAIL, to_email, msg.as_string())
        return True
    except Exception as e:
        st.error(f"❌ SMTP send failed: {e}")
        return False


def add_to_unsubscribe_list(db, email, reason):
    try:
        db[UNSUBSCRIBE_COLLECTION].update_one(
            {"email": email},
            {
                "$setOnInsert": {
                    "email": email,
                    "reason": reason,
                    "unsubscribed_at": datetime.datetime.now(datetime.timezone.utc),
                }
            },
            upsert=True,
        )
        st.warning(f"🚫 Added {email} to unsubscribe list due to: {reason}")
        return True
    except Exception as e:
        st.error(f"❌ Failed to add to unsubscribe list: {e}")
        return False


def is_unsubscribed(db, email):
    return db[UNSUBSCRIBE_COLLECTION].find_one({"email": email}) is not None


# ===============================
# AI FUNCTIONS
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


def generate_meeting_link_reply(recipient_name):
    system_message = "You are an AI assistant writing a professional follow-up email."
    prompt = f"""
Write a short, polite email to {recipient_name} who showed interest.
Invite them to book a meeting using this Google Appointment Scheduler link:
{SCHEDULING_LINK}
Start with 'Great to hear from you, {recipient_name}!' and end with a friendly closing.
"""
    body = generate_ai_response(prompt, system_message)
    if not body:
        body = f"""Great to hear from you, {recipient_name}!

I'd love to connect and discuss how Morphius AI can help.
You can schedule a time that works best for you here:
{SCHEDULING_LINK}

Looking forward to our conversation!

Best regards,
Gowthami
Morphius AI"""
    subject = "Following Up: Let's Connect!"
    return subject, body


def generate_alternative_offer_reply(recipient_name):
    system_message = "You are an AI assistant writing an empathetic follow-up email."
    prompt = f"""
Write a polite email for {recipient_name} acknowledging their disinterest.
Briefly mention Morphius AI's other offerings (workflow automation, AI chatbots, analytics dashboards).
End with an open-ended question like 'Would you be open to exploring these?'.
"""
    body = generate_ai_response(prompt, system_message)
    if not body:
        body = f"""Thank you for your feedback, {recipient_name}.

Even if our initial proposal isn't the right fit, Morphius AI also provides
workflow automation, AI chatbots, and data analytics dashboards that can deliver value.

Would you be open to exploring these alternatives?

Best regards,
Gowthami
Morphius AI"""
    subject = "Understanding Your Needs - Morphius AI"
    return subject, body


def generate_follow_up_email(recipient_name, previous_subject, follow_up_count):
    system_message = "You are an AI assistant creating a friendly follow-up email."
    prompt = f"""
Write a polite follow-up email to {recipient_name} about '{previous_subject}'.
This is follow-up number {follow_up_count}.
Be professional, add value, and suggest they reply or schedule a chat.
"""
    body = generate_ai_response(prompt, system_message)
    if not body:
        body = f"""Hi {recipient_name},

Just checking in regarding my previous email about '{previous_subject}'.
I'd love to share how Morphius AI can help streamline your workflows and improve efficiency.

If now isn't a good time, please let me know.
Otherwise, feel free to schedule a slot here: {SCHEDULING_LINK}

Best regards,
Gowthami
Morphius AI"""
    subject = f"Following Up: {previous_subject}"
    return subject, body


def analyze_sentiment(email_body):
    system_message = """
You are an email sentiment classifier for Morphius AI.

Respond with ONE of these words ONLY:
positive → interested, asks for info, wants to connect
negative → not interested, reject, unsubscribe
neutral → polite acknowledgment, no intent
unknown → unclear, irrelevant, or too short

Examples:
"I'm interested" → positive
"No thanks" → negative
"Got it" → neutral
"?" → unknown
"""
    prompt = f"Classify this email:\n\n{email_body}"
    sentiment = generate_ai_response(prompt, system_message, max_tokens=20, temperature=0.2)
    sentiment = (sentiment or "").strip().lower()
    if sentiment not in ["positive", "negative", "neutral", "unknown"]:
        return "unknown"
    return sentiment


# ===============================
# MAIN STREAMLIT APP
# ===============================
def main():
    st.set_page_config(page_title="Handle Email Replies & Follow-ups", page_icon="↩️", layout="wide")
    st.title("↩️ Handle Email Replies & Follow-ups")
    st.markdown("This section automates reply handling and follow-ups.")

    if not all([OPENAI_API_KEY, SMTP_SERVER, SMTP_PORT, SENDER_EMAIL, SENDER_PASSWORD]):
        st.error("⚠️ Missing .env configuration for email or OpenAI API.")
        return

    client, db = get_db_connection()
    if not client:
        return

    setup_db_indexes(db)

    st.subheader("Simulate Incoming Replies and Automate Actions")

    sent_emails_cursor = db[EMAIL_LOGS_COLLECTION].aggregate([
        {"$match": {"event_type": {"$in": ["initial_outreach", "follow_up_sent"]}}},
        {"$group": {
            "_id": "$recipient_email",
            "last_sent_subject": {"$last": "$subject"},
            "last_sent_body": {"$last": "$body"},
            "last_sent_timestamp": {"$last": "$timestamp"},
            "total_follow_ups_sent": {
                "$sum": {"$cond": [{"$eq": ["$event_type", "follow_up_sent"]}, 1, 0]}
            },
        }}
    ])

    all_sent_df = pd.DataFrame(list(sent_emails_cursor))
    if all_sent_df.empty:
        st.info("No emails found for follow-up.")
        client.close()
        return

    replied_emails = db[EMAIL_LOGS_COLLECTION].find({"event_type": {"$regex": "^replied_"}}).distinct("recipient_email")
    pending_emails_df = all_sent_df[~all_sent_df["_id"].isin(replied_emails)]

    if pending_emails_df.empty:
        st.info("All emails have received replies.")
        client.close()
        return

    pending_emails_df = pending_emails_df[
        ~pending_emails_df["_id"].apply(lambda x: is_unsubscribed(db, x))
    ]

    if pending_emails_df.empty:
        st.info("All pending emails are unsubscribed or replied.")
        client.close()
        return

    actions_to_take = []
    now_utc = datetime.datetime.now(datetime.timezone.utc)

    for _, row in pending_emails_df.iterrows():
        email_addr = row["_id"]
        last_sent_ts = row["last_sent_timestamp"]
        if isinstance(last_sent_ts, datetime.datetime):
            if last_sent_ts.tzinfo is None:
                last_sent_ts = last_sent_ts.replace(tzinfo=datetime.timezone.utc)
        else:
            continue

        time_since_last_sent = (now_utc - last_sent_ts).total_seconds() / 60
        contact_name = "there"
        contact = db[CLEANED_CONTACTS_COLLECTION].find_one(
            {"$or": [{"work_emails": email_addr}, {"personal_emails": email_addr}]}
        )
        if contact and contact.get("name"):
            contact_name = contact["name"].split(" ")[0]

        if time_since_last_sent >= FOLLOW_UP_GRACE_PERIOD_MINUTES:
            if row["total_follow_ups_sent"] < MAX_FOLLOW_UPS_BEFORE_UNSUBSCRIBE:
                actions_to_take.append({
                    "email": email_addr,
                    "action_type": "send_follow_up",
                    "reason": f"No reply after {FOLLOW_UP_GRACE_PERIOD_MINUTES} minutes.",
                    "recipient_name": contact_name,
                    "previous_subject": row["last_sent_subject"],
                    "follow_up_count": row["total_follow_ups_sent"] + 1,
                })
            else:
                actions_to_take.append({
                    "email": email_addr,
                    "action_type": "unsubscribe",
                    "reason": f"Reached max follow-ups ({MAX_FOLLOW_UPS_BEFORE_UNSUBSCRIBE}).",
                    "recipient_name": contact_name,
                })

    if not actions_to_take:
        st.info("No immediate follow-ups required.")
        client.close()
        return

    st.subheader("Pending Actions")
    st.table(pd.DataFrame(actions_to_take)[["email", "action_type", "reason"]])

    if st.button("Simulate & Process Actions"):
        for action in actions_to_take:
            if action["action_type"] == "send_follow_up":
                subject, body = generate_follow_up_email(
                    action["recipient_name"],
                    action["previous_subject"],
                    action["follow_up_count"],
                )
                if send_email_smtp_direct(action["email"], subject, body):
                    log_event_to_db(db, "follow_up_sent", action["email"], subject, body, "success", follow_up_count=action["follow_up_count"])
                    st.success(f"✅ Sent follow-up to {action['email']}")
                else:
                    st.error(f"❌ Failed to send follow-up to {action['email']}")
            elif action["action_type"] == "unsubscribe":
                add_to_unsubscribe_list(db, action["email"], action["reason"])
                log_event_to_db(db, "unsubscribed_automated", action["email"], "N/A", action["reason"], "success")
        st.success("All pending actions processed!")
        st.experimental_rerun()

    st.markdown("---")
    st.subheader("Manually Simulate a Reply (for testing AI auto-replies)")
    recipient_email_for_sim = st.selectbox(
        "Select an email:", pending_emails_df["_id"].tolist(), key="sim_email_select"
    )
    simulated_reply_body = st.text_area(
        "Enter simulated reply body:",
        "Yes, I'm interested! Could you please share more details?",
        height=150,
    )

    if st.button("Simulate Reply & Auto Respond"):
        if not recipient_email_for_sim:
            st.warning("Select an email.")
            return

        recipient_name = "there"
        contact = db[CLEANED_CONTACTS_COLLECTION].find_one(
            {"$or": [{"work_emails": recipient_email_for_sim}, {"personal_emails": recipient_email_for_sim}]}
        )
        if contact and contact.get("name"):
            recipient_name = contact["name"].split(" ")[0]

        sentiment = analyze_sentiment(simulated_reply_body)
        st.info(f"Detected sentiment: **{sentiment}**")

        log_event_to_db(
            db, f"replied_{sentiment}", recipient_email_for_sim, "Simulated Reply", simulated_reply_body, "success", interest_level=sentiment
        )

        if sentiment == "positive":
            subject, body = generate_meeting_link_reply(recipient_name)
            if send_email_smtp_direct(recipient_email_for_sim, subject, body):
                log_event_to_db(db, "response_positive_auto", recipient_email_for_sim, subject, body, "success", interest_level=sentiment)
                st.success(f"✅ Sent Google meeting link to {recipient_email_for_sim}")
        elif sentiment == "negative":
            subject, body = generate_alternative_offer_reply(recipient_name)
            if send_email_smtp_direct(recipient_email_for_sim, subject, body):
                log_event_to_db(db, "response_negative_auto", recipient_email_for_sim, subject, body, "success", interest_level=sentiment)
                st.success(f"✅ Sent alternative offer to {recipient_email_for_sim}")
        else:
            st.info("Neutral or unknown sentiment — no automatic response sent.")

    client.close()


if __name__ == "__main__":
    main()
