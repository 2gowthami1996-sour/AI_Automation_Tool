import streamlit as st
import pandas as pd
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from io import StringIO
from openai import OpenAI
import os
from dotenv import load_dotenv

# ===============================
# LOAD CONFIG
# ===============================
load_dotenv()
MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client_ai = OpenAI(api_key=OPENAI_API_KEY)

# ===============================
# HELPERS
# ===============================
def get_db_connection():
    try:
        client = MongoClient(MONGO_URI)
        client.admin.command('ismaster')
        db = client[MONGO_DB_NAME]
        return client, db
    except ConnectionFailure as e:
        st.error(f"❌ Database Connection Error: {e}")
        return None, None

def fetch_cleaned_contacts(db):
    try:
        cursor = db.cleaned_contacts.find().sort('_id', -1)
        df = pd.DataFrame(list(cursor))
        if '_id' in df.columns:
            df.rename(columns={'_id': 'mongo_id'}, inplace=True)
        return df
    except Exception as e:
        st.warning(f"⚠ Could not fetch contacts. Error: {e}")
        return pd.DataFrame()

# ===============================
# UNSUBSCRIBE LINK HELPER
# ===============================
def append_unsubscribe_link(body_html, recipient_email):
    unsubscribe_html = f"""
<p>If you'd like to unsubscribe and stop receiving these emails, 
<a href="https://www.morphius.in/unsubscribe?email={recipient_email}">click here</a>.</p>
"""
    return body_html.strip() + unsubscribe_html

# ===============================
# EMAIL BODY GENERATION
# ===============================
def generate_personalized_email_body(contact_details):
    name = contact_details.get('name', 'Sir/Madam')
    domain = contact_details.get('domain', 'their sector')
    email = (contact_details.get('work_emails') or contact_details.get('personal_emails') or '')

    # HTML email components
    greeting = f"<p>Dear {name},</p>"
    body_text = f"""
<p>I hope this message finds you well. My name is G Gowthami, and I am reaching out on behalf of Morphius AI, 
where we specialize in delivering cutting-edge AI solutions to enhance operational efficiency and innovation.</p>

<p>We understand the unique challenges in the {domain} sector and would love to explore potential collaboration opportunities.</p>
"""
    signature = f"""
<p>Best regards,<br>
Gowthami<br>
Employee, Morphius AI<br>
<a href="https://www.morphius.in/">https://www.morphius.in/</a></p>
"""

    full_body = greeting + body_text + signature
    return append_unsubscribe_link(full_body, email)

# ===============================
# STREAMLIT APP
# ===============================
def main():
    st.set_page_config(page_title="Morphius AI: Email Generator", layout="wide")
    st.title("📧 Morphius AI: Generate & Edit HTML Email Drafts")

    if 'edited_emails' not in st.session_state:
        st.session_state.edited_emails = []

    client_mongo, db = get_db_connection()
    if not client_mongo:
        return

    # Step 1: Load contacts
    contacts_df = fetch_cleaned_contacts(db)
    client_mongo.close()
    if contacts_df.empty:
        st.info("No contacts found.")
        return

    st.header("Step 1: Select Contacts")
    if 'Select' not in contacts_df.columns:
        contacts_df.insert(0, "Select", False)

    select_all = st.checkbox("Select All Contacts", value=False)
    if select_all:
        contacts_df['Select'] = True

    edited_df = st.data_editor(contacts_df, hide_index=True, disabled=list(contacts_df.columns.drop("Select")), key="data_editor")
    selected_rows = edited_df[edited_df['Select']]

    # Step 2: Generate drafts
    if st.button(f"Generate Drafts for {len(selected_rows)} Selected Contacts", disabled=selected_rows.empty):
        st.session_state.edited_emails = []
        for i, row in selected_rows.iterrows():
            to_email = None
            if isinstance(row.get('work_emails'), str) and row['work_emails'].strip():
                to_email = row['work_emails'].split(',')[0].strip()
            elif isinstance(row.get('personal_emails'), str) and row['personal_emails'].strip():
                to_email = row['personal_emails'].split(',')[0].strip()
            else:
                st.warning(f"⚠ Skipped '{row.get('name', 'Unknown')}' - no valid email.")
                continue

            body_html = generate_personalized_email_body(row)
            st.session_state.edited_emails.append({
                "id": i,
                "name": row['name'],
                "to_email": to_email,
                "subject": "Connecting from Morphius AI",
                "body": body_html,
                "contact_details": row.to_dict()
            })
        st.success(f"✅ Generated {len(st.session_state.edited_emails)} email drafts.")

    # Step 3: Review drafts
    if st.session_state.edited_emails:
        st.header("Step 3: Review & Download Drafts")
        for i, email_draft in enumerate(st.session_state.edited_emails):
            with st.expander(f"Draft for {email_draft['name']} <{email_draft['to_email']}>", expanded=True):
                st.text_input("Subject", value=email_draft['subject'], key=f"subject_{i}")
                st.text_area("Body (HTML)", value=email_draft['body'], height=250, key=f"body_{i}")

        # Download as CSV
        df_export = pd.DataFrame(st.session_state.edited_emails)[["name", "to_email", "subject", "body"]]
        csv_buffer = StringIO()
        df_export.to_csv(csv_buffer, index=False)
        st.download_button("⬇ Download Drafts as CSV", data=csv_buffer.getvalue(),
                           file_name="morphius_email_drafts.csv", mime="text/csv", use_container_width=True)

if __name__ == "__main__":
    main()
