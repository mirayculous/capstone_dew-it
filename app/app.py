from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_cors import CORS
import pandas as pd
import numpy as np
import tensorflow as tf
from datetime import datetime
import pymysql
from google.cloud.sql.connector import Connector
from google.oauth2 import service_account
import os
from sklearn.preprocessing import MinMaxScaler

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
                # Membuat tabel users
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        username VARCHAR(255) NOT NULL,
                        email VARCHAR(255) NOT NULL,
                        phone VARCHAR(15) NOT NULL,
                        password VARCHAR(255) NOT NULL
                    )
                ''')
                
                # Membuat tabel incomes
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS incomes (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        user_id INT NOT NULL,
                        amount DECIMAL(10, 2) NOT NULL,
                        date DATE NOT NULL,
                        FOREIGN KEY (user_id) REFERENCES users(id)
                    )
                ''')
                
                # Membuat tabel expenses
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS expenses (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        user_id INT NOT NULL,
                        amount DECIMAL(10, 2) NOT NULL,
                        date DATE NOT NULL,
                        FOREIGN KEY (user_id) REFERENCES users(id)
                    )
                ''')
                
                conn.commit()
                print("Database initialized successfully.")
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
                    # Ambil total income
                    cursor.execute("SELECT SUM(amount) FROM incomes WHERE user_id = %s", (user_id,))
                    total_income = cursor.fetchone()[0] or 0  # Default to 0 if None
                    
                    # Ambil total expense
                    cursor.execute("SELECT SUM(amount) FROM expenses WHERE user_id = %s", (user_id,))
                    total_expense = cursor.fetchone()[0] or 0  # Default to 0 if None

        return render_template(
            'index.html',
            total_income=total_income,
            total_expense=total_expense,
            username=username
        )
    
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
                    # Ambil data dari tabel incomes dan expenses
                    cursor.execute("SELECT * FROM incomes WHERE user_id = %s", (user_id,))
                    income_transactions = cursor.fetchall()

                    cursor.execute("SELECT * FROM expenses WHERE user_id = %s", (user_id,))
                    expense_transactions = cursor.fetchall()

        return render_template(
            'transaction.html', 
            income_transactions=income_transactions, 
            expense_transactions=expense_transactions, 
            username=username
        )
    
    return redirect(url_for('login'))

@app.route('/add_transaction', methods=['POST'])
def add_transaction():
    if 'username' in session:
        user_id = session['user_id']
        date = request.form['date']
        amount = request.form['amount']
        type = request.form['type']

        # Validasi jumlah
        if not amount.replace('.', '', 1).isdigit() or float(amount) <= 0:
            flash('Amount must be a positive number.', 'error')
            return redirect(url_for('transactions'))

        # Koneksi manual tanpa blok `with`
        conn = get_connection()
        if conn:
            try:
                cursor = conn.cursor()

                if type.lower() == "income":
                    # Masukkan ke tabel incomes
                    cursor.execute(
                        "INSERT INTO incomes (user_id, amount, date) "
                        "VALUES (%s, %s, %s)",
                        (user_id, amount, date)
                    )
                elif type.lower() == "expense":
                    # Masukkan ke tabel expenses
                    cursor.execute(
                        "INSERT INTO expenses (user_id, amount, date) "
                        "VALUES (%s, %s, %s)",
                        (user_id, amount, date)
                    )

                conn.commit()
                flash('Transaction added successfully.', 'success')
            except pymysql.MySQLError as e:
                print(f"Database Error: {e}")
                flash('Failed to add transaction.', 'error')
            finally:
                cursor.close()
                conn.close()

        return redirect(url_for('transactions'))
    else:
        return redirect(url_for('login'))


@app.route('/delete_transaction/<string:transaction_type>/<int:transaction_id>', methods=['POST'])
def delete_transaction(transaction_type, transaction_id):
    if 'username' in session:
        with get_connection() as conn:
            if conn:
                with conn.cursor() as cursor:
                    if transaction_type == 'income':
                        # Delete from incomes table
                        cursor.execute("DELETE FROM incomes WHERE id = %s", (transaction_id,))
                    elif transaction_type == 'expense':
                        # Delete from expenses table
                        cursor.execute("DELETE FROM expenses WHERE id = %s", (transaction_id,))
                    else:
                        flash('Invalid transaction type.', 'error')
                        return redirect(url_for('transactions'))
                    
                    conn.commit()
                    flash('Transaction deleted successfully.', 'success')
    else:
        flash('You must be logged in to delete a transaction.', 'error')

    return redirect(url_for('transactions'))

# Load models
income_model = tf.keras.models.load_model(
    'app\model\model_income.h5', custom_objects={'mse': tf.keras.losses.MeanSquaredError()}
)
expenses_model = tf.keras.models.load_model(
    'app\model\model_expenses.h5', custom_objects={'mse': tf.keras.losses.MeanSquaredError()}
)

# Load scalers
income_scaler = MinMaxScaler(feature_range=(0, 1))
expenses_scaler = MinMaxScaler(feature_range=(0, 1))

@app.route("/statistics", methods=["GET", "POST"])
def statistics():
    user_id = session.get('user_id')
    if request.method == "POST":
        try:
            # Hubungkan ke database cloud
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute(
            "SELECT amount FROM incomes WHERE user_id = %s ORDER BY date DESC LIMIT 12", (user_id,))
            income_data = cursor.fetchall()
            income_data = [row[0] for row in income_data]  # Mengubah hasil menjadi list sederhana

            # Mengambil data pengeluaran terakhir 12 bulan
            cursor.execute(
            "SELECT amount FROM expenses WHERE user_id = %s ORDER BY date DESC LIMIT 12", (user_id,))
            expenses_data = cursor.fetchall()
            expenses_data = [row[0] for row in expenses_data]  # Mengubah hasil menjadi list sederhana

            conn.close()

            # Validasi data
            if len(income_data) != 12 or len(expenses_data) != 12:
                return jsonify({"error": "Data dari database tidak mencukupi."}), 500

            # Siapkan data input untuk model
            income_values = [row[0] for row in income_data]
            expenses_values = [row[0] for row in expenses_data]

            last_window_income = income_scaler.fit_transform(
                np.array(income_values).reshape(-1, 1)
            ).reshape(1, -1, 1)

            last_window_expenses = expenses_scaler.fit_transform(
                np.array(expenses_values).reshape(-1, 1)
            ).reshape(1, -1, 1)

            # Prediksi
            future_income = forecast_future(income_model, income_scaler, last_window_income)
            future_expenses = forecast_future(expenses_model, expenses_scaler, last_window_expenses)

            return jsonify({
                "forecasted_income": list(map(float, future_income.flatten())),
                "forecasted_expenses": list(map(float, future_expenses.flatten()))
            })

        except Exception as e:
            return jsonify({"error": f"Terjadi kesalahan: {str(e)}"}), 500

    return render_template("statistics.html")


def forecast_future(model, scaler, last_window, steps=12):
    future_input = last_window
    forecast = []
    for _ in range(steps):
        pred = model.predict(future_input, verbose=0)
        forecast.append(pred[0, 0])
        future_input = np.append(future_input[:, 1:, :], [[pred[0]]], axis=1)
    forecast = np.array(forecast).reshape(-1, 1)
    return scaler.inverse_transform(forecast)

if __name__ == "__main__":
    app.run(debug=True)
