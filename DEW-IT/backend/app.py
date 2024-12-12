from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from datetime import datetime
import pymysql
from google.cloud.sql.connector import Connector
from google.oauth2 import service_account
import os

# Ensure GOOGLE_APPLICATION_CREDENTIALS environment variable is set
SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
if not SERVICE_ACCOUNT_FILE:
    raise RuntimeError("GOOGLE_APPLICATION_CREDENTIALS environment variable is not set.")

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# Set up Google Cloud SQL connection
connector = Connector()
DATABASE = {
    "project_id": "capstone-442107",
    "region": "asia-southeast2",
    "instance_id": "dewit",
    "database_name": "dewit",
    "user": "root",
    "password": "root"
}

# Function to connect to the database
def get_connection():
    try:
        connection = connector.connect(
            f"{DATABASE['project_id']}:{DATABASE['region']}:{DATABASE['instance_id']}",
            "pymysql",
            user=DATABASE['user'],
            password=DATABASE['password'],
            db=DATABASE['database_name'],
        )
        return connection
    except Exception as e:
        print(f"Error connecting to database: {e}")
        return None

# Initialize the database
with get_connection() as conn:
    if conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        username VARCHAR(255) NOT NULL,
                        email VARCHAR(255) NOT NULL,
                        phone VARCHAR(15) NOT NULL,
                        password VARCHAR(255) NOT NULL
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS transactions (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        user_id INT NOT NULL,
                        amount DECIMAL(10, 2) NOT NULL,
                        category VARCHAR(255) NOT NULL,
                        date DATE NOT NULL,
                        description TEXT,
                        payment_method VARCHAR(50) NOT NULL,
                        FOREIGN KEY (user_id) REFERENCES users (id)
                    )
                ''')
                conn.commit()
            except Exception as e:
                print(f"Error initializing database: {e}")

@app.route('/')
def index():
    if 'username' in session:
        user_id = session['user_id']
        username = session['username']

        with get_connection() as conn:
            if conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT * FROM transactions WHERE user_id = %s", (user_id,))
                    transactions = cursor.fetchall()

                total_amount = sum(transaction[2] for transaction in transactions)
                total_upi = sum(transaction[2] for transaction in transactions if transaction[6] == 'UPI')
                total_cash = sum(transaction[2] for transaction in transactions if transaction[6] == 'Cash')

        return render_template('index.html', username=username, total_amount=total_amount, total_upi=total_upi, total_cash=total_cash)
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        with get_connection() as conn:
            if conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT id, username FROM users WHERE username = %s AND password = %s", (username, password))
                    user = cursor.fetchone()

        if user:
            session['user_id'] = user[0]
            session['username'] = user[1]
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password. Please try again.', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    session.pop('user_id', None)
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        phone = request.form['phone']
        password = request.form['password']

        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'error')
            return render_template('register.html')

        with get_connection() as conn:
            if conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
                    existing_user = cursor.fetchone()

                    if existing_user:
                        flash('Username already exists. Please choose a different one.', 'error')
                    else:
                        cursor.execute(
                            "INSERT INTO users (username, email, phone, password) VALUES (%s, %s, %s, %s)",
                            (username, email, phone, password)
                        )
                        conn.commit()
                        flash('Registration successful! Please log in.', 'success')
                        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/transactions')
def transactions():
    if 'username' in session:
        user_id = session['user_id']
        username = session['username']

        with get_connection() as conn:
            if conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT * FROM transactions WHERE user_id = %s", (user_id,))
                    transactions = cursor.fetchall()

        return render_template('transaction.html', transactions=transactions, username=username)
    else:
        return redirect(url_for('login'))

@app.route('/add_transaction', methods=['POST'])
def add_transaction():
    if 'username' in session:
        user_id = session['user_id']
        date = request.form['date']
        category = request.form['category']
        amount = request.form['amount']
        payment_method = request.form['payment_method']
        description = request.form['notes']

        if not amount.isdigit() or float(amount) <= 0:
            flash('Amount must be a positive number.', 'error')
            return redirect(url_for('transactions'))

        with get_connection() as conn:
            if conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "INSERT INTO transactions (user_id, date, category, amount, payment_method, description) VALUES (%s, %s, %s, %s, %s, %s)",
                        (user_id, date, category, amount, payment_method, description)
                    )
                conn.commit()

        return redirect(url_for('transactions'))
    else:
        return redirect(url_for('login'))

@app.route('/delete_transaction/<int:transaction_id>', methods=['POST'])
def delete_transaction(transaction_id):
    if 'username' in session:
        with get_connection() as conn:
            if conn:
                with conn.cursor() as cursor:
                    cursor.execute("DELETE FROM transactions WHERE id = %s", (transaction_id,))
                conn.commit()

        flash('Transaction deleted successfully.', 'success')
    else:
        flash('You must be logged in to delete a transaction.', 'error')
    return redirect(url_for('transactions'))


# Daily Spending Data Route
@app.route('/daily_spending_data')
def daily_spending_data():
    if 'username' in session:
        user_id = session['user_id']
        
        # Fetch daily spending data from the database
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT date, SUM(amount) FROM transactions WHERE user_id = %s GROUP BY date", (user_id,))
        data = cursor.fetchall()
        conn.close()

        # Format data for Chart.js
        labels = [row[0] for row in data]
        amounts = [row[1] for row in data]

        return jsonify({'labels': labels, 'amounts': amounts})
    else:
        return redirect(url_for('login'))

# Monthly Spending Data Route
@app.route('/monthly_spending_data')
def monthly_spending_data():
    if 'username' in session:
        user_id = session['user_id']
        
        # Fetch monthly spending data from the database
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT strftime('%Y-%m', date) AS month, SUM(amount) FROM transactions WHERE user_id = %s GROUP BY month", (user_id,))
        data = cursor.fetchall()
        conn.close()

        # Format data for Chart.js
        labels = [datetime.strptime(row[0], '%Y-%m').strftime('%b %Y') for row in data]
        amounts = [row[1] for row in data]

        return jsonify({'labels': labels, 'amounts': amounts})
    else:
        return redirect(url_for('login'))

# Statistics Route
@app.route('/statistics')
def statistics():
    if 'username' in session:
        user_id = session['user_id']
        
        # Fetch data for statistics page for the logged-in user from the database
        conn = get_connection()
        cursor = conn.cursor()

        # Fetch total expenses for the logged-in user
        cursor.execute("SELECT SUM(amount) FROM transactions WHERE user_id = %s", (user_id,))
        total_expenses_result = cursor.fetchone()
        total_expenses = total_expenses_result[0] if total_expenses_result else 0

        # Fetch expense breakdown by category
        cursor.execute("SELECT category, SUM(amount) FROM transactions WHERE user_id = %s GROUP BY category", (user_id,))
        expense_by_category_result = cursor.fetchall()
        expense_by_category = dict(expense_by_category_result) if expense_by_category_result else {}

        # Fetch top spending categories
        cursor.execute("SELECT category, SUM(amount) FROM transactions WHERE user_id = %s GROUP BY category ORDER BY SUM(amount) DESC LIMIT 5", (user_id,))
        top_spending_categories_result = cursor.fetchall()
        top_spending_categories = dict(top_spending_categories_result) if top_spending_categories_result else {}

        conn.close()

        return render_template('statistics.html', total_expenses=total_expenses, expense_by_category=expense_by_category,
                               top_spending_categories=top_spending_categories)
    else:
        return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)
