from datetime import datetime
import vivamk_daily_monitor as m

settings = m.load_settings()
m.send_email(
    settings,
    "[VivaMK] Daily monitor email test",
    "This is a test email from the VivaMK daily catalogue monitor.\n\n"
    f"Sent: {datetime.now():%A %d %B %Y at %H:%M}\n\n"
    "If you received this, the heartbeat email configuration is working."
)
print("Test email sent successfully.")
