import os
import uuid
import requests
import threading
import time
from flask import Flask, redirect, url_for, request, jsonify, render_template
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import IntegrityError

app = Flask(__name__)
CORS(app, supports_credentials=True)
app.secret_key = os.urandom(24)

# Configure SQLAlchemy to use PostgreSQL via Render's DATABASE_URL.
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///database.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Spotify API credentials
SPOTIFY_CLIENT_ID = 'f5dd28f91f6f44048eee06f0903f308c'
SPOTIFY_CLIENT_SECRET = 'd65b54fc514f453d8e6617768ab02471'
SPOTIFY_REDIRECT_URI = 'https://music-widget1.onrender.com/callback'

# Define the User model.
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    spotify_user_id = db.Column(db.String(128), unique=True, nullable=False)
    user_key = db.Column(db.String(36), unique=True, nullable=False)
    access_token = db.Column(db.String(256))
    refresh_token = db.Column(db.String(256))

with app.app_context():
    db.create_all()

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/login')
def login():
    auth_url = (
        f"https://accounts.spotify.com/authorize?response_type=code&client_id={SPOTIFY_CLIENT_ID}"
        f"&redirect_uri={SPOTIFY_REDIRECT_URI}&scope=user-read-currently-playing%20user-read-playback-state"
    )
    return redirect(auth_url)

def refresh_access_token(user):
    """Refresh the access token for a given user and update the database."""
    data = {
        'grant_type': 'refresh_token',
        'refresh_token': user.refresh_token,
        'client_id': SPOTIFY_CLIENT_ID,
        'client_secret': SPOTIFY_CLIENT_SECRET,
    }
    response = requests.post('https://accounts.spotify.com/api/token', data=data)
    try:
        response_data = response.json()
    except ValueError:
        return None
    new_access_token = response_data.get('access_token')
    if new_access_token:
        user.access_token = new_access_token
        db.session.commit()
        return new_access_token
    return None

@app.route('/callback')
def callback():
    code = request.args.get('code')
    
    # Redirect to login if code is missing (e.g., page refresh)
    if not code:
        return redirect(url_for('login'))

    data = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': SPOTIFY_REDIRECT_URI,
        'client_id': SPOTIFY_CLIENT_ID,
        'client_secret': SPOTIFY_CLIENT_SECRET,
    }
    token_response = requests.post('https://accounts.spotify.com/api/token', data=data)
    
    try:
        token_data = token_response.json()
    except ValueError:
        return redirect(url_for('login'))

    if 'error' in token_data:
        return redirect(url_for('login'))

    access_token = token_data.get('access_token')
    refresh_token = token_data.get('refresh_token')

    headers = {'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json'}
    profile_response = requests.get("https://api.spotify.com/v1/me", headers=headers)

    if profile_response.status_code != 200:
        return redirect(url_for('login'))

    user_info = profile_response.json()
    spotify_user_id = user_info.get('id')

    if not spotify_user_id:
        return redirect(url_for('login'))

    # Create or update user record.
    user = User.query.filter_by(spotify_user_id=spotify_user_id).first()
    if user:
        user.access_token = access_token
        user.refresh_token = refresh_token
        db.session.commit()
    else:
        user_key = str(uuid.uuid4())
        user = User(
            spotify_user_id=spotify_user_id,
            user_key=user_key,
            access_token=access_token,
            refresh_token=refresh_token
        )
        db.session.add(user)
        db.session.commit()

    return render_template('profile.html', user_key=user.user_key)

@app.route('/currently-playing')
def currently_playing():
    user_key = request.args.get('userKey')
    if not user_key:
        return jsonify({"error": "Missing userKey"}), 400
    
    user = User.query.filter_by(user_key=user_key).first()
    if not user:
        return jsonify({"error": "Invalid userKey"}), 400
    
    headers = {'Authorization': f'Bearer {user.access_token}', 'Content-Type': 'application/json'}
    response = requests.get("https://api.spotify.com/v1/me/player/currently-playing", headers=headers)

    if response.status_code == 401:
        new_token = refresh_access_token(user)
        if new_token:
            headers['Authorization'] = f'Bearer {new_token}'
            response = requests.get("https://api.spotify.com/v1/me/player/currently-playing", headers=headers)

    if response.status_code == 204:
        return jsonify({
            "track": "",
            "artists": "",
            "album_image_url": "",
            "is_playing": False,
            "progress_ms": 0,
            "duration_ms": 0
        }), 200
    elif response.status_code != 200:
        return jsonify({"error": "Failed to fetch currently playing"}), response.status_code

    data = response.json()
    if data and data.get('item'):
        track_name = data['item'].get('name', 'Unknown Title')
        artists = ", ".join([artist['name'] for artist in data['item'].get('artists', [])])
        is_playing = data.get('is_playing', False)
        progress_ms = data.get('progress_ms', 0)
        duration_ms = data['item'].get('duration_ms', 1)
        album_images = data['item'].get('album', {}).get('images', [])
        album_image_url = album_images[0]['url'] if album_images else ""
        return jsonify({
            "track": track_name,
            "artists": artists,
            "album_image_url": album_image_url,
            "is_playing": is_playing,
            "progress_ms": progress_ms,
            "duration_ms": duration_ms
        })

    return jsonify({
        "track": "",
        "artists": "",
        "album_image_url": "",
        "is_playing": False,
        "progress_ms": 0,
        "duration_ms": 0
    }), 200

def keep_alive():
    """
    Periodically ping the app to keep it active.
    This function sends a GET request to the home page once every hour.
    """
    while True:
        try:
            # Replace the URL below with your actual Render URL if different.
            requests.get("https://music-widget1.onrender.com")
            print("Pinged self to keep alive.")
        except Exception as e:
            print("Keep-alive ping failed:", e)
        # Wait for one hour (3600 seconds) before the next ping.
        time.sleep(3600)

if __name__ == '__main__':
    # Start the keep-alive thread as a daemon.
    ping_thread = threading.Thread(target=keep_alive)
    ping_thread.daemon = True
    ping_thread.start()

    # Start the Flask app.
    app.run(port=3000, debug=True)
