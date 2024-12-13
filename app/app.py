from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_cors import CORS
import pickle
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
    "project_id": "project-dewit-442507",\
    "region": "asia-southeast2",
    "instance_id": "sql",
    "database_name": "dewit",
    "user": "root",
    "password": "root"
}

# Function to connect to the database
def get_connection():
        connection = connector.connect(
            f"{DATABASE['project_id']}:{DATABASE['region']}:{DATABASE['instance_id']}",
            "pymysql",
            user=DATABASE['user'],
            password=DATABASE['password'],
            db=DATABASE['database_name'],
            port=3306,
        )
        return connection

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
                        amount FLOAT NOT NULL,
                        date DATE NOT NULL,
                        FOREIGN KEY (user_id) REFERENCES users(id)
                    )
                ''')
                
                # Membuat tabel expenses
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS expenses (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        user_id INT NOT NULL,
                        amount FLOAT NOT NULL,
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
            income_transactions=income_transactions, expense_transactions=expense_transactions, username=username
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
    else:\
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

# Define constants
WINDOW_SIZE = 12

# Load pre-trained models
model_income = tf.keras.models.load_model(
    'app/model/model_income.h5',
    custom_objects={'mse': tf.keras.losses.MeanSquaredError()}
)

model_expenses = tf.keras.models.load_model(
    'app/model/model_expenses.h5',
    custom_objects={'mse': tf.keras.losses.MeanSquaredError()}
)

# Load scalers
with open('app/model/scaler_income.pkl', 'rb') as f:
    scaler_income = pickle.load(f)

with open('app/model/scaler_expenses.pkl', 'rb') as f:
    scaler_expenses = pickle.load(f)

# Define prediction function
def forecast_future(model, scaler, last_window, steps=12):
    future_input = last_window
    forecast = []
    for _ in range(steps):
        pred = model.predict(future_input, verbose=0)
        forecast.append(pred[0, 0])
        future_input = np.append(future_input[:, 1:, :], [[pred[0]]], axis=1)
    forecast = np.array(forecast).reshape(-1, 1)
    return scaler.inverse_transform(forecast)

# Define routes
@app.route("/forecast", methods=["GET", "POST"])
def forecast():
    if request.method == "POST":
        data = request.json
        if not data or "last_window" not in data:
            return jsonify({"error": "Invalid input"}), 400

        last_window_income = np.array(data["last_window"]["income"]).reshape(1, -1, 1)
        last_window_expenses = np.array(data["last_window"]["expenses"]).reshape(1, -1, 1)

        if last_window_income.shape[1] != WINDOW_SIZE or last_window_expenses.shape[1] != WINDOW_SIZE:
            return jsonify({"error": "Each input must contain exactly 12 values."}), 400

        # Forecast income and expenses
        future_income = forecast_future(model_income, scaler_income, last_window_income)
        future_expenses = forecast_future(model_expenses, scaler_expenses, last_window_expenses)

        return jsonify({
            "forecasted_income": list(map(float, future_income.flatten())),
            "forecasted_expenses": list(map(float, future_expenses.flatten()))
        })

    return render_template("statistics.html")


if __name__ == "__main__":
    app.run(debug=True)

