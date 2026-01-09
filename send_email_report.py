
import os
import smtplib
import glob
import configparser
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import pandas as pd
from jinja2 import Environment, FileSystemLoader

# --- Load Configuration ---
config = configparser.ConfigParser()
config.read('config.ini')

def send_email_report():
    """
    Finds the latest CSV report, generates an HTML report from it,
    and sends it as an email.
    """
    # --- Configuration ---
    # SMTP server details are expected to be in environment variables
    SMTP_HOST = os.getenv('SMTP_HOST')
    SMTP_PORT = int(os.getenv('SMTP_PORT', 587))
    SMTP_USER = os.getenv('SMTP_USER')
    SMTP_PASSWORD = os.getenv('SMTP_PASSWORD')
    
    # Email details
    SENDER_EMAIL = os.getenv('SENDER_EMAIL', SMTP_USER)
    RECIPIENT_EMAIL = os.getenv('RECIPIENT_EMAIL')

    if not all([SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, RECIPIENT_EMAIL]):
        print("Error: Missing one or more required environment variables for sending email.")
        print("Required: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, RECIPIENT_EMAIL")
        return

    # --- Find the latest report ---
    try:
        reports_dir = config['Paths']['reports_dir']
        list_of_files = glob.glob(f'{reports_dir}/*.csv')
        if not list_of_files:
            print(f"No CSV reports found in the '{reports_dir}' directory.")
            return
        latest_file = max(list_of_files, key=os.path.getctime)
        print(f"Found latest report: {latest_file}")
    except Exception as e:
        print(f"Error finding latest report: {e}")
        return

    # --- Generate HTML from the report ---
    try:
        df = pd.read_csv(latest_file)
        env = Environment(loader=FileSystemLoader('.'))
        template = env.get_template('email_template.html')
        html_output = template.render(
            report_title=f"PageSpeed Report - {os.path.basename(latest_file)}",
            data_frame=df
        )
        print("Successfully generated HTML from template.")
    except Exception as e:
        print(f"Error generating HTML report: {e}")
        return

    # --- Send the email ---
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"PageSpeed Performance Report: {os.path.basename(latest_file)}"
        msg['From'] = SENDER_EMAIL
        msg['To'] = RECIPIENT_EMAIL

        part1 = MIMEText(df.to_string(), 'plain')
        part2 = MIMEText(html_output, 'html')

        msg.attach(part1)
        msg.attach(part2)

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SENDER_EMAIL, RECIPIENT_EMAIL, msg.as_string())
        print(f"Email sent successfully to {RECIPIENT_EMAIL}")

    except Exception as e:
        print(f"Failed to send email: {e}")

if __name__ == '__main__':
    send_email_report()
