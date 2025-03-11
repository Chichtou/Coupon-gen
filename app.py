import sqlite3
import random
import string
import csv
import io
import base64
from datetime import datetime, timedelta

from flask import Flask, request, render_template, Response, url_for

# If you plan to generate QR codes for coupons, install qrcode and Pillow:
# pip install qrcode[pil]
import qrcode

app = Flask(__name__)

DATABASE = 'coupons.db'
DEFAULT_DOMAIN = 'elpatrontaqueriabar.ca'

def init_db():
    """Create the coupons table if it doesn't already exist."""
    with sqlite3.connect(DATABASE) as conn:
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS coupons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT,
                code TEXT UNIQUE,
                created_at TIMESTAMP,
                expires_at TIMESTAMP,
                redeemed INTEGER DEFAULT 0,
                domain TEXT
            )
        ''')
        conn.commit()

def generate_coupon_code():
    """Generates a short coupon code starting with 'VIP' followed by 4 random alphanumeric characters."""
    return "VIP" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))

def generate_qr_base64(text):
    """
    Generates a QR code image for the given text and returns it as a base64 data URL.
    Remove if you don't need QR code generation.
    """
    qr = qrcode.QRCode(version=1, box_size=6, border=2)
    qr.add_data(text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{img_str}"

@app.route('/')
def index():
    """Home page."""
    return render_template("index.html")

@app.route('/generate_coupons', methods=['GET', 'POST'])
def generate_coupons():
    """
    Allows the user to:
      - Enter a number (count) to generate that many coupons with no email
      - Upload a CSV file of emails to generate one coupon per email
    Returns a page displaying the generated coupons (optionally with QR codes)
    and provides a downloadable CSV.
    """
    coupons = []
    csv_output = ""
    if request.method == 'POST':
        file = request.files.get('file')
        count_str = request.form.get('count', '').strip()
        now = datetime.now()
        expires_at = now + timedelta(days=30)

        # Case 1: CSV file of emails
        if file and file.filename != '':
            try:
                stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
            except Exception as e:
                return f"Error reading file: {str(e)}", 400

            reader = csv.reader(stream)
            emails = []
            first_row = next(reader, None)
            # If the first row might be a header containing "email"
            if first_row and any("email" in cell.lower() for cell in first_row):
                pass  # skip it
            else:
                if first_row:
                    emails.append(first_row[0])

            for row in reader:
                if row:
                    emails.append(row[0])

            if not emails:
                return "No emails found in the file.", 400

            with sqlite3.connect(DATABASE) as conn:
                c = conn.cursor()
                for email in emails:
                    code = generate_coupon_code()
                    c.execute(
                        "INSERT INTO coupons (email, code, created_at, expires_at, domain) VALUES (?, ?, ?, ?, ?)",
                        (email, code, now, expires_at, DEFAULT_DOMAIN)
                    )
                    qr_img = generate_qr_base64(code)  # Remove if you don't need QR codes
                    coupons.append({
                        'email': email,
                        'code': code,
                        'qr': qr_img,
                        'created_at': now.strftime('%Y-%m-%d %H:%M:%S'),
                        'expires_at': expires_at.strftime('%Y-%m-%d %H:%M:%S'),
                        'redeemed': 0
                    })
                conn.commit()

        # Case 2: Numeric count
        elif count_str:
            try:
                count = int(count_str)
            except ValueError:
                return "Invalid number", 400

            with sqlite3.connect(DATABASE) as conn:
                c = conn.cursor()
                for _ in range(count):
                    code = generate_coupon_code()
                    c.execute(
                        "INSERT INTO coupons (email, code, created_at, expires_at, domain) VALUES (?, ?, ?, ?, ?)",
                        (None, code, now, expires_at, DEFAULT_DOMAIN)
                    )
                    qr_img = generate_qr_base64(code)  # Remove if you don't need QR codes
                    coupons.append({
                        'email': '',
                        'code': code,
                        'qr': qr_img,
                        'created_at': now.strftime('%Y-%m-%d %H:%M:%S'),
                        'expires_at': expires_at.strftime('%Y-%m-%d %H:%M:%S'),
                        'redeemed': 0
                    })
                conn.commit()
        else:
            return "Please provide a CSV file or a number of coupons to generate.", 400

        # Build a CSV output from the generated coupons
        output = io.StringIO()
        fieldnames = ['email', 'code', 'created_at', 'expires_at', 'redeemed']
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for coupon in coupons:
            writer.writerow({
                'email': coupon['email'],
                'code': coupon['code'],
                'created_at': coupon['created_at'],
                'expires_at': coupon['expires_at'],
                'redeemed': coupon['redeemed']
            })
        csv_output = output.getvalue()
        output.close()

        return render_template("generate_coupons.html", coupons=coupons, csv_data=csv_output)

    # If GET request, just render the page without coupons
    return render_template("generate_coupons.html", coupons=None)

@app.route('/validate_coupon', methods=['GET', 'POST'])
def validate_coupon():
    """
    Validates a coupon code. 
    Shows a green background if valid, red if already redeemed/expired/not found.
    """
    message = None
    if request.method == 'POST':
        code = request.form['code']
        with sqlite3.connect(DATABASE) as conn:
            c = conn.cursor()
            c.execute("SELECT expires_at, redeemed FROM coupons WHERE code = ?", (code,))
            result = c.fetchone()
            if result:
                expires_at_str, redeemed = result
                expires_at = datetime.strptime(expires_at_str, '%Y-%m-%d %H:%M:%S.%f')
                if redeemed:
                    message = "This coupon has already been redeemed."
                elif expires_at < datetime.now():
                    message = "This coupon has expired."
                else:
                    message = "This coupon is valid and now redeemed!"
                    c.execute("UPDATE coupons SET redeemed = 1 WHERE code = ?", (code,))
                    conn.commit()
            else:
                message = "Coupon code not found."
    return render_template("validate_coupon.html", message=message)

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
