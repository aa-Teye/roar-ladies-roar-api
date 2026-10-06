import os
import random
import string
import requests
from datetime import datetime
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(
    title="Roar Ladies Roar - Conference & Attendance API",
    description="Backend API for Roar Ladies Roar Ministry: Pre-registration, Event-day Attendance, Neon PostgreSQL, and Arkesel SMS.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# Enable CORS for all frontend origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE_URL = os.getenv("DATABASE_URL", "")
ARKESEL_API_KEY = os.getenv("ARKESEL_API_KEY", "")
ARKESEL_SENDER_ID = os.getenv("ARKESEL_SENDER_ID", "RLRMinistry")

# In-memory store fallback when DATABASE_URL is not yet set
_memory_registrations: Dict[str, Dict[str, Any]] = {}
_memory_attendance: Dict[str, Dict[str, Any]] = {}


# ── Arkesel SMS Helper ────────────────────────────────────────────────────────
def normalize_phone_for_arkesel(phone_str: str) -> str:
    """Normalizes phone number to international format without leading + for Arkesel."""
    if not phone_str:
        return ""
    digits = "".join(ch for ch in phone_str if ch.isdigit() or ch == "+")
    if digits.startswith("+233"):
        return digits[1:]
    if digits.startswith("233"):
        return digits
    if digits.startswith("0") and len(digits) >= 10:
        return "233" + digits[1:]
    if digits.startswith("+"):
        return digits[1:]
    return digits


def send_arkesel_sms(recipients: List[str], message: str) -> Dict[str, Any]:
    """Sends SMS via Arkesel V2 API."""
    clean_recipients = [normalize_phone_for_arkesel(p) for p in recipients if p]
    clean_recipients = [p for p in clean_recipients if p]

    if not clean_recipients:
        return {"status": "error", "message": "No valid recipient phone numbers"}

    if not ARKESEL_API_KEY:
        print(f"[Arkesel SMS Mock] (Key not configured) To: {clean_recipients} | Msg: {message}")
        return {
            "status": "mocked",
            "message": "SMS simulated locally. Set ARKESEL_API_KEY in .env for live SMS delivery.",
            "recipients": clean_recipients,
        }

    url = "https://sms.arkesel.com/api/v2/sms/send"
    headers = {
        "api-key": ARKESEL_API_KEY,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    payload = {
        "sender": ARKESEL_SENDER_ID,
        "message": message,
        "recipients": clean_recipients,
    }

    try:
        res = requests.post(url, json=payload, headers=headers, timeout=10)
        return res.json()
    except Exception as e:
        print(f"[Arkesel SMS Error] {e}")
        return {"status": "error", "error": str(e)}


# ── Database Helpers ──────────────────────────────────────────────────────────
def get_db_connection():
    if not DATABASE_URL:
        return None
    url = DATABASE_URL
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    try:
        conn = psycopg2.connect(url, sslmode="require")
        return conn
    except Exception as e:
        print(f"[DB Warning] Could not connect to Neon PostgreSQL: {e}")
        return None


def init_db():
    conn = get_db_connection()
    if not conn:
        print("[DB Info] Running in in-memory mode. Add DATABASE_URL in .env to connect to Neon.")
        return

    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS registrations (
                    id VARCHAR(64) PRIMARY KEY,
                    title VARCHAR(32),
                    full_name VARCHAR(255) NOT NULL,
                    phone VARCHAR(64) NOT NULL,
                    email VARCHAR(255),
                    age VARCHAR(32),
                    member_status VARCHAR(128),
                    first_timer VARCHAR(32),
                    attendance_mode VARCHAR(64),
                    location VARCHAR(255),
                    referral VARCHAR(128),
                    invited_by VARCHAR(255),
                    prayer_request TEXT,
                    registered_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS attendance (
                    id SERIAL PRIMARY KEY,
                    registration_id VARCHAR(64) NOT NULL REFERENCES registrations(id) ON DELETE CASCADE,
                    checked_in_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                    marked_by VARCHAR(64) DEFAULT 'usher',
                    UNIQUE(registration_id)
                );
            """)
            conn.commit()
            print("[DB Success] Neon PostgreSQL tables verified/initialized.")
    except Exception as e:
        print(f"[DB Error] Failed to initialize tables: {e}")
    finally:
        conn.close()


@app.on_event("startup")
def on_startup():
    init_db()


# ── Pydantic Request Models ────────────────────────────────────────────────────
class RegistrationCreate(BaseModel):
    title: Optional[str] = ""
    fullName: str
    phone: str
    email: Optional[str] = ""
    age: Optional[str] = ""
    memberStatus: Optional[str] = ""
    firstTimer: Optional[str] = ""
    attendanceMode: Optional[str] = "Yes, in person"
    location: str
    referral: Optional[str] = ""
    invitedBy: Optional[str] = ""
    prayerRequest: Optional[str] = ""


class SingleSMSRequest(BaseModel):
    recipient: str
    message: str


class BroadcastSMSRequest(BaseModel):
    target: str = "all"  # 'all' | 'pending' | 'checked_in'
    message: str


# ── Root & Health Endpoints ───────────────────────────────────────────────────
@app.get("/")
def root():
    return {
        "service": "Roar Ladies Roar Ministry API",
        "status": "online",
        "documentation": "/docs",
        "health": "/api/health",
    }


@app.get("/api/health")
def health():
    db_connected = bool(get_db_connection())
    sms_configured = bool(ARKESEL_API_KEY)
    return {
        "status": "healthy",
        "service": "Roar Ladies Roar API",
        "database": "Neon PostgreSQL" if db_connected else "In-Memory Fallback",
        "db_connected": db_connected,
        "arkesel_sms_configured": sms_configured,
        "time": datetime.utcnow().isoformat(),
    }


def format_display_name(title: Optional[str], full_name: str) -> str:
    t = (title or '').strip()
    fn = (full_name or '').strip()
    if not t:
        return fn
    if t in ['Mr', 'Mrs', 'Ms', 'Dr', 'Rev', 'Sis']:
        return f"{t}. {fn}"
    return f"{t} {fn}"

# ── Attendee Pre-Registration ─────────────────────────────────────────────────
@app.post("/api/register", status_code=status.HTTP_201_CREATED)
def register_attendee(payload: RegistrationCreate):
    # Generate unique 5-char conference pass ID: e.g. RLR-A9X2K-2026
    code = "".join(random.choices(string.ascii_uppercase + string.digits, k=5))
    reg_id = f"RLR-{code}-2026"
    now_iso = datetime.utcnow().isoformat()
    display_name = format_display_name(payload.title, payload.fullName)

    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO registrations (
                        id, title, full_name, phone, email, age, member_status,
                        first_timer, attendance_mode, location, referral, invited_by,
                        prayer_request, registered_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    reg_id,
                    payload.title,
                    payload.fullName.strip(),
                    payload.phone.strip(),
                    payload.email.strip() if payload.email else None,
                    payload.age,
                    payload.memberStatus,
                    payload.firstTimer,
                    payload.attendanceMode,
                    payload.location.strip(),
                    payload.referral,
                    payload.invitedBy,
                    payload.prayerRequest,
                    datetime.utcnow(),
                ))
                conn.commit()
        except Exception as e:
            conn.rollback()
            raise HTTPException(status_code=500, detail=f"Database insertion failed: {e}")
        finally:
            conn.close()
    else:
        _memory_registrations[reg_id] = {
            "id": reg_id,
            "title": payload.title,
            "full_name": payload.fullName.strip(),
            "phone": payload.phone.strip(),
            "email": payload.email.strip() if payload.email else "",
            "age": payload.age,
            "member_status": payload.memberStatus,
            "first_timer": payload.firstTimer,
            "attendance_mode": payload.attendanceMode,
            "location": payload.location.strip(),
            "referral": payload.referral,
            "invited_by": payload.invitedBy,
            "prayer_request": payload.prayerRequest,
            "registered_at": now_iso,
        }

    # Trigger Automated Arkesel Confirmation SMS (1 credit)
    if payload.phone:
        sms_text = f"Dear {display_name}, thank you for registering for Roar Ladies Conf 2026! Join our WhatsApp group: https://chat.whatsapp.com/LBl5RWnbfmtEzpv0KahMbO"
        send_arkesel_sms([payload.phone], sms_text)

    return {
        "id": reg_id,
        "regId": reg_id,
        "title": payload.title,
        "fullName": payload.fullName.strip(),
        "displayName": display_name,
        "phone": payload.phone.strip(),
        "email": payload.email.strip() if payload.email else "",
        "age": payload.age,
        "memberStatus": payload.memberStatus,
        "firstTimer": payload.firstTimer,
        "attendanceMode": payload.attendanceMode,
        "location": payload.location.strip(),
        "referral": payload.referral,
        "invitedBy": payload.invitedBy,
        "prayerRequest": payload.prayerRequest,
        "registeredAt": now_iso,
        "checkedIn": False,
    }


# ── Registrations List ────────────────────────────────────────────────────────
@app.get("/api/registrations")
def list_registrations():
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT 
                        r.id,
                        r.title,
                        r.full_name AS "fullName",
                        r.phone,
                        r.email,
                        r.age,
                        r.member_status AS "memberStatus",
                        r.first_timer AS "firstTimer",
                        r.attendance_mode AS "attendanceMode",
                        r.location,
                        r.referral,
                        r.invited_by AS "invitedBy",
                        r.prayer_request AS "prayerRequest",
                        r.registered_at AS "registeredAt",
                        CASE WHEN a.registration_id IS NOT NULL THEN true ELSE false END AS "checkedIn",
                        a.checked_in_at AS "checkedInAt"
                    FROM registrations r
                    LEFT JOIN attendance a ON r.id = a.registration_id
                    ORDER BY r.registered_at DESC
                """)
                rows = cur.fetchall()
                result = []
                for row in rows:
                    title = row.get("title") or ""
                    fname = row.get("fullName") or ""
                    disp = format_display_name(title, fname)
                    row["displayName"] = disp
                    if row.get("registeredAt"):
                        row["registeredAt"] = row["registeredAt"].isoformat()
                    if row.get("checkedInAt"):
                        row["checkedInAt"] = row["checkedInAt"].isoformat()
                    result.append(row)
                return result
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Query failed: {e}")
        finally:
            conn.close()
    else:
        res = []
        for reg_id, reg in reversed(list(_memory_registrations.items())):
            checked = reg_id in _memory_attendance
            checked_at = _memory_attendance.get(reg_id, {}).get("checked_in_at")
            title = reg.get("title", "")
            fname = reg.get("full_name", "")
            res.append({
                "id": reg_id,
                "title": title,
                "fullName": fname,
                "displayName": format_display_name(title, fname),
                "phone": reg.get("phone", ""),
                "email": reg.get("email", ""),
                "age": reg.get("age", ""),
                "memberStatus": reg.get("member_status", ""),
                "firstTimer": reg.get("first_timer", ""),
                "attendanceMode": reg.get("attendance_mode", ""),
                "location": reg.get("location", ""),
                "referral": reg.get("referral", ""),
                "invitedBy": reg.get("invited_by", ""),
                "prayerRequest": reg.get("prayer_request", ""),
                "registeredAt": reg.get("registered_at", ""),
                "checkedIn": checked,
                "checkedInAt": checked_at,
            })
        return res


# ── Attendance Check-In / Uncheck ─────────────────────────────────────────────
@app.post("/api/attendance/{reg_id}")
def mark_attendee_present(reg_id: str):
    now_iso = datetime.utcnow().isoformat()
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM registrations WHERE id = %s", (reg_id,))
                if not cur.fetchone():
                    raise HTTPException(status_code=404, detail="Attendee registration not found")

                cur.execute("""
                    INSERT INTO attendance (registration_id, checked_in_at)
                    VALUES (%s, CURRENT_TIMESTAMP)
                    ON CONFLICT (registration_id) DO UPDATE
                    SET checked_in_at = CURRENT_TIMESTAMP
                """, (reg_id,))
                conn.commit()
                return {"success": True, "regId": reg_id, "checkedIn": True, "checkedInAt": now_iso}
        except HTTPException:
            raise
        except Exception as e:
            conn.rollback()
            raise HTTPException(status_code=500, detail=f"Check-in failed: {e}")
        finally:
            conn.close()
    else:
        _memory_attendance[reg_id] = {"checked_in_at": now_iso}
        return {"success": True, "regId": reg_id, "checkedIn": True, "checkedInAt": now_iso}


@app.delete("/api/attendance/{reg_id}")
def unmark_attendee_present(reg_id: str):
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM attendance WHERE registration_id = %s", (reg_id,))
                conn.commit()
                return {"success": True, "regId": reg_id, "checkedIn": False}
        except Exception as e:
            conn.rollback()
            raise HTTPException(status_code=500, detail=f"Unmark failed: {e}")
        finally:
            conn.close()
    else:
        _memory_attendance.pop(reg_id, None)
        return {"success": True, "regId": reg_id, "checkedIn": False}


# ── Statistics ────────────────────────────────────────────────────────────────
@app.get("/api/stats")
def conference_stats():
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM registrations")
                total = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM attendance")
                checked_in = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM registrations WHERE LOWER(attendance_mode) LIKE '%person%'")
                in_person = cur.fetchone()[0]
                virtual = total - in_person
                return {
                    "total": total,
                    "checkedIn": checked_in,
                    "inPerson": in_person,
                    "virtual": virtual,
                }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Stats query failed: {e}")
        finally:
            conn.close()
    else:
        total = len(_memory_registrations)
        checked_in = len(_memory_attendance)
        in_person = sum(1 for r in _memory_registrations.values() if "person" in r.get("attendance_mode", "").lower())
        virtual = total - in_person
        return {
            "total": total,
            "checkedIn": checked_in,
            "inPerson": in_person,
            "virtual": virtual,
        }


# ── Arkesel SMS Endpoints ─────────────────────────────────────────────────────
@app.post("/api/sms/send")
def send_single_sms(payload: SingleSMSRequest):
    """Sends a single custom SMS via Arkesel."""
    if not payload.recipient or not payload.message:
        raise HTTPException(status_code=400, detail="Recipient phone and message are required")

    result = send_arkesel_sms([payload.recipient], payload.message)
    return {"success": True, "result": result}


@app.post("/api/sms/broadcast")
def broadcast_sms(payload: BroadcastSMSRequest):
    """
    Broadcasts reminder or announcement SMS via Arkesel to registered attendees.
    Target options: 'all' | 'pending' | 'checked_in'
    """
    if not payload.message.strip():
        raise HTTPException(status_code=400, detail="Message content cannot be empty")

    recipients: List[str] = []
    regs = list_registrations()

    for r in regs:
        phone = r.get("phone")
        if not phone:
            continue
        is_checked = r.get("checkedIn", False)

        if payload.target == "all":
            recipients.append(phone)
        elif payload.target == "pending" and not is_checked:
            recipients.append(phone)
        elif payload.target == "checked_in" and is_checked:
            recipients.append(phone)

    if not recipients:
        return {
            "success": False,
            "message": f"No attendees found matching filter target: '{payload.target}'",
            "recipientsCount": 0,
        }

    sms_res = send_arkesel_sms(recipients, payload.message)
    return {
        "success": True,
        "target": payload.target,
        "recipientsCount": len(recipients),
        "arkeselResponse": sms_res,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
