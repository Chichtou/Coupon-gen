import os
import uuid
import sqlite3
import random
import string
import csv
import io
from datetime import datetime, timedelta

from flask import Flask, request, render_template
import qrcode

app = Flask(__name__)

# Adjust these to your environment
DATABASE = 'coupons.db'
DEFAULT_DOMAIN = 'elpatrontaqueriabar.ca'
USERNAME = 'Luxtech'  # Your PythonAnywhere username
STATIC_QR_FOLDER = "/home/Luxtech/Coupon-gen/qr_images"  # Where QR images are saved locally
STATIC_QR_URL = f"https://{USERNAME}.pythonanywhere.com/qr_images"  # Public URL prefix

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

def update_db():
    """
    If you already have a 'coupons' table without 'client' or 'redeemed_at',
    run this once to add them, then comment it out.
    """
    with sqlite3.connect(DATABASE) as conn:
        c = conn.cursor()
        # Add 'client' and 'redeemed_at' if they don't exist
        try:
            c.execute("ALTER TABLE coupons ADD COLUMN client TEXT DEFAULT ''")
        except:
            pass
        try:
            c.execute("ALTER TABLE coupons ADD COLUMN redeemed_at TIMESTAMP")
        except:
            pass
        conn.commit()

def generate_coupon_code():
    """Generates a short coupon code starting with 'VIP' followed by 4 random alphanumeric characters."""
    return "VIP" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))

def generate_qr_file(code):
    """
    Generates a QR code PNG file in the local folder (qr_images/).
    Returns the filename so we can reference it in a public URL.
    """
    # Create a QR code
    qr = qrcode.QRCode(version=1, box_size=6, border=2)
    qr.add_data(code)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    # Ensure the local folder exists
    os.makedirs(STATIC_QR_FOLDER, exist_ok=True)

    # Create a unique filename, e.g., "VIPABCD-<uuid>.png"
    filename = f"{code}-{uuid.uuid4().hex}.png"
    filepath = os.path.join(STATIC_QR_FOLDER, filename)

    # Save the PNG
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
      - Enter a number (count) to generate that many coupons with no email
      - Upload a CSV file of emails
      - Specify a client/session name
    Returns a page displaying the generated coupons and a downloadable CSV
    referencing a public QR URL (hosted automatically on PythonAnywhere).
    """
    coupons = []
    csv_output = ""
    if request.method == 'POST':
        file = request.files.get('file')
        count_str = request.form.get('count', '').strip()
        client_name = request.form.get('client', '').strip()  # new client/session field
        now = datetime.now()
        expires_at = now + timedelta(days=30)

        if file and file.filename != '':
            # Case 1: CSV file of emails
            try:
                stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
            except Exception as e:
                return f"Error reading file: {str(e)}", 400

            reader = csv.reader(stream)
            emails = []
            first_row = next(reader, None)
            # If first row might be a header with "email"
            if first_row and any("email" in cell.lower() for cell in first_row):
                pass
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
                        "INSERT INTO coupons (email, code, created_at, expires_at, domain, client) VALUES (?, ?, ?, ?, ?, ?)",
                        (email, code, now, expires_at, DEFAULT_DOMAIN, client_name)
                    )
                    filename = generate_qr_file(code)
                    qr_url = f"{STATIC_QR_URL}/{filename}"  # public URL
                    coupons.append({
                        'email': email,
                        'code': code,
                        'qr_url': qr_url,
                        'created_at': now.strftime('%Y-%m-%d %H:%M:%S'),
                        'expires_at': expires_at.strftime('%Y-%m-%d %H:%M:%S'),
                        'redeemed': 0,
                        'client': client_name
                    })
                conn.commit()

        elif count_str:
            # Case 2: Numeric count
            try:
                count = int(count_str)
            except ValueError:
                return "Invalid number", 400

            with sqlite3.connect(DATABASE) as conn:
                c = conn.cursor()
                for _ in range(count):
                    code = generate_coupon_code()
                    c.execute(
                        "INSERT INTO coupons (email, code, created_at, expires_at, domain, client) VALUES (?, ?, ?, ?, ?, ?)",
                        (None, code, now, expires_at, DEFAULT_DOMAIN, client_name)
                    )
                    filename = generate_qr_file(code)
                    qr_url = f"{STATIC_QR_URL}/{filename}"
                    coupons.append({
                        'email': '',
                        'code': code,
                        'qr_url': qr_url,
                        'created_at': now.strftime('%Y-%m-%d %H:%M:%S'),
                        'expires_at': expires_at.strftime('%Y-%m-%d %H:%M:%S'),
                        'redeemed': 0,
                        'client': client_name
                    })
                conn.commit()
        else:
            return "Please provide a CSV file or a number of coupons to generate.", 400

        # Build CSV
        output = io.StringIO()
        fieldnames = ['email', 'code', 'qr_url', 'created_at', 'expires_at', 'redeemed', 'client']
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for coupon in coupons:
            writer.writerow({
                'email': coupon['email'],
                'code': coupon['code'],
                'qr_url': coupon['qr_url'],
                'created_at': coupon['created_at'],
                'expires_at': coupon['expires_at'],
                'redeemed': coupon['redeemed'],
                'client': coupon['client']
            })
        csv_output = output.getvalue()
        output.close()

        return render_template("generate_coupons.html", coupons=coupons, csv_data=csv_output)

    # If GET request
    return render_template("generate_coupons.html", coupons=None)

@app.route('/validate_coupon', methods=['GET', 'POST'])
def validate_coupon():
    """
    Validates a coupon code. Sets redeemed_at on success.
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
                    c.execute(
                        "UPDATE coupons SET redeemed=1, redeemed_at=? WHERE code=?",
                        (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), code)
                    )
                    conn.commit()
            else:
                message = "Coupon code not found."
    return render_template("validate_coupon.html", message=message)

@app.route('/history')
def history():
    """
    Shows a list of coupons with redemption status. Optional filter by client.
    """
    client_name = request.args.get('client', '')
    with sqlite3.connect(DATABASE) as conn:
        c = conn.cursor()
        if client_name:
            c.execute("SELECT code, email, redeemed, redeemed_at, client FROM coupons WHERE client=?", (client_name,))
        else:
            c.execute("SELECT code, email, redeemed, redeemed_at, client FROM coupons")
        rows = c.fetchall()

    coupons = []
    for code, email, redeemed, redeemed_at, client in rows:
        coupons.append({
            'code': code,
            'email': email,
            'redeemed': redeemed,
            'redeemed_at': redeemed_at,
            'client': client
        })
    return render_template("history.html", coupons=coupons)

if __name__ == '__main__':
    init_db()
    # update_db()  # Uncomment and run once if you need to add 'client' & 'redeemed_at' to an existing DB
    app.run(debug=True)
