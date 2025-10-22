
# 🧠 AI Automation Tool  
### Internal Client Acquisition & Smart Email Outreach  

**Version:** 1.0      #it indicates the current release or maturity level of your project.

**Owner:** Growth Engineering Team  

**Status:** Active Development  

---

## 🚀 Overview  
The **AI Automation Tool** is an internal system designed to **discover qualified prospects**, **generate personalized outreach emails using AI**, and **automate compliant follow-up workflows** — all from a unified dashboard.  

It integrates AI models, database storage, and email sending modules into one streamlined workflow, reducing manual effort and improving lead engagement rates.  

---

## 🧩 Key Features  

✅ **Prospect Discovery & Data Ingestion**  
- Import leads via CSV or approved web scraping sources  
- Automatically cleans and validates lead data  
- Stores data securely in MongoDB  

✅ **AI-Powered Email Drafting**  
- Uses **OpenAI API** to generate personalized, compliant email content  
- Context-aware templates based on role, company, and value proposition  
- Human review step before sending  

✅ **Automated Email Sending**  
- Sends emails via **SMTP**  
- Supports subject, body, and signature variables  
- Built-in unsubscribe and logging support  

✅ **Streamlit Dashboard (Operator UI)**  
- Visual interface for monitoring and approving emails  
- Upload, filter, and review prospects  
- View reply logs, error reports, and performance summaries  

✅ **Compliance-First Architecture**  
- Tracks lawful basis and consent  
- Ensures one-click unsubscribe in every message  
- Transparent storage of sender identity and message logs  

---

## 🏗️ Architecture Overview  

```text
1. Data Ingestion  →  2. Cleaning & Enrichment  →  3. AI Draft Generation
         ↓                         ↓                          ↓
  MongoDB Storage ←  Streamlit Review Dashboard  ←  Email Sending & Logs
```

- **Backend**: Python  
- **Frontend**: Streamlit  
- **Database**: MongoDB  
- **AI Engine**: OpenAI GPT models  
- **Email Service**: SMTP  
- **Environment Management**: dotenv  

---

## ⚙️ Tech Stack  

| Layer | Tools / Libraries |
|-------|--------------------|
| 🧮 Core Logic | Python 3.x |
| 🧠 AI Email Generation | OpenAI API |
| 📊 UI Dashboard | Streamlit |
| 🗃️ Database | MongoDB |
| 📬 Email Sending | SMTP |
| 🧰 Utilities | Pandas, BeautifulSoup, Requests, SerpAI |
| 🔐 Security | .env secrets, tokenized access |

---

## 🧠 Workflow  

1. **Upload Prospects** → via CSV or web scraper (`ai_webscraper.py`)  
2. **Data Processing** → cleaned using `clean_data.py`  
3. **AI Email Draft Generation** → via `send_email.py` (OpenAI prompt-based)  
4. **Human Review & Approval** → through Streamlit UI (`app.py`)  
5. **Send Email** → using `send_email.py`  
6. **Monitor Replies** → auto-detection of responses and logs  

---

## 📁 Project Structure  

```bash
AI_Automation_Tool/
│
├── app.py                # Streamlit dashboard for operator UI
├── reply.py              # AI email generation logic (OpenAI)
├── send_email.py         # Handles sending emails using Yagmail
├── ai_webscraper.py      # Web scraping for permitted sources
├── clean_data.py         # Cleans and validates prospect data
├── database.py           # MongoDB connection and CRUD operations
├── .env                  # Environment variables (keys, URIs)
├── requirements.txt      # Dependencies list
└── README.md             # Project documentation (this file)
```

---

## 📦 Installation  

1. **Clone this repository**
   ```bash
   git clone https://github.com/2gowthami1996-sour/AI_Automation_Tool.git
   cd AI_Automation_Tool
   ```

2. **Create and activate virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate   # macOS/Linux
   venv\Scripts\activate      # Windows
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Add your `.env` file**  
   Include:
   ```env
   MONGO_URI=<your_mongodb_connection_string>
   OPENAI_API_KEY=<your_openai_key>
   EMAIL_USER=<your_email>
   EMAIL_PASS=<your_app_password>
   ```

5. **Run the app**
   ```bash
   streamlit run app.py
   ```

---

## 📊 Sample AI-Generated Email  

<img width="964" height="374" alt="image" src="https://github.com/user-attachments/assets/9158d7f8-6060-42f9-84c8-a39e17029605" />


---

## 🔒 Compliance & Data Protection  

- Follows **CAN-SPAM, GDPR, and DPDP Act (India)**  
- One-click unsubscribe link mandatory in every email  
- No scraping of unlicensed or non-consented data sources  

---

## 📈 Future Enhancements  

- ✅ Smart throttling and inbox warm-up  
- ✅ Engagement tracking and reply sentiment classification  
- ✅ AI-assisted reply handling (smart follow-ups)  
- ✅ Centralized analytics dashboard  

---

## 👩‍💻 Contributors  

**Owner:** G. Gowthami  
**Role:** Growth Engineering | AI Automation & Data Scientist  
