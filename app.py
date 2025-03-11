import os
import uuid
import sqlite3
import random
import string
import csv
import io
from datetime import datetime, timedelta

from flask import Flask, request, render_template, redirect, url_for
import qrcode

app = Flask(__name__)

DATABASE = 'coupons.db'
DEFAULT_DOMAIN = 'elpatrontaqueriabar.ca'

# This is your local folder for QR images
STATIC_QR_FOLDER = '/home/Luxtech/Coupon-gen/qr-images'
# This is the exact link you see in the PythonAnywhere file manager
# (not publicly accessible, but stored in CSV).
FILE_MANAGER_URL = "https://www.pythonanywhere.com/user/Luxtech/files/home/Luxtech/Coupon-gen/qr-images"

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
                domain TEXT,
                client TEXT,
                redeemed_at TIMESTAMP
            )
        ''')
        conn.commit()

def generate_coupon_code():
    """Generates a short coupon code like VIPAB12."""
    return "VIP" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))

def generate_qr_file(code):
    """
    Generates a QR code PNG file in STATIC_QR_FOLDER.
    Returns the filename.
    """
    qr = qrcode.QRCode(version=1, box_size=6, border=2)
    qr.add_data(code)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    os.makedirs(STATIC_QR_FOLDER, exist_ok=True)
    filename = f"{code}-{uuid.uuid4().hex}.png"
    filepath = os.path.join(STATIC_QR_FOLDER, filename)
    img.save(filepath)
    return filename

@app.route('/')
def index():
    """Home page."""
    return render_template("index.html")

@app.route('/generate_coupons', methods=['GET', 'POST'])
def generate_coupons():
    """
    Allows the user to:
      - Enter a number to generate that many coupons (no email)
      - Or upload a CSV of emails
      - Optionally specify a client name
    Displays the generated coupons & provides a downloadable CSV.
    If neither is provided, we show an error on the same page.
    """
    coupons = []
    csv_output = ""
    error_message = None

    if request.method == 'POST':
        file = request.files.get('file')
        count_str = request.form.get('count', '').strip()
        client_name = request.form.get('client', '').strip()
        now = datetime.now()
        expires_at = now + timedelta(days=30)

        # If user provided neither file nor count, show error on same page
        if (not file or file.filename == '') and (not count_str):
            error_message = "Please provide a CSV file or a number of coupons to generate."
            return render_template("generate_coupons.html", coupons=None, error_message=error_message)

        if file and file.filename != '':
            # CSV file
            try:
                stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
            except Exception as e:
                error_message = f"Error reading file: {str(e)}"
                return render_template("generate_coupons.html", coupons=None, error_message=error_message)

            reader = csv.reader(stream)
            emails = []
            first_row = next(reader, None)
            if first_row and any("email" in cell.lower() for cell in first_row):
                pass
            else:
                if first_row:
                    emails.append(first_row[0])

            for row in reader:
                if row:
                    emails.append(row[0])

            if not emails:
                error_message = "No emails found in the file."
                return render_template("generate_coupons.html", coupons=None, error_message=error_message)

            with sqlite3.connect(DATABASE) as conn:
                c = conn.cursor()
                for email in emails:
                    code = generate_coupon_code()
                    c.execute(
                        "INSERT INTO coupons (email, code, created_at, expires_at, domain, client) VALUES (?, ?, ?, ?, ?, ?)",
                        (email, code, now, expires_at, DEFAULT_DOMAIN, client_name)
                    )
                    filename = generate_qr_file(code)
                    # Build the PythonAnywhere file manager link
                    # (not publicly accessible, but stored in CSV)
                    file_link = f"{FILE_MANAGER_URL}/{filename}"
                    coupons.append({
                        'email': email,
                        'code': code,
                        'qr_file': filename,
                        'qr_link': file_link,
                        'created_at': now.strftime('%Y-%m-%d %H:%M:%S'),
                        'expires_at': expires_at.strftime('%Y-%m-%d %H:%M:%S'),
                        'redeemed': 0,
                        'client': client_name
                    })
                conn.commit()

        elif count_str:
            # Numeric count
            try:
                count = int(count_str)
            except ValueError:
                error_message = "Invalid number"
                return render_template("generate_coupons.html", coupons=None, error_message=error_message)

            with sqlite3.connect(DATABASE) as conn:
                c = conn.cursor()
                for _ in range(count):
                    code = generate_coupon_code()
                    c.execute(
                        "INSERT INTO coupons (email, code, created_at, expires_at, domain, client) VALUES (?, ?, ?, ?, ?, ?)",
                        (None, code, now, expires_at, DEFAULT_DOMAIN, client_name)
                    )
                    filename = generate_qr_file(code)
                    file_link = f"{FILE_MANAGER_URL}/{filename}"
                    coupons.append({
                        'email': '',
                        'code': code,
                        'qr_file': filename,
                        'qr_link': file_link,
                        'created_at': now.strftime('%Y-%m-%d %H:%M:%S'),
                        'expires_at': expires_at.strftime('%Y-%m-%d %H:%M:%S'),
                        'redeemed': 0,
                        'client': client_name
                    })
                conn.commit()

        # Build CSV
        output = io.StringIO()
        fieldnames = ['email', 'code', 'qr_file', 'qr_link', 'created_at', 'expires_at', 'redeemed', 'client']
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for coupon in coupons:
            writer.writerow({
                'email': coupon['email'],
                'code': coupon['code'],
                'qr_file': coupon['qr_file'],
                'qr_link': coupon['qr_link'],
                'created_at': coupon['created_at'],
                'expires_at': coupon['expires_at'],
                'redeemed': coupon['redeemed'],
                'client': coupon['client']
            })
        csv_output = output.getvalue()
        output.close()

        return render_template("generate_coupons.html", coupons=coupons, csv_data=csv_output, error_message=None)

    # GET request
    return render_template("generate_coupons.html", coupons=None, error_message=None)

@app.route('/validate_coupon', methods=['GET', 'POST'])
def validate_coupon():
    """
    Validates a coupon code, sets redeemed=1 if valid.
    Also includes a Scan button to use phone camera with html5-qrcode.
    """
    message = None
    if request.method == 'POST':
        code = request.form['code']
        with sqlite3.connect(DATABASE) as conn:
            c = conn.cursor()
            c.execute("SELECT expires_at, redeemed FROM coupons WHERE code=?", (code,))
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
                    c.execute("UPDATE coupons SET redeemed=1 WHERE code=?", (code,))
                    conn.commit()
            else:
                message = "Coupon code not found."
    return render_template("validate_coupon.html", message=message)

@app.route('/history')
def history():
    """
    Shows a list of coupons with redemption status. 
    Optional filter by client: /history?client=XYZ
    """
    client_name = request.args.get('client', '')
    with sqlite3.connect(DATABASE) as conn:
        c = conn.cursor()
        if client_name:
            c.execute("SELECT code, email, redeemed, domain, client FROM coupons WHERE client=?", (client_name,))
        else:
            c.execute("SELECT code, email, redeemed, domain, client FROM coupons")
        rows = c.fetchall()

    coupons = []
    for code, email, redeemed, domain, client in rows:
        coupons.append({
            'code': code,
            'email': email,
            'redeemed': redeemed,
            'domain': domain,
            'client': client
        })
    return render_template("history.html", coupons=coupons)

@app.route('/delete_coupon', methods=['POST'])
def delete_coupon():
    """Deletes a coupon by its code, then redirects back to history page."""
    code = request.form.get('code', '')
    with sqlite3.connect(DATABASE) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM coupons WHERE code=?", (code,))
        conn.commit()
    return redirect(url_for('history'))

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
