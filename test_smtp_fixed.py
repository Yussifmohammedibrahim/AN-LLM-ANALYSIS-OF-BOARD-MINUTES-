import smtplib
from email.mime.text import MIMEText
import os
from dotenv import load_dotenv

load_dotenv(dotenv_path='itds_env/.env')

def test_smtp():
    SMTP_SERVER = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
    SMTP_PORT = int(os.getenv('SMTP_PORT', 587))
    SMTP_USERNAME = os.getenv('SMTP_USERNAME')
    SMTP_PASSWORD = os.getenv('SMTP_PASSWORD')
    FROM_EMAIL = os.getenv('FROM_EMAIL', SMTP_USERNAME)
    
    if not SMTP_USERNAME or not SMTP_PASSWORD:
        print("❌ ERROR: SMTP_USERNAME or SMTP_PASSWORD missing in itds_env/.env")
        print("Create itds_env/.env with your Gmail App Password")
        print("Example:")
        print("SMTP_SERVER=smtp.gmail.com")
        print("SMTP_PORT=587")
        print("SMTP_USERNAME=your@gmail.com")
        print("SMTP_PASSWORD=your16char_app_password")
        return False
    
    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        print("✅ SMTP Connection SUCCESS!")
        print(f"User: {SMTP_USERNAME}")
        server.quit()
        return True
    except Exception as e:
        print(f"❌ SMTP ERROR: {e}")
        print("1. Enable 2FA on Gmail")
        print("2. Generate App Password: https://myaccount.google.com/apppasswords")
        print("3. Update itds_env/.env")
        return False

if __name__ == '__main__':
    test_smtp()

