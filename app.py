from flask import Flask, render_template, send_file, jsonify, request, send_from_directory
import pandas as pd
import sqlite3
from datetime import datetime
import os
import zipfile
import io
import pytz
from flask import after_this_request
import traceback
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
    try:
        # Create database connection
        conn = sqlite3.connect(DATABASE)
        
        # Read data
        data = pd.read_sql_query("SELECT * FROM sensor_data", conn)
        conn.close()

        # Convert timestamps and round values
        data['timestamp'] = pd.to_datetime(data['timestamp'])
        data['timestamp'] = data['timestamp'].dt.tz_localize('UTC').dt.tz_convert('Asia/Kolkata')
        data['timestamp'] = data['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')
        
        numeric_columns = ['temperature', 'humidity', 'pressure', 'gas_resistance', 'iaq']
        data[numeric_columns] = data[numeric_columns].round(2)

        # Generate filename
        filename = f'sensor_data_ist_rounded_{datetime.now(IST).strftime("%Y%m%d_%H%M%S")}.csv'
        
        # Create response
        output = io.StringIO()
        data.to_csv(output, index=False)
        response = app.make_response(output.getvalue())
        output.close()
        
        # Set headers
        response.headers["Content-Disposition"] = f"attachment; filename={filename}"
        response.headers["Content-type"] = "text/csv"
        
        return response

    except Exception as e:
        app.logger.error(f"Error in download_sensor_data: {str(e)}")
        return jsonify({'error': 'Failed to generate CSV file'}), 500
    finally:
        try:
            conn.close()
        except:
            pass
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
    try:
        # Check if the UPLOAD_FOLDER exists and has camera directories
        if not os.path.exists(UPLOAD_FOLDER):
            app.logger.error(f"Upload folder {UPLOAD_FOLDER} does not exist")
            return jsonify({'error': 'No images directory found'}), 404
            
        # Check for camera directories
        camera_dirs = [d for d in os.listdir(UPLOAD_FOLDER) if d.startswith('camera_')]
        if not camera_dirs:
            app.logger.error("No camera directories found in upload folder")
            return jsonify({'error': 'No camera directories found'}), 404

        # Create a temporary directory with error handling
        temp_dir = os.path.join(os.getcwd(), 'temp')
        try:
            if not os.path.exists(temp_dir):
                os.makedirs(temp_dir, exist_ok=True)
        except Exception as e:
            app.logger.error(f"Failed to create temp directory: {str(e)}")
            return jsonify({'error': 'Failed to create temporary directory'}), 500

        # Create zip filename with timestamp
        timestamp = datetime.now(IST).strftime("%Y%m%d_%H%M%S")
        zip_filename = f'camera_images_{timestamp}.zip'
        zip_filepath = os.path.join(temp_dir, zip_filename)

        files_exist = False
        file_count = 0
        
        try:
            with zipfile.ZipFile(zip_filepath, 'w', zipfile.ZIP_DEFLATED) as zf:
                for camera_dir in camera_dirs:
                    camera_path = os.path.join(UPLOAD_FOLDER, camera_dir)
                    if not os.path.isdir(camera_path):
                        continue
                        
                    for file in os.listdir(camera_path):
                        if file.lower().endswith(tuple(ALLOWED_EXTENSIONS)):
                            file_path = os.path.join(camera_path, file)
                            if not os.path.exists(file_path):
                                app.logger.warning(f"File {file_path} does not exist")
                                continue
                                
                            try:
                                # Check if file is readable
                                if not os.access(file_path, os.R_OK):
                                    app.logger.error(f"File {file_path} is not readable")
                                    continue
                                    
                                # Check file size
                                if os.path.getsize(file_path) == 0:
                                    app.logger.warning(f"File {file_path} is empty")
                                    continue
                                    
                                arcname = os.path.join(camera_dir, file)
                                zf.write(file_path, arcname)
                                files_exist = True
                                file_count += 1
                                
                            except Exception as e:
                                app.logger.error(f"Error adding file {file_path} to zip: {str(e)}")
                                continue
        
        except Exception as zip_error:
            app.logger.error(f"Error creating zip file: {str(zip_error)}")
            # Clean up the zip file if it exists
            if os.path.exists(zip_filepath):
                os.remove(zip_filepath)
            return jsonify({'error': 'Failed to create ZIP file'}), 500

        if not files_exist:
            app.logger.error("No valid image files found to zip")
            if os.path.exists(zip_filepath):
                os.remove(zip_filepath)
            return jsonify({'error': 'No valid image files found'}), 404

        app.logger.info(f"Successfully created zip file with {file_count} images")

        @after_this_request
        def remove_file(response):
            try:
                if os.path.exists(zip_filepath):
                    os.remove(zip_filepath)
                if os.path.exists(temp_dir) and not os.listdir(temp_dir):
                    os.rmdir(temp_dir)
            except Exception as e:
                app.logger.error(f"Error removing temporary file: {str(e)}")
            return response

        return send_file(
            zip_filepath,
            mimetype='application/zip',
            as_attachment=True,
            download_name=zip_filename
        )

    except Exception as e:
        app.logger.error(f"Error in download_images: {str(e)}")
        app.logger.error(traceback.format_exc())
        
        # Clean up any temporary files if they exist
        try:
            if 'zip_filepath' in locals() and os.path.exists(zip_filepath):
                os.remove(zip_filepath)
            if 'temp_dir' in locals() and os.path.exists(temp_dir) and not os.listdir(temp_dir):
                os.rmdir(temp_dir)
        except Exception as cleanup_error:
            app.logger.error(f"Error during cleanup: {str(cleanup_error)}")
            
        return jsonify({'error': 'Failed to generate ZIP file'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
