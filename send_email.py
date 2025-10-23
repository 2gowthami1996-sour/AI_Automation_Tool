import os
import streamlit as st
import pandas as pd
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from urllib.parse import quote

# --- SMTP CONFIG ---
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 465))
EMAIL_USER = os.getenv("EMAIL_USER", "youremail@morphius.in")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "your_app_password")


# --- EMAIL TEMPLATE (Stylish HTML) ---
def generate_email_html(recipient_name, recipient_email):
    unsubscribe_link = f"https://www.morphius.in/unsubscribe?email={quote(recipient_email)}"

    html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; margin:0; padding:0; background-color:#f7f7f7;">
      <table align="center" border="0" cellpadding="0" cellspacing="0" width="600"
             style="border-collapse: collapse; background-color: #ffffff; border-radius: 12px;
                    box-shadow: 0 3px 8px rgba(0,0,0,0.1); overflow:hidden;">

        <!-- Header -->
        <tr>
          <td align="center" bgcolor="#1a73e8" style="padding: 25px 0;">
            <h2 style="color: #ffffff; margin: 0;">Morphius AI</h2>
            <p style="color: #d2e3fc; margin: 0;">Innovating with Intelligence</p>
          </td>
        </tr>

        <!-- Body -->
        <tr>
          <td style="padding: 30px 40px; color: #333333;">
            <p>Hi {recipient_name},</p>
            <p>
              I hope this message finds you well. My name is <b>Gowthami</b>, and I am reaching out from
              <b>Morphius AI</b>. We are a leading company in the AI sector, dedicated to providing
              cutting-edge technology solutions that empower businesses to reach their full potential.
            </p>
            <p>
              I came across your profile and was impressed by your expertise in the industry.
              At Morphius AI, we believe collaboration can drive innovation and open exciting opportunities.
            </p>
            <p>
              I would love to discuss how our solutions can help your organization or explore
              collaboration possibilities. Please let me know if you’re available for a brief
              conversation at your convenience.
            </p>
            <p>Thank you for your time. I look forward to connecting with you!</p>
            <p>Best regards,<br>
            <b>Gowthami</b><br>
            Employee, Morphius AI<br>
            <a href="https://www.morphius.in" style="color:#1a73e8;">www.morphius.in</a></p>

            <!-- CTA Button -->
            <div style="text-align: center; margin-top: 30px;">
              <a href="https://www.morphius.in/contact"
                 style="background-color:#1a73e8; color:#ffffff; text-decoration:none;
                        padding:12px 24px; border-radius:6px; display:inline-block; font-weight:bold;">
                Schedule a Call
              </a>
            </div>
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td align="center" bgcolor="#f1f3f4" style="padding: 20px; font-size: 13px; color: #666;">
            If you prefer not to receive future emails, you can
            <a href="{unsubscribe_link}" style="color:#1a73e8;">unsubscribe here</a>.
          </td>
        </tr>
      </table>
    </body>
    </html>
    """
    return html


# --- SMTP SENDER ---
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
        return True, f"✅ Email sent to {to_email}"

    except Exception as e:
        return False, f"❌ Failed to send to {to_email}: {e}"


# --- STREAMLIT UI ---
st.set_page_config(page_title="Morphius AI Email Sender", page_icon="📧", layout="centered")

st.title("📧 Morphius AI – Stylish Marketing Email Sender")

st.write("Send personalized HTML marketing emails to your contacts instantly via SMTP.")

uploaded_file = st.file_uploader("Upload your contact list (CSV with Name and Email columns)", type=["csv"])

if uploaded_file:
    df = pd.read_csv(uploaded_file)
    st.dataframe(df.head())

    if st.button("Preview Emails"):
        st.session_state.previews = []
        for _, row in df.iterrows():
            name = row.get("Name", "there")
            email = row.get("Email")
            html = generate_email_html(name, email)
            st.session_state.previews.append({"name": name, "email": email, "html": html})

        st.success("✅ Email drafts generated successfully!")

    if "previews" in st.session_state:
        st.markdown("### ✉️ Preview and Send")
        for draft in st.session_state.previews:
            with st.expander(f"📩 {draft['name']} ({draft['email']})"):
                st.markdown(draft["html"], unsafe_allow_html=True)

        if st.button("📤 Send All Emails via SMTP", use_container_width=True):
            sent_count, failed_count = 0, 0
            for draft in st.session_state.previews:
                success, msg = send_marketing_email(
                    draft["email"],
                    "Exploring Collaboration Opportunities with Morphius AI",
                    draft["html"]
                )
                if success:
                    st.toast(msg)
                    sent_count += 1
                else:
                    st.error(msg)
                    failed_count += 1

            st.success(f"✅ {sent_count} emails sent successfully!")
            if failed_count:
                st.warning(f"⚠️ {failed_count} failed to send.")
