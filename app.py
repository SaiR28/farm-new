from flask import Flask, render_template, send_file, jsonify, request, send_from_directory
import pandas as pd
import sqlite3
from datetime import datetime
import os
import zipfile
import io
import pytz

app = Flask(__name__)

# Configuration
UPLOAD_FOLDER = 'camera_images'
DATABASE = 'sensor_data.db'
ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png'}

# Ensure upload folders exist
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# IST timezone setup
IST = pytz.timezone('Asia/Kolkata')

def init_db():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS sensor_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            temperature FLOAT,
            humidity FLOAT,
            pressure FLOAT,
            gas_resistance FLOAT,
            iaq FLOAT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/sensor_data', methods=['POST'])
def receive_sensor_data():
    data = request.json
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('''
        INSERT INTO sensor_data 
        (temperature, humidity, pressure, gas_resistance)
        VALUES (?, ?, ?, ?)
    ''', (
        data['temperature'],
        data['humidity'],
        data['pressure'],
        data['gas_resistance'],
    ))
    conn.commit()
    conn.close()
    return jsonify({"status": "success"})

@app.route('/api/latest_sensor_data')
def get_latest_sensor_data():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('''
        SELECT * FROM sensor_data 
        ORDER BY timestamp DESC 
        LIMIT 1
    ''')
    data = c.fetchone()
    conn.close()

    if data:
        # Convert timestamp to IST
        timestamp_utc = datetime.strptime(data[1], '%Y-%m-%d %H:%M:%S')
        timestamp_ist = timestamp_utc.replace(tzinfo=pytz.utc).astimezone(IST)

        return jsonify({
            "timestamp": timestamp_ist.isoformat(),
            "temperature": data[2],
            "humidity": data[3],
            "pressure": data[4],
            "gas_resistance": data[5],
            "iaq": data[6]
        })
    return jsonify({"error": "No data available"})

@app.route('/api/camera_upload/<camera_id>', methods=['POST'])
def upload_image(camera_id):
    if 'image' not in request.files:
        return jsonify({"error": "No image file"}), 400
        
    file = request.files['image']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
        
    camera_folder = os.path.join(UPLOAD_FOLDER, f'camera_{camera_id}')
    if not os.path.exists(camera_folder):
        os.makedirs(camera_folder)
        
    # Save with IST timestamp in filename
    timestamp = datetime.now(IST).strftime('%Y%m%d_%H%M%S')
    filename = f"{timestamp}.jpg"
    file_path = os.path.join(camera_folder, filename)
    file.save(file_path)
    
    return jsonify({"status": "success"})

@app.route('/api/latest_images')
def get_latest_images():
    images = {}
    for folder in os.listdir(UPLOAD_FOLDER):
        if folder.startswith('camera_'):
            camera_folder = os.path.join(UPLOAD_FOLDER, folder)
            if os.path.exists(camera_folder):
                image_files = [f for f in os.listdir(camera_folder) 
                               if f.lower().endswith(tuple(ALLOWED_EXTENSIONS))]
                if image_files:
                    latest_image = max(image_files, key=lambda x: os.path.getctime(
                        os.path.join(camera_folder, x)
                    ))
                    image_timestamp_utc = os.path.getctime(os.path.join(camera_folder, latest_image))
                    image_timestamp_ist = datetime.fromtimestamp(image_timestamp_utc, pytz.utc).astimezone(IST)

                    images[folder] = {
                        'filename': latest_image,
                        'timestamp': image_timestamp_ist.isoformat(),
                        'url': f'/images/{folder}/{latest_image}'
                    }
    return jsonify(images)

@app.route('/download/sensor_data')
def download_sensor_data():
    conn = sqlite3.connect(DATABASE)
    data = pd.read_sql_query("SELECT * FROM sensor_data", conn)
    conn.close()

    # Convert the timestamp column to IST (Indian Standard Time)
    data['timestamp'] = pd.to_datetime(data['timestamp'])
    data['timestamp'] = data['timestamp'].dt.tz_localize('UTC').dt.tz_convert('Asia/Kolkata')

    # Format the timestamp to string without timezone information (remove +05:30)
    data['timestamp'] = data['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')

    # Round numeric columns to 2 decimal places
    numeric_columns = ['temperature', 'humidity', 'pressure', 'gas_resistance', 'iaq']
    data[numeric_columns] = data[numeric_columns].round(2)

    # Create a CSV in memory with IST timestamps and rounded values
    csv_buffer = io.StringIO()
    data.to_csv(csv_buffer, index=False)
    
    mem_file = io.BytesIO()
    mem_file.write(csv_buffer.getvalue().encode())
    mem_file.seek(0)
    
    return send_file(
        mem_file,
        mimetype='text/csv',
        as_attachment=True,
        download_name='sensor_data_ist_rounded.csv'
    )


@app.route('/images/<camera_id>/<filename>')
def serve_image(camera_id, filename):
    try:
        return send_from_directory(
            os.path.join(UPLOAD_FOLDER, camera_id),
            filename
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 404

@app.route('/download/images')
def download_images():
    memory_file = io.BytesIO()
    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(UPLOAD_FOLDER):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, UPLOAD_FOLDER)
                zf.write(file_path, arcname)
    
    memory_file.seek(0)
    return send_file(
        memory_file,
        mimetype='application/zip',
        as_attachment=True,
        download_name='camera_images.zip'
    )

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
