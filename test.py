import requests
import random
import time
from PIL import Image, ImageDraw
import io
from datetime import datetime

SERVER_URL = "http://localhost:5000"  # Change if your server is on a different address

def generate_random_sensor_data():
    """Generate random BME680 sensor data"""
    return {
        "temperature": random.uniform(20.0, 35.0),
        "humidity": random.uniform(30.0, 80.0),
        "pressure": random.uniform(980.0, 1020.0),
        "gas_resistance": random.uniform(1000.0, 5000.0),
        "iaq": random.uniform(0.0, 500.0)
    }

def generate_test_image(camera_id):
    """Generate a test image with current timestamp and random patterns"""
    # Create a new image with a random background color
    width, height = 640, 480
    image = Image.new('RGB', (width, height), (
        random.randint(200, 255),
        random.randint(200, 255),
        random.randint(200, 255)
    ))
    draw = ImageDraw.Draw(image)
    
    # Add random shapes
    for _ in range(10):
        shape_type = random.choice(['rectangle', 'ellipse'])
        x1 = random.randint(0, width)
        y1 = random.randint(0, height)
        x2 = random.randint(x1, min(x1 + 100, width))
        y2 = random.randint(y1, min(y1 + 100, height))
        color = (
            random.randint(0, 200),
            random.randint(0, 200),
            random.randint(0, 200)
        )
        if shape_type == 'rectangle':
            draw.rectangle([x1, y1, x2, y2], fill=color)
        else:
            draw.ellipse([x1, y1, x2, y2], fill=color)
    
    # Add timestamp and camera ID
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    draw.text((10, 10), f'Camera: {camera_id}', fill=(0, 0, 0))
    draw.text((10, 30), f'Time: {current_time}', fill=(0, 0, 0))
    
    # Convert to bytes
    img_byte_arr = io.BytesIO()
    image.save(img_byte_arr, format='JPEG')
    img_byte_arr.seek(0)
    
    return img_byte_arr

def send_sensor_data():
    """Send random sensor data to server"""
    data = generate_random_sensor_data()
    try:
        response = requests.post(f"{SERVER_URL}/api/sensor_data", json=data)
        if response.status_code == 200:
            print(f"Sensor data sent successfully: {data}")
        else:
            print(f"Failed to send sensor data. Status code: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"Error sending sensor data: {e}")

def send_camera_image(camera_id):
    """Send test image to server"""
    img_data = generate_test_image(camera_id)
    files = {'image': ('image.jpg', img_data, 'image/jpeg')}
    try:
        response = requests.post(
            f"{SERVER_URL}/api/camera_upload/{camera_id}",
            files=files
        )
        if response.status_code == 200:
            print(f"Image sent successfully for camera {camera_id}")
        else:
            print(f"Failed to send image for camera {camera_id}. Status code: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"Error sending image: {e}")

def main():
    # Configuration
    num_cameras = 3  # Number of simulated cameras
    sensor_interval = 5  # Seconds between sensor readings
    camera_interval = 10  # Seconds between camera captures
    
    print("Starting ESP32 simulation...")
    print(f"Simulating {num_cameras} cameras")
    print(f"Sensor interval: {sensor_interval} seconds")
    print(f"Camera interval: {camera_interval} seconds")
    
    last_sensor_time = 0
    last_camera_time = 0
    
    try:
        while True:
            current_time = time.time()
            
            # Send sensor data
            if current_time - last_sensor_time >= sensor_interval:
                send_sensor_data()
                last_sensor_time = current_time
            
            # Send camera images
            if current_time - last_camera_time >= camera_interval:
                for camera_id in range(1, num_cameras + 1):
                    send_camera_image(f"cam{camera_id}")
                last_camera_time = current_time
            
            time.sleep(1)  # Small delay to prevent excessive CPU usage
            
    except KeyboardInterrupt:
        print("\nStopping simulation...")

if __name__ == "__main__":
    main()