if not all([OPENAI_API_KEY, SMTP_SERVER, SMTP_PORT, SENDER_EMAIL, SENDER_PASSWORD]):
    st.error("⚠️ **Missing Environment Variables!** Please ensure `OPENAI_API_KEY`, `SMTP_SERVER`, `SMTP_PORT`, `SENDER_EMAIL`, and `SENDER_PASSWORD` are set in your `.env` file for AI and email sending functionality.")
    return

client, db = get_db_connection()
if not client:
    return

setup_db_indexes(db)

st.subheader("Simulate Incoming Replies and Automate Actions")

# Fetch initial outreach emails that haven't received a clear reply yet
# An email is considered "unreplied" if:
# 1. It's an 'initial_outreach' or 'follow_up_sent'
# 2. There's no later 'replied_' event for the same recipient

# Get all distinct recipients from initial outreach / follow-ups
sent_emails_cursor = db[EMAIL_LOGS_COLLECTION].aggregate([
    {"$match": {"event_type": {"$in": ["initial_outreach", "follow_up_sent"]}}},
    {"$group": {
        "_id": "$recipient_email",
        "last_sent_subject": {"$last": "$subject"},
        "last_sent_body": {"$last": "$body"},
        "last_sent_timestamp": {"$last": "$timestamp"},
        "sent_event_type": {"$last": "$event_type"},
        "initial_sent_timestamp": {"$first": "$timestamp"}, # For calculating grace period from first mail
        "total_follow_ups_sent": {"$sum": {"$cond": [{"$eq": ["$event_type", "follow_up_sent"]}, 1, 0]}}
    }}
])

# Convert to DataFrame for easier processing
all_sent_df = pd.DataFrame(list(sent_emails_cursor))

if all_sent_df.empty:
    st.info("No initial outreach or follow-up emails have been sent yet.")
    client.close()
    return

# Filter out emails that have already received a reply (any type)
replied_emails = db[EMAIL_LOGS_COLLECTION].find({"event_type": {"$regex": "^replied_"}}).distinct("recipient_email")
pending_emails_df = all_sent_df[~all_sent_df['_id'].isin(replied_emails)].copy()

if pending_emails_df.empty:
    st.info("All sent emails have received a reply or are being processed.")
    client.close()
    return

# Check for unsubscribed emails
pending_emails_df = pending_emails_df[
    ~pending_emails_df['_id'].apply(lambda x: is_unsubscribed(db, x))
].copy()

if pending_emails_df.empty:
    st.info("All pending emails are either unsubscribed or have received a reply.")
    client.close()
    return

# Determine actions for each pending email
actions_to_take = []
now_utc = datetime.datetime.now(datetime.timezone.utc)

for index, row in pending_emails_df.iterrows():
    email_addr = row['_id']
    last_sent_ts = row['last_sent_timestamp'].replace(tzinfo=pytz.utc) if row['last_sent_timestamp'].tzinfo is None else row['last_sent_timestamp']
    
    time_since_last_sent = (now_utc - last_sent_ts).total_seconds() / 60
    
    # Determine the name to use in the email
    contact_name = "there" # Default if name not found
    contact_in_cleaned_db = db[CLEANED_CONTACTS_COLLECTION].find_one(
        {"$or": [{"work_emails": email_addr}, {"personal_emails": email_addr}]}
    )
    if contact_in_cleaned_db and contact_in_cleaned_db.get('name'):
        contact_name = contact_in_cleaned_db['name'].split(' ')[0] # Use first name

    if time_since_last_sent >= FOLLOW_UP_GRACE_PERIOD_MINUTES:
        # It's time for a follow-up IF we haven't reached max follow-ups
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
            # Max follow-ups reached, move to unsubscribe
            actions_to_take.append({
                "email": email_addr,
                "action_type": "unsubscribe",
                "reason": f"Reached max follow-ups ({MAX_FOLLOW_UPS_BEFORE_UNSUBSCRIBE}) without reply.",
                "recipient_name": contact_name
            })
    # For simplicity in this demo, emails that are within the grace period will just wait.
    # In a real app, you might show them as "awaiting reply."

if not actions_to_take:
    st.info(f"No immediate actions needed for pending emails. All are within the {FOLLOW_UP_GRACE_PERIOD_MINUTES}-minute grace period or already handled.")
    client.close()
    return

st.subheader("Pending Actions")
st.table(pd.DataFrame(actions_to_take).drop(columns=['recipient_name', 'previous_subject', 'follow_up_count'], errors='ignore'))


if st.button("Simulate & Process Actions"):
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
            if send_email_smtp_direct(action['email'], subject, body):
                log_event_to_db(db, "follow_up_sent", action['email'], subject, body, "success",
                                follow_up_count=action['follow_up_count'])
                st.success(f"✅ Sent follow-up {action['follow_up_count']} to {action['email']}")
            else:
                log_event_to_db(db, "follow_up_sent", action['email'], subject, body, "failed",
                                follow_up_count=action['follow_up_count'])
                st.error(f"❌ Failed to send follow-up to {action['email']}")
        
        elif action['action_type'] == "unsubscribe":
            add_to_unsubscribe_list(db, action['email'], action['reason'])
            log_event_to_db(db, "unsubscribed_automated", action['email'], "N/A", action['reason'], "success")
        
        time.sleep(1) # Simulate some work

    processing_message.empty()
    st.success("All pending actions processed!")
    st.experimental_rerun() # Refresh the page to show updated status

st.markdown("---")
st.subheader("Manually Simulate a Reply (for testing AI response generation)")

recipient_email_for_sim = st.selectbox(
    "Select an email to simulate a reply for:",
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

            # Generate and send automated response based on sentiment
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
                # Still log the action of not sending a response if desired
                log_event_to_db(db, f"no_automated_response_{sentiment}", recipient_email_for_sim, 
                                "N/A", "No automated response due to neutral/unknown sentiment", "info")
                response_subject = None # Indicate no email to send
            
            if response_subject:
                st.subheader(f"Generated Automated {sentiment.capitalize()} Response:")
                st.text_input("Subject", value=response_subject, key="gen_sub", disabled=True)
                st.text_area("Body", value=response_body, height=200, key="gen_body", disabled=True)
                
                if st.button(f"Send Automated {sentiment.capitalize()} Response"):
                    if send_email_smtp_direct(recipient_email_for_sim, response_subject, response_body):
                        log_event_to_db(db, event_type_response, recipient_email_for_sim, response_subject, response_body, "success", interest_level=sentiment)
                        st.success(f"Successfully sent automated {sentiment.lower()} response to {recipient_email_for_sim}!")
                        st.experimental_rerun()
                    else:
                        log_event_to_db(db, event_type_response, recipient_email_for_sim, response_subject, response_body, "failed", interest_level=sentiment)
                        st.error(f"Failed to send automated {sentiment.lower()} response to {recipient_email_for_sim}.")
            else:
                st.info("No automated response generated for this sentiment. The reply has been logged.")
    else:
        st.warning("Please select an email and enter a simulated reply body.")

client.close()
