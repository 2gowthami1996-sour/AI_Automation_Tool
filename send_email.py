import streamlit as st
import pandas as pd
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from io import StringIO
from openai import OpenAI
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import os
from dotenv import load_dotenv
from urllib.parse import quote

# ===============================
# LOAD CONFIG
# ===============================
load_dotenv()
MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME")
client_ai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 465))

# ===============================
# HELPER FUNCTIONS
# ===============================
def get_db_connection():
    try:
        client = MongoClient(MONGO_URI)
        client.admin.command("ismaster")
        db = client[MONGO_DB_NAME]
        return client, db
    except ConnectionFailure as e:
        st.error(f"❌ Database Connection Error: {e}")
        return None, None


def fetch_cleaned_contacts(db):
    try:
        cursor = db.cleaned_contacts.find().sort("_id", -1)
        df = pd.DataFrame(list(cursor))
        if "_id" in df.columns:
            df.rename(columns={"_id": "mongo_id"}, inplace=True)
        return df
    except Exception as e:
        st.warning(f"⚠ Could not fetch contacts. Error: {e}")
        return pd.DataFrame()


def update_subject(index, email_id):
    for i, email_draft in enumerate(st.session_state.edited_emails):
        if email_draft["id"] == email_id:
            widget_key = f"subject_{email_id}_{email_draft['regen_counter']}"
            st.session_state.edited_emails[i]["subject"] = st.session_state[widget_key]
            break


def update_body(index, email_id):
    for i, email_draft in enumerate(st.session_state.edited_emails):
        if email_draft["id"] == email_id:
            widget_key = f"body_{email_id}_{email_draft['regen_counter']}"
            st.session_state.edited_emails[i]["body"] = st.session_state[widget_key]
            break


# ===============================
# EMAIL SENDING FUNCTION (SMTP)
# ===============================
def send_marketing_email(to_email, subject, html_body):
    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = EMAIL_USER
        msg["To"] = to_email
        msg["Subject"] = subject

        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
            server.login(EMAIL_USER, EMAIL_PASSWORD)
            server.send_message(msg)

        return True, f"✅ Sent to {to_email}"
    except Exception as e:
        return False, f"❌ Failed to send to {to_email}: {e}"


# ===============================
# HTML TEMPLATE + UNSUBSCRIBE
# ===============================
def append_unsubscribe_link(body_html, recipient_email):
    unsubscribe_section = f"""
    <hr style="border:none;border-top:1px solid #ddd;margin-top:30px;margin-bottom:10px;">
    <p style="font-size:12px;color:#777;text-align:center;">
        If you prefer not to receive future emails, you can 
        <a href="https://www.morphius.in/unsubscribe?email={quote(recipient_email)}" 
           style="color:#777;text-decoration:underline;">unsubscribe here</a>.
    </p>
    """
    return body_html.strip() + unsubscribe_section


def generate_personalized_email_body(contact_details):
    name = contact_details.get("name")
    domain = contact_details.get("domain", "your industry")
    email = contact_details.get("work_emails") or contact_details.get("personal_emails", "")
    greeting_name = f"{name}" if pd.notna(name) and name.strip() else "there"

    try:
        prompt = f"""
        Write a stylish marketing email in HTML for {name} from Morphius AI.
        Focus on {domain} sector, keep it short, engaging, and professional.
        Add CTA button 'Learn More' (https://www.morphius.in).
        Include logo header, brand colors (#2b6cb0), and unsubscribe footer.
        """
        response = client_ai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a professional email marketer who writes in HTML with inline styles."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=450,
            temperature=0.8,
        )
        html_body = response.choices[0].message.content.strip()
    except Exception as e:
        st.warning(f"⚠ OpenAI API failed. Using fallback design. (Error: {e})")
        html_body = f"""
        <html>
        <body style="font-family:Arial, sans-serif;color:#333;line-height:1.6;background-color:#f4f6f8;padding:0;margin:0;">
            <div style="max-width:600px;margin:auto;background-color:#fff;border-radius:8px;overflow:hidden;box-shadow:0 2px 6px rgba(0,0,0,0.1);">
                
                <div style="background-color:#2b6cb0;padding:20px;text-align:center;">
                    <img src="https://www.morphius.in/assets/logo.png" alt="Morphius AI" style="width:140px;">
                </div>

                <div style="padding:30px;">
                    <h2 style="color:#2b6cb0;">Hi {greeting_name},</h2>
                    <p>
                        At <strong>Morphius AI</strong>, we specialize in creating intelligent automation tools 
                        tailored for businesses in the {domain} sector. Our AI solutions empower teams 
                        to improve productivity and customer engagement.
                    </p>
                    <p>
                        Let’s explore how Morphius AI can help your organization accelerate innovation.
                    </p>

                    <div style="text-align:center;margin:30px 0;">
                        <a href="https://www.morphius.in/" 
                           style="background-color:#2b6cb0;color:#fff;padding:12px 28px;
                                  border-radius:6px;text-decoration:none;font-weight:bold;">
                           Learn More
                        </a>
                    </div>

                    <p>Best regards,<br>
                    <strong>Gowthami</strong><br>
                    Employee, Morphius AI<br>
                    <a href="https://www.morphius.in/" style="color:#2b6cb0;text-decoration:none;">www.morphius.in</a></p>
                </div>
            </div>
        </body>
        </html>
        """

    return append_unsubscribe_link(html_body, email)


# ===============================
# MAIN STREAMLIT APP
# ===============================
def main():
    st.set_page_config(page_title="Morphius AI Email Generator", page_icon="📧", layout="wide")
    st.title("📧 Morphius AI: Marketing Email Generator & Sender")

    if "edited_emails" not in st.session_state:
        st.session_state.edited_emails = []
    if "filter_domain" not in st.session_state:
        st.session_state.filter_domain = None

    client_mongo, db = get_db_connection()
    if not client_mongo:
        return

    st.header("Step 1: Filter Contacts by Prompt")
    prompt = st.text_input("Enter a prompt (e.g., 'top 10 edtech companies', 'e-commerce startups')", key="prompt_input")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔍 Filter Contacts"):
            if prompt:
                domain = prompt.lower().split()[0]
                st.session_state.filter_domain = domain
                st.success(f"Filtered contacts for domain: *{domain}*")
                st.rerun()
            else:
                st.warning("Please enter a prompt first.")
    with col2:
        if st.button("🔄 Show All Contacts"):
            st.session_state.filter_domain = None
            st.rerun()

    st.header("Step 2: Select Contacts & Generate Drafts")
    contacts_df = fetch_cleaned_contacts(db)
    client_mongo.close()
    if contacts_df.empty:
        st.info("No contacts found.")
        return

    display_df = contacts_df.copy()
    if st.session_state.filter_domain:
        display_df = contacts_df[
            contacts_df["domain"].str.contains(st.session_state.filter_domain, case=False, na=False)
        ].copy()
        st.info(f"Showing {len(display_df)} contacts matching domain '{st.session_state.filter_domain}'")

    if "Select" not in display_df.columns:
        display_df.insert(0, "Select", False)

    select_all = st.checkbox("Select All Contacts", value=False)
    if select_all:
        display_df["Select"] = True

    edited_df = st.data_editor(display_df, hide_index=True, disabled=list(display_df.columns.drop("Select")), key="data_editor")
    selected_rows = edited_df[edited_df["Select"]]

    if st.button(f"Generate Drafts for {len(selected_rows)} Selected Contacts", disabled=selected_rows.empty):
        st.session_state.edited_emails = []
        for i, row in selected_rows.iterrows():
            to_email = row.get("work_emails") or row.get("personal_emails", "")
            if not isinstance(to_email, str) or not to_email.strip():
                st.warning(f"⚠️ Skipped '{row.get('name', 'Unknown')}' - no valid email.")
                continue

            to_email = to_email.split(",")[0].strip()
            body = generate_personalized_email_body(row)
            st.session_state.edited_emails.append({
                "id": i, "name": row["name"], "to_email": to_email,
                "subject": "Discover How Morphius AI Can Help You", "body": body,
                "contact_details": row.to_dict(), "regen_counter": 0
            })
        st.rerun()

    if st.session_state.edited_emails:
        st.header("Step 3: Review & Send Drafts")
        for i, email_draft in enumerate(st.session_state.edited_emails):
            unique_id = email_draft["id"]
            regen_count = email_draft["regen_counter"]
            with st.expander(f"Draft for {email_draft['name']} <{email_draft['to_email']}>", expanded=True):
                st.text_input("Subject", value=email_draft["subject"],
                              key=f"subject_{unique_id}_{regen_count}", on_change=update_subject, args=(i, unique_id))
                st.text_area("Body (HTML)", value=email_draft["body"], height=200,
                             key=f"body_{unique_id}_{regen_count}", on_change=update_body, args=(i, unique_id))

                st.markdown("#### ✉️ Email Preview")
                st.markdown(email_draft["body"], unsafe_allow_html=True)

        # Download option
        st.markdown("### 📥 Download All Drafts")
        df_export = pd.DataFrame(st.session_state.edited_emails)[["name", "to_email", "subject", "body"]]
        csv_buffer = StringIO()
        df_export.to_csv(csv_buffer, index=False)
        st.download_button("⬇ Download Drafts as CSV", data=csv_buffer.getvalue(),
                           file_name="morphius_email_drafts.csv", mime="text/csv", use_container_width=True)

        # Send all emails
        st.markdown("### 🚀 Send All Marketing Emails")
        if st.button("📤 Send All Emails via SMTP", use_container_width=True):
            sent_count = 0
            failed_count = 0
            for draft in st.session_state.edited_emails:
                success, msg = send_marketing_email(draft["to_email"], draft["subject"], draft["body"])
                if success:
                    st.toast(msg)
                    sent_count += 1
                else:
                    st.error(msg)
                    failed_count += 1
            st.success(f"✅ Sent {sent_count} emails successfully!")
            if failed_count > 0:
                st.warning(f"⚠️ {failed_count} emails failed to send.")


if __name__ == "__main__":
    main()
