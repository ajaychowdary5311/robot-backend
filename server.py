from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import smtplib
import random
import string
import time
import threading
import os

# Optional: import serial only if you're using it locally
try:
    import serial
except ImportError:
    serial = None

app = Flask(__name__)
CORS(app)

# ========================================
# 🔌 Serial (Arduino) Setup — disabled for cloud
# ========================================
USE_SERIAL = False  # Set to True only when running locally
SERIAL_PORT = "COM3"
BAUD_RATE = 9600
arduino = None

def connect_arduino():
    global arduino
    if USE_SERIAL and serial:
        try:
            arduino = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
            time.sleep(2)
            print("✅ Arduino connected successfully")
        except Exception as e:
            print(f"❌ Error connecting to Arduino: {e}")
            arduino = None
    else:
        print("⚠️ Serial connection skipped (cloud mode)")

connect_arduino()

def safe_serial_write(command):
    if arduino:
        arduino.write(command.encode())
        print(f"📤 Sent command: {command.strip()}")
    else:
        print(f"⚠️ Skipped sending '{command.strip()}' (no Arduino connected)")

# ========================================
# 📦 Database Setup
# ========================================
def init_db():
    conn = sqlite3.connect("robot_data.db")
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS parcels (
                        customer_email TEXT PRIMARY KEY,
                        otp TEXT NOT NULL,
                        location TEXT
                    )''')
    conn.commit()
    conn.close()

init_db()

# ========================================
# 🔐 OTP Generation
# ========================================
def generate_otp():
    return ''.join(random.choices(string.digits, k=6))

# ========================================
# 📧 Email Sender
# ========================================
def send_email(email, subject, body):
    sender_email = "21r21A6619@mlrinstitutions.ac.in"
    sender_password = "aqpa ytzs wltb gwmp"

    message = f"Subject: {subject}\n\n{body}"

    try:
        server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, email, message)
        server.quit()
        print("📧 Email sent to", email)
        return True
    except Exception as e:
        print("❌ Error sending email:", e)
        return False

# ========================================
# 👂 Arduino Listener Thread
# ========================================
def listen_to_arduino():
    global arduino
    if not arduino:
        return
    while arduino.is_open:
        try:
            line = arduino.readline().decode().strip()
            if line:
                print("📥 Arduino:", line)
                if "ARRIVED" in line:
                    conn = sqlite3.connect("robot_data.db")
                    cursor = conn.cursor()
                    cursor.execute("SELECT customer_email FROM parcels LIMIT 1")
                    result = cursor.fetchone()
                    conn.close()
                    if result:
                        customer_email = result[0]
                        send_email(customer_email, "Robot Has Arrived!",
                                   "Your parcel is at your location. Please unlock using your OTP.")
        except Exception as e:
            print("⚠️ Listener error:", e)
            break

if arduino:
    threading.Thread(target=listen_to_arduino, daemon=True).start()

# ========================================
# 📦 API: Send Parcel
# ========================================
@app.route('/send_parcel', methods=['POST'])
def send_parcel():
    data = request.json
    customer_email = data.get("customer_email")
    location = data.get("location")

    if not customer_email or not location:
        return jsonify({"error": "Email and location are required"}), 400

    otp = generate_otp()

    conn = sqlite3.connect("robot_data.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM parcels WHERE customer_email = ?", (customer_email,))
    cursor.execute("INSERT INTO parcels (customer_email, otp, location) VALUES (?, ?, ?)",
                   (customer_email, otp, location))
    conn.commit()
    conn.close()

    if send_email(customer_email, "Your OTP to Unlock the Robot",
                  f"Your OTP is: {otp}\nUse this to unlock your parcel from the robot."):
        safe_serial_write("GO\n")
        return jsonify({"message": "OTP sent successfully"}), 200
    else:
        return jsonify({"error": "Failed to send OTP"}), 500

# ========================================
# 🔓 API: Unlock Robot
# ========================================
@app.route('/unlock_robot', methods=['POST'])
def unlock_robot():
    data = request.json
    customer_email = data.get("customer_email")
    otp_entered = data.get("otp")

    conn = sqlite3.connect("robot_data.db")
    cursor = conn.cursor()
    cursor.execute("SELECT otp FROM parcels WHERE customer_email = ?", (customer_email,))
    row = cursor.fetchone()
    stored_otp = row[0] if row else None

    if stored_otp == otp_entered:
        cursor.execute("DELETE FROM parcels WHERE customer_email = ?", (customer_email,))
        conn.commit()
        conn.close()
        safe_serial_write("UNLOCK\n")
        return jsonify({"message": "Robot unlocked successfully"}), 200
    else:
        conn.close()
        return jsonify({"error": "Invalid OTP"}), 400

# ========================================
# 🚀 Start Server
# ========================================
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
