from flask import Flask, request, render_template_string
from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME")

app = Flask(__name__)

# Connect to MongoDB
def get_db():
    client = MongoClient(MONGO_URI)
    db = client[MONGO_DB_NAME]
    return db

@app.route("/unsubscribe")
def unsubscribe():
    email = request.args.get("email")
    if not email:
        return render_template_string("<h2>❌ Invalid unsubscribe request.</h2>")

    db = get_db()
    # Assuming your contacts are in 'cleaned_contacts' collection
    result = db.cleaned_contacts.update_many(
        {"$or":[{"work_emails": email}, {"personal_emails": email}]},
        {"$set": {"unsubscribed": True}}
    )

    if result.modified_count > 0:
        message = f"✅ {email} has been unsubscribed successfully!"
    else:
        message = f"ℹ️ {email} was not found or already unsubscribed."

    return render_template_string(f"""
        <h2>{message}</h2>
        <p>Thank you for updating your preferences.</p>
    """)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)  # Make sure this port is open
