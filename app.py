from flask import Flask, request, render_template
import sqlite3
from datetime import datetime

app = Flask(__name__)

# ... your other routes ...

@app.route('/validate_coupon', methods=['GET', 'POST'])
def validate_coupon():
    message = None
    if request.method == 'POST':
        code = request.form['code']
        with sqlite3.connect('coupons.db') as conn:
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

# if __name__ == '__main__':
#     app.run(debug=True)
