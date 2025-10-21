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
import pytz # For accurate timezone handling
import smtplib # Import here for direct use
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


# ===============================
# CONFIGURATION
# ===============================
load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SENDER_EMAIL = os.getenv("SENDER_EMAIL") # Your sending email for follow-ups
SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD")

EMAIL_LOGS_COLLECTION = "email_logs"
CLEANED_CONTACTS_COLLECTION = "cleaned_contacts"
UNSUBSCRIBE_COLLECTION = "unsubscribe_list"

# --- Business Logic Configuration ---
# Set to 1 minute for rapid testing. For production, consider 24*60 (1 day) or more.
FOLLOW_UP_GRACE_PERIOD_MINUTES = 1
MAX_FOLLOW_UPS_BEFORE_UNSUBSCRIBE = 4 # Number of follow-ups before unsubscribing

# Initialize OpenAI Client
client_ai = OpenAI(api_key=OPENAI_API_KEY)

# ===============================
# DATABASE & EMAIL FUNCTIONS
# ===============================
def get_db_connection():
    """Establishes and returns a connection to the MongoDB database."""
    try:
        client = MongoClient(MONGO_URI)
        client.admin.command('ismaster')
        db = client[MONGO_DB_NAME]
        return client, db
    except ConnectionFailure as e:
        st.error(f"❌ **Database Connection Error:** Could not connect to MongoDB. Ensure `MONGO_URI` is correct and MongoDB is reachable.")
        st.error(e)
        return None, None

def setup_db_indexes(db):
    """Ensures necessary indexes are present in MongoDB collections."""
    try:
        db[UNSUBSCRIBE_COLLECTION].create_index("email", unique=True)
    except OperationFailure:
        pass # Index already exists

def log_event_to_db(db, event_type, recipient_email, subject, body, status, **kwargs):
    """Inserts an email event document into the 'email_logs' collection."""
    try:
        log_entry = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc),
            "event_type": event_type,
            "recipient_email": recipient_email,
            "subject": subject,
            "body": body,
            "status": status,
            **kwargs # Add any additional keyword arguments (e.g., interest_level, follow_up_count)
        }
        db[EMAIL_LOGS_COLLECTION].insert_one(log_entry)
        return True
    except Exception as e:
        st.error(f"❌ Failed to log event to database: {e}")
        return False

def send_email_smtp_direct(to_email, subject, body, db=None): # Added db argument for logging inside
    """Connects to the SMTP server, sends the email, and logs the event to the database if db is provided."""
    if not all([SMTP_SERVER, SMTP_PORT, SENDER_EMAIL, SENDER_PASSWORD]):
        st.error("❌ SMTP server details are not fully configured in environment variables.")
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
        
        # If successfully sent, log it here if db connection is passed
        if db:
            log_event_to_db(db, "sent_automated_reply", to_email, subject, body, "success")
        return True
    except smtplib.SMTPAuthenticationError:
        st.error(f"❌ SMTP Authentication Error for {SENDER_EMAIL}. Check SENDER_EMAIL and SENDER_PASSWORD (especially if using Gmail App Password).")
        if db: log_event_to_db(db, "sent_automated_reply", to_email, subject, body, "failed_auth")
        return False
    except smtplib.SMTPException as e:
        st.error(f"❌ SMTP Error sending to {to_email}: {e}")
        if db: log_event_to_db(db, "sent_automated_reply", to_email, subject, body, "failed_smtp")
        return False
    except Exception as e:
        st.error(f"❌ Unexpected Error sending to {to_email}: {e}")
        if db: log_event_to_db(db, "sent_automated_reply", to_email, subject, body, "failed_unknown")
        return False

def add_to_unsubscribe_list(db, email, reason):
    """Adds an email to the unsubscribe_list collection."""
    try:
        db[UNSUBSCRIBE_COLLECTION].update_one(
            {'email': email},
            {'$setOnInsert': {
                'email': email,
                'reason': reason,
                'unsubscribed_at': datetime.datetime.now(datetime.timezone.utc)
            }},
            upsert=True
        )
        st.warning(f"🚫 Added {email} to unsubscribe list due to: {reason}")
        return True
    except Exception as e:
        st.error(f"❌ Failed to add {email} to unsubscribe list: {e}")
        return False

def is_unsubscribed(db, email):
    """Checks if an email is in the unsubscribe list."""
    return db[UNSUBSCRIBE_COLLECTION].find_one({'email': email}) is not None

# ===============================
# AI GENERATION FUNCTIONS
# ===============================
def generate_ai_response(prompt, system_message, max_tokens=200, temperature=0.7):
    """Helper to call OpenAI API."""
    try:
        response = client_ai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt}
            ],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        st.error(f"OpenAI API Error: {e}")
        return None

def generate_meeting_link_reply(recipient_name):
    system_message = "You are an AI assistant crafting a professional email to a prospect who expressed interest. Provide a short, polite email including a Calendly link."
    prompt = f"Write an email for {recipient_name} inviting them to book a meeting using this Calendly link: https://calendly.com/morphius-ai/intro. Start with 'Great to hear from you, {recipient_name}!' or similar. Keep it concise."

    body = generate_ai_response(prompt, system_message)
    if body:
        subject = "Following Up: Let's Connect!"
    else: # Fallback
        body = f"Great to hear from you, {recipient_name}!\n\nI'd be happy to schedule a quick chat. You can book a time directly using my Calendly link here: https://calendly.com/morphius-ai/intro\n\nLooking forward to speaking!\n\nBest regards,\nGowthami\nMorphius AI"
        subject = "Following Up: Let's Connect!"
    return subject, body

def generate_alternative_offer_reply(recipient_name):
    system_message = "You are an AI assistant crafting a professional email to a prospect who expressed disinterest in the initial offer but might be open to other services. Offer alternative Morphius AI services briefly."
    prompt = f"Write a polite email for {recipient_name} acknowledging their disinterest in the initial proposal. Suggest other ways Morphius AI can help, such as workflow automation, AI chatbots, or analytics dashboards. Keep it brief and open-ended. End with a polite closing."

    body = generate_ai_response(prompt, system_message)
    if body:
        subject = "Understanding Your Needs - Morphius AI"
    else: # Fallback
        body = f"Thank you for your candid feedback, {recipient_name}.\n\nWhile our initial proposal might not be the right fit, Morphius AI offers a range of other solutions like workflow automation, AI chatbots, and custom analytics dashboards that could still be valuable.\n\nWould you be open to a brief discussion about these alternatives?\n\nBest regards,\nGowthami\nMorphius AI"
        subject = "Understanding Your Needs - Morphius AI"
    return subject, body

def generate_follow_up_email(recipient_name, previous_subject, follow_up_count):
    system_message = "You are an AI assistant crafting a polite follow-up email to a prospect who hasn't replied to a previous email. Keep it concise, professional, and add value. Ensure the subject line clearly indicates it's a follow-up."
    prompt = f"Write a follow-up email for {recipient_name}. This is follow-up number {follow_up_count}. Reference the previous subject: '{previous_subject}'. Reiterate value without being pushy. Add a clear call to action, e.g., 'If now isn't a good time, please let me know.' Make the subject line concise and clear, e.g., 'Following Up: [Original Subject]' or 'Quick Follow-up regarding [Original Subject]'."

    body = generate_ai_response(prompt, system_message)
    # Refine subject after body generation if AI provided a good one, or use fallback
    if body:
        # Attempt to extract subject from AI response if it's there, otherwise fallback
        subject_match = re.search(r"Subject: (.+)", body, re.IGNORECASE)
        if subject_match:
            subject = subject_match.group(1).strip()
            body = re.sub(r"Subject: (.+)\n\n", "", body, flags=re.IGNORECASE).strip() # Remove subject line from body
        else:
            subject = f"Following Up: {previous_subject}" # Default if AI didn't provide a subject
    else: # Fallback
        body = f"Hi {recipient_name},\n\nHope this email finds you well. I'm just circling back on my previous email regarding '{previous_subject}'.\n\nI believe our AI solutions could genuinely benefit your operations by [mention a key benefit, e.g., streamlining workflows or enhancing customer engagement].\n\nIf now isn't the best time, or if you're not the right person, please let me know. Otherwise, I'd be happy to discuss further.\n\nBest regards,\nGowthami\nMorphius AI"
        subject = f"Following Up: {previous_subject}"
    return subject, body

def analyze_sentiment(email_body):
    system_message = """
    Analyze the sentiment of the provided email reply towards Morphius AI's services.
    Respond with ONLY one of the following words: 'positive', 'negative', 'neutral', 'unknown'.
    'Positive' means they are interested, want to learn more, or book a meeting.
    'Negative' means they are explicitly not interested, asking to unsubscribe, or rejecting the offer.
    'Neutral' means acknowledgment without clear interest or disinterest.
    'Unknown' if the sentiment is unclear or the email is short/generic.
    """
    prompt = f"Analyze the sentiment of this email:\n\n{email_body}"
    sentiment = generate_ai_response(prompt, system_message, max_tokens=10, temperature=0.1)
    if sentiment not in ['positive', 'negative', 'neutral', 'unknown']:
        return 'unknown' # Default for unexpected AI output
    return sentiment

# ===============================
# MAIN STREAMLIT APP
# ===============================
def main():
    st.set_page_config(page_title="Handle Email Replies & Follow-ups", page_icon="↩️", layout="wide")
    st.title("↩️ Handle Email Replies & Follow-ups")
    st.markdown("This section automatically processes follow-ups and allows manual simulation of replies.")

    # Check for critical environment variables at the start
    if not all([OPENAI_API_KEY, SMTP_SERVER, SMTP_PORT, SENDER_EMAIL, SENDER_PASSWORD]):
        st.error("⚠️ **Missing Environment Variables!** Please ensure `OPENAI_API_KEY`, `SMTP_SERVER`, `SMTP_PORT`, `SENDER_EMAIL`, and `SENDER_PASSWORD` are set in your `.env` file for AI and email sending functionality.")
        return

    client, db = get_db_connection()
    if not client:
        return

    setup_db_indexes(db)

    st.subheader("Automated Follow-up and Unsubscribe Processing")

    # Fetch initial outreach emails that haven't received a clear reply yet
    sent_emails_cursor = db[EMAIL_LOGS_COLLECTION].aggregate([
        {"$match": {"event_type": {"$in": ["initial_outreach", "follow_up_sent"]}}},
        {"$group": {
            "_id": "$recipient_email",
            "last_sent_subject": {"$last": "$subject"},
            "last_sent_body": {"$last": "$body"},
            "last_sent_timestamp": {"$last": "$timestamp"},
            "sent_event_type": {"$last": "$event_type"},
            "initial_sent_timestamp": {"$first": "$timestamp"},
            "total_follow_ups_sent": {"$sum": {"$cond": [{"$eq": ["$event_type", "follow_up_sent"]}, 1, 0]}}
        }}
    ])

    all_sent_df = pd.DataFrame(list(sent_emails_cursor))

    if all_sent_df.empty:
        st.info("No initial outreach or follow-up emails have been sent yet.")
        client.close()
        return

    replied_emails = db[EMAIL_LOGS_COLLECTION].find({"event_type": {"$regex": "^replied_"}}).distinct("recipient_email")
    pending_emails_df = all_sent_df[~all_sent_df['_id'].isin(replied_emails)].copy()

    if pending_emails_df.empty:
        st.info("All sent emails have received a reply or are being processed.")
        client.close()
        return

    pending_emails_df = pending_emails_df[
        ~pending_emails_df['_id'].apply(lambda x: is_unsubscribed(db, x))
    ].copy()

    if pending_emails_df.empty:
        st.info("All pending emails are either unsubscribed or have received a reply.")
        client.close()
        return

    actions_to_take = []
    now_utc = datetime.datetime.now(datetime.timezone.utc)

    for index, row in pending_emails_df.iterrows():
        email_addr = row['_id']
        last_sent_ts = row['last_sent_timestamp'].replace(tzinfo=pytz.utc) if row['last_sent_timestamp'].tzinfo is None else row['last_sent_timestamp']

        time_since_last_sent = (now_utc - last_sent_ts).total_seconds() / 60

        contact_name = "there"
        contact_in_cleaned_db = db[CLEANED_CONTACTS_COLLECTION].find_one(
            {"$or": [{"work_emails": email_addr}, {"personal_emails": email_addr}]}
        )
        if contact_in_cleaned_db and contact_in_cleaned_db.get('name'):
            contact_name = contact_in_cleaned_db['name'].split(' ')[0]

        if time_since_last_sent >= FOLLOW_UP_GRACE_PERIOD_MINUTES:
            if row['total_follow_ups_sent'] < MAX_FOLLOW_UPS_BEFORE_UNSUBSCRIBE:
                actions_to_take.append({
                    "email": email_addr,
                    "action_type": "send_follow_up",
                    "reason": f"No reply after {FOLLOW_UP_GRACE_PERIOD_MINUTES} minutes.",
                    "recipient_name": contact_name,
                    "previous_subject": row['last_sent_subject'],
                    "follow_up_count": row['total_follow_ups_sent'] + 1
                })
            else:
                actions_to_take.append({
                    "email": email_addr,
                    "action_type": "unsubscribe",
                    "reason": f"Reached max follow-ups ({MAX_FOLLOW_UPS_BEFORE_UNSUBSCRIBE}) without reply.",
                    "recipient_name": contact_name
                })

    if actions_to_take:
        st.subheader("Actions Being Processed Automatically:")
        st.table(pd.DataFrame(actions_to_take).drop(columns=['recipient_name', 'previous_subject', 'follow_up_count'], errors='ignore'))

        processing_message = st.empty()
        total_actions = len(actions_to_take)
        processed_count = 0

        for action in actions_to_take:
            processed_count += 1
            processing_message.info(f"Processing action {processed_count}/{total_actions}: {action['action_type']} for {action['email']}...")

            if action['action_type'] == "send_follow_up":
                subject, body = generate_follow_up_email(
                    action['recipient_name'],
                    action['previous_subject'],
                    action['follow_up_count']
                )
                if send_email_smtp_direct(action['email'], subject, body, db=db): # Pass db for logging
                    log_event_to_db(db, "follow_up_sent", action['email'], subject, body, "success",
                                    follow_up_count=action['follow_up_count'])
                    st.success(f"✅ Sent follow-up {action['follow_up_count']} to {action['email']}")
                else:
                    # Error already logged inside send_email_smtp_direct
                    st.error(f"❌ Failed to send follow-up to {action['email']}")

            elif action['action_type'] == "unsubscribe":
                add_to_unsubscribe_list(db, action['email'], action['reason'])
                log_event_to_db(db, "unsubscribed_automated", action['email'], "N/A", action['reason'], "success")

            time.sleep(1) # Simulate some work for visual feedback

        processing_message.empty()
        st.success("All automated actions processed for this cycle!")
        # To make it truly "real-time" in a Streamlit app, you'd need continuous refreshing.
        # This will trigger a re-run, effectively looping the automation check.
        time.sleep(5) # Give some time for user to see success message
        st.experimental_rerun()
    else:
        st.info("No immediate automated actions needed at this time. Checking again soon...")
        time.sleep(5) # Check again after 5 seconds
        st.experimental_rerun()


    st.markdown("---")
    st.subheader("Manually Simulate a Reply (for testing AI response generation)")
    st.info("This section allows you to test how the system responds to a reply, independent of automated follow-ups.")

    recipient_email_for_sim = st.selectbox(
        "Select an email to simulate a reply for (only emails not yet marked as replied):",
        options=pending_emails_df['_id'].tolist(),
        index=0 if not pending_emails_df.empty else None,
        key="sim_email_select"
    )
    simulated_reply_body = st.text_area(
        "Enter simulated reply body:",
        "Yes, I'm interested! Could you please share more details or a Calendly link?",
        height=150,
        key="sim_reply_body"
    )

    if st.button("Simulate Reply & Generate Automated Response"):
        if recipient_email_for_sim and simulated_reply_body:
            # Ensure email is not already unsubscribed or replied to
            if is_unsubscribed(db, recipient_email_for_sim):
                st.warning(f"🚫 {recipient_email_for_sim} is on the unsubscribe list. No action taken.")
                client.close()
                return
            if db[EMAIL_LOGS_COLLECTION].find_one({"recipient_email": recipient_email_for_sim, "event_type": {"$regex": "^replied_"}}):
                st.warning(f"⚠️ {recipient_email_for_sim} has already received a reply. Simulating again may lead to duplicate responses.")
                # You might want to remove this `return` in a real app to allow re-simulating
                # or add logic to handle multiple replies from the same person.

            recipient_name = "there"
            contact_in_cleaned_db = db[CLEANED_CONTACTS_COLLECTION].find_one(
                {"$or": [{"work_emails": recipient_email_for_sim}, {"personal_emails": recipient_email_for_sim}]}
            )
            if contact_in_cleaned_db and contact_in_cleaned_db.get('name'):
                recipient_name = contact_in_cleaned_db['name'].split(' ')[0]

            with st.spinner("Analyzing reply sentiment and generating response..."):
                sentiment = analyze_sentiment(simulated_reply_body)
                st.info(f"Detected sentiment: **{sentiment}**")

                # Log the incoming reply
                log_event_to_db(db, f"replied_{sentiment}", recipient_email_for_sim,
                                "Simulated Reply", simulated_reply_body, "success",
                                interest_level=sentiment)

                response_subject = ""
                response_body = ""
                event_type_response = ""

                if sentiment == 'positive':
                    response_subject, response_body = generate_meeting_link_reply(recipient_name)
                    event_type_response = "response_positive"
                elif sentiment == 'negative':
                    response_subject, response_body = generate_alternative_offer_reply(recipient_name)
                    event_type_response = "response_negative"
                else:
                    st.info("For 'neutral' or 'unknown' sentiment, no automated email is sent in this demo. Manual review is recommended.")
                    response_subject = None # Indicate no email to send

                if response_subject:
                    st.subheader(f"Generated Automated {sentiment.capitalize()} Response:")
                    st.text_input("Subject", value=response_subject, key="gen_sub", disabled=True)
                    st.text_area("Body", value=response_body, height=200, key="gen_body", disabled=True)

                    if st.button(f"Send Automated {sentiment.capitalize()} Response", key="send_sim_response_btn"):
                        if send_email_smtp_direct(recipient_email_for_sim, response_subject, response_body, db=db): # Pass db for logging
                            log_event_to_db(db, event_type_response, recipient_email_for_sim, response_subject, response_body, "success", interest_level=sentiment)
                            st.success(f"Successfully sent automated {sentiment.lower()} response to {recipient_email_for_sim}!")
                            st.experimental_rerun()
                        else:
                            st.error(f"Failed to send automated {sentiment.lower()} response to {recipient_email_for_sim}.")
                else:
                    st.info("No automated response generated for this sentiment. The reply has been logged.")
        else:
            st.warning("Please select an email and enter a simulated reply body.")

    client.close()

if __name__ == "__main__":
    main()
