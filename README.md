# Roar Ladies Roar — Conference & Attendance API

Production-ready backend API service for **Roar Ladies Roar Ministry**:
- Pre-Registration with automatic Pass ID generation (`RLR-XXXX-2026`).
- Event-day Attendance Check-In (Present / Pending).
- **Neon PostgreSQL** serverless cloud database persistence.
- **Arkesel SMS Gateway** (`sms.arkesel.com`) for automated instant confirmation SMS and broadcast reminders.
- Deployable to **Vercel Serverless**, Render, or Railway.

---

## 🚀 Quick Start (Local Development)

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Fill in your credentials:
- `DATABASE_URL`: Your Neon PostgreSQL connection string.
- `ARKESEL_API_KEY`: Your API key from [arkesel.com](https://arkesel.com).
- `ARKESEL_SENDER_ID`: Your registered Sender ID (e.g., `RLRMinistry`).

*(If no `DATABASE_URL` is set, the API automatically runs in safe in-memory fallback mode).*

### 3. Run Server
```bash
python3 -m uvicorn main:app --reload --port 8000
```

- **Interactive Swagger Docs**: `http://127.0.0.1:8000/docs`
- **Health Check**: `http://127.0.0.1:8000/api/health`

---

## 📡 API Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/register` | Pre-register attendee & trigger instant Arkesel SMS |
| `GET` | `/api/registrations` | List all attendees with check-in status |
| `POST` | `/api/attendance/{id}` | Mark attendee present (Checked In) |
| `DELETE` | `/api/attendance/{id}` | Unmark check-in (Undo) |
| `GET` | `/api/stats` | Live counts (Total, Checked In, In-Person, Virtual) |
| `POST` | `/api/sms/send` | Send individual SMS |
| `POST` | `/api/sms/broadcast` | Broadcast reminder SMS (`all`, `pending`, `checked_in`) |

---

## 🚢 Vercel Serverless Deployment

1. Push this repository to GitHub:
   ```bash
   git init
   git add .
   git commit -m "feat: initial commit for Roar Ladies Roar API"
   git remote add origin https://github.com/YOUR_USERNAME/roar-ladies-roar-api.git
   git push -u origin main
   ```
2. Import the repository into **Vercel**.
3. Add Environment Variables in Vercel project settings:
   - `DATABASE_URL`
   - `ARKESEL_API_KEY`
   - `ARKESEL_SENDER_ID`
4. Click **Deploy**. Vercel will automatically configure the Python serverless runtime using `vercel.json`!
