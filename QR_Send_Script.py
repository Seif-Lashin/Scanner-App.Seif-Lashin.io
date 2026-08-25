# %%
!pip install dotenv pandas

# %%
import os
import time
import smtplib
import pandas as pd
from pathlib import Path
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from dotenv import load_dotenv

load_dotenv()

# --- MULTI-ACCOUNT CONFIGURATION ---
# Gmail limit is 500 emails/day per free account (use ~450 to stay safe).
# Add as many accounts as needed.
ACCOUNTS = [
    {
        "email": os.getenv('SENDER_EMAIL_1', 'account1@gmail.com'),
        "password": os.getenv('SMTP_PASSWORD_1', 'app_pass_1'),
        "sender_name": "Event Team",
        "smtp_server": "smtp.gmail.com",
        "smtp_port": 587,
        "daily_limit": 450
    },
    # Add more account dicts here as needed
]

SHEET_FILENAME = "guests_data.csv"
QR_FOLDER = "QR code data"
DELAY_BETWEEN_EMAILS = 1.0

EMAIL_SUBJECT = "Your Official Ticket & QR Code for the Event"
EMAIL_TEMPLATE_HTML = """
<!DOCTYPE html>
<html>
<body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6; margin: 0; padding: 0;">
    <div style="max-width: 600px; margin: 20px auto; padding: 20px; border: 1px solid #e0e0e0; border-radius: 10px; background-color: #ffffff;">
        <h2 style="color: #007aff; margin-top: 0;">Hello {name},</h2>
        <p>We are excited to welcome you to the upcoming event!</p>
        <p>Your registration is confirmed. Please keep this email safe and present the QR code below at the gate for entry verification.</p>
        
        <div style="text-align: center; margin: 30px 0; padding: 15px; background: #f9f9f9; border-radius: 8px;">
            <img src="cid:qrcode_img" alt="Your QR Code" style="width: 220px; height: 220px; border: 2px solid #ddd; padding: 5px; background: #fff; border-radius: 8px;">
            <p style="font-size: 0.85rem; color: #666; margin-top: 8px; font-family: monospace;">Ticket ID: {uuid}</p>
        </div>
        
        <p>If you have any issues or questions, reply directly to this email.</p>
        <br>
        <p>Best regards,<br><strong>{sender_name}</strong></p>
    </div>
</body>
</html>
"""

# %%
local_file = Path(SHEET_FILENAME)
if not local_file.exists():
    raise FileNotFoundError(f"Cannot find '{SHEET_FILENAME}'.")

df = pd.read_csv(local_file)

if 'email_sent' not in df.columns:
    df['email_sent'] = False

df['email_sent'] = df['email_sent'].fillna(False).astype(bool)

unsent_count = len(df[~df['email_sent']])
sent_count = len(df[df['email_sent']])

print(f"📊 Total Attendees: {len(df)}")
print(f"✅ Emails Already Sent: {sent_count}")
print(f"⏳ Remaining to Send: {unsent_count}")

# %%
def create_smtp_connection(acc):
    """Establishes an active, authenticated SMTP connection safely."""
    port = int(acc['smtp_port'])
    host = acc['smtp_server']
    
    if port == 465:
        server = smtplib.SMTP_SSL(host, port)
    else:
        server = smtplib.SMTP(host, port)
        server.starttls()
        
    server.login(acc['email'], acc['password'])
    return server

def send_qr_email(smtp_conn, sender_acc, recipient_email, recipient_name, uuid_val):
    qr_file_path = Path(QR_FOLDER) / f"{uuid_val}.png"
    
    if not qr_file_path.exists():
        print(f"⚠️ Missing QR code file for {recipient_name} ({uuid_val}). Skipping.")
        return False

    msg = MIMEMultipart('related')
    msg['Subject'] = EMAIL_SUBJECT
    msg['From'] = f"{sender_acc['sender_name']} <{sender_acc['email']}>"
    msg['To'] = recipient_email

    html_content = EMAIL_TEMPLATE_HTML.format(
        name=recipient_name,
        uuid=uuid_val,
        sender_name=sender_acc['sender_name']
    )
    
    msg.attach(MIMEText(html_content, 'html'))

    with open(qr_file_path, 'rb') as f:
        img = MIMEImage(f.read())
        img.add_header('Content-ID', '<qrcode_img>')
        img.add_header('Content-Disposition', 'inline', filename=f"{uuid_val}.png")
        msg.attach(img)

    smtp_conn.send_message(msg)
    return True

# %%
pending_df = df[~df['email_sent']]

if pending_df.empty:
    print("🎉 All emails have been sent! Nothing left to process.")
else:
    account_idx = 0
    current_acc = ACCOUNTS[account_idx]
    emails_sent_by_acc = 0
    server = None

    print(f"🚀 Starting dispatch across {len(ACCOUNTS)} sender accounts...\n")

    try:
        server = create_smtp_connection(current_acc)
        print(f"🔑 Connected using account: {current_acc['email']}")
    except Exception as e:
        print(f"❌ Initial connection failed for {current_acc['email']}: {e}")

    for idx, row in pending_df.iterrows():
        # Rotate account if limit reached for current sender
        if emails_sent_by_acc >= current_acc.get('daily_limit', 450):
            print(f"\n✋ Reached safety limit ({emails_sent_by_acc}) for {current_acc['email']}.")
            if server:
                try: server.quit() 
                except: pass

            account_idx += 1
            if account_idx >= len(ACCOUNTS):
                print("🚨 All accounts have reached their limits! Stopping execution.")
                break

            current_acc = ACCOUNTS[account_idx]
            emails_sent_by_acc = 0
            try:
                server = create_smtp_connection(current_acc)
                print(f"🔄 Switched to account: {current_acc['email']}")
            except Exception as e:
                print(f"❌ Failed connecting to next account {current_acc['email']}: {e}")
                break

        guest_name = str(row['name'])
        guest_email = str(row['email']).strip()
        guest_uuid = str(row['uuid']).strip()

        try:
            success = send_qr_email(server, current_acc, guest_email, guest_name, guest_uuid)
            if success:
                df.at[idx, 'email_sent'] = True
                emails_sent_by_acc += 1
                
                print(f"✅ Sent to {guest_name} <{guest_email}> via {current_acc['email']}")
                df.to_csv(SHEET_FILENAME, index=False)
                
            time.sleep(DELAY_BETWEEN_EMAILS)

        except (smtplib.SMTPDataError, smtplib.SMTPResponseException) as quota_err:
            print(f"⚠️ Quota/Rate limit error on {current_acc['email']}: {quota_err}")
            # Trigger account switch on next iteration
            emails_sent_by_acc = current_acc.get('daily_limit', 450)
            
        except Exception as e:
            print(f"❌ Failed sending to {guest_name} ({guest_email}): {e}")

    if server:
        try: server.quit()
        except: pass

    print(f"\n✨ Batch complete. Progress updated in {SHEET_FILENAME}.")