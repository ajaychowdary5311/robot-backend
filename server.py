from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import smtplib
import random
import string
import serial
import time
import threading

app = Flask(__name__)
CORS(app)

# Serial Configuration
SERIAL_PORT = "COM3"  # Change based on your system
BAUD_RATE = 9600
arduino = None
# Initialize Serial Connection
def connect_arduino():
    global arduino
    try:
        arduino = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        time.sleep(2)  # Wait for Arduino to initialize
        print("✅ Arduino connected successfully")
    except Exception as e:
        print(f"❌ Error connecting to Arduino: {e}")
        arduino = None

connect_arduino()

# Database initialization
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

# Generate OTP
def generate_otp():
    return ''.join(random.choices(string.digits, k=6))

# Email sender
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

# Listen to Arduino messages
def listen_to_arduino():
    global arduino
    while arduino and arduino.is_open:
        try:
            line = arduino.readline().decode().strip()
            if line:
                print("📥 Arduino:", line)
                if "ARRIVED" in line:
                    # Notify the user when robot arrives
                    conn = sqlite3.connect("robot_data.db")
                    cursor = conn.cursor()
                    cursor.execute("SELECT customer_email FROM parcels LIMIT 1")
                    result = cursor.fetchone()
                    conn.close()
                    if result:
                        customer_email = result[0]
                        send_email(customer_email, "Robot Has Arrived!",
                                   "Your parcel is at your location. Please unlock using your OTP.")
        except serial.SerialException as e:
            print("🔌 Serial connection lost:", e)
            break
        except Exception as e:
            print("⚠️ Unexpected error:", e)

# Start listening thread
if arduino:
    threading.Thread(target=listen_to_arduino, daemon=True).start()

# 📦 Send parcel
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
        if arduino:
            arduino.write(b"GO\n")
            print("📤 Sent 'GO' command to Arduino")
        return jsonify({"message": "OTP sent successfully"}), 200
    else:
        return jsonify({"error": "Failed to send OTP"}), 500

# 🔓 Unlock robot
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

        if arduino:
            arduino.write(b"UNLOCK\n")
            print("🔓 Sent 'UNLOCK' to Arduino")
        return jsonify({"message": "Robot unlocked successfully"}), 200
    else:
        conn.close()
        return jsonify({"error": "Invalid OTP"}), 400

if __name__ == '__main__':
  app.run(host='0.0.0.0', port=port)
