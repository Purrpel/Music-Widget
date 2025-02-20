import os
import uuid
import requests
from flask import Flask, redirect, url_for, request, jsonify, render_template
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import IntegrityError

app = Flask(__name__)
CORS(app, supports_credentials=True)
app.secret_key = os.urandom(24)

# Configure SQLAlchemy to use PostgreSQL via Render's DATABASE_URL.
# For local testing, it falls back to SQLite.
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///database.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Spotify API credentials
SPOTIFY_CLIENT_ID = 'f5dd28f91f6f44048eee06f0903f308c'
SPOTIFY_CLIENT_SECRET = 'd65b54fc514f453d8e6617768ab02471'
SPOTIFY_REDIRECT_URI = 'https://music-widget.onrender.com/callback'

# Define the User model.
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    spotify_user_id = db.Column(db.String(128), unique=True, nullable=False)
    user_key = db.Column(db.String(36), unique=True, nullable=False)
    access_token = db.Column(db.String(256))
    refresh_token = db.Column(db.String(256))

# Create the database tables if they don't exist.
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
    """Refresh the access token for a given user (User model instance) and update the DB."""
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
    if not code:
        return "Error: Missing code in callback"
    
    # Exchange the code for tokens.
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
        return f"Error decoding token response: {token_response.text}", 500

    if 'error' in token_data:
        return f"Error exchanging code: {token_data}. Please <a href='/login'>login</a> again."
    
    access_token = token_data.get('access_token')
    refresh_token = token_data.get('refresh_token')
    
    if not access_token or not refresh_token:
        return f"Error: {token_data}. Please <a href='/login'>login</a> again."
    
    # Retrieve the Spotify user profile.
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }
    profile_response = requests.get("https://api.spotify.com/v1/me", headers=headers)
    if profile_response.status_code != 200:
        try:
            error_details = profile_response.json()
        except ValueError:
            error_details = profile_response.text or "No details provided."
        return f"Error fetching profile: {error_details}", 500
    try:
        user_info = profile_response.json()
    except ValueError:
        return f"Error parsing profile response: {profile_response.text}", 500

    spotify_user_id = user_info.get('id')
    if not spotify_user_id:
        return "Error: Could not retrieve Spotify user ID."
    
    # Check if this Spotify user already exists.
    user = User.query.filter_by(spotify_user_id=spotify_user_id).first()
    if user:
        try:
            # Update tokens but keep the existing widget key.
            user.access_token = access_token
            user.refresh_token = refresh_token
            db.session.commit()
        except IntegrityError as e:
            db.session.rollback()
            return f"Database error updating user: {str(e)}", 500
    else:
        try:
            # Create a new user with a unique widget key.
            user_key = str(uuid.uuid4())
            user = User(
                spotify_user_id=spotify_user_id,
                user_key=user_key,
                access_token=access_token,
                refresh_token=refresh_token
            )
            db.session.add(user)
            db.session.commit()
        except IntegrityError as e:
            db.session.rollback()
            return f"Database error creating user: {str(e)}", 500

    # Render the profile page with the widget key.
    return render_template('profile.html', user_key=user.user_key)

@app.route('/profile')
def profile():
    # For debugging: retrieve user info based on a provided user_key.
    user_key = request.args.get('user_key')
    if not user_key:
        return "No user key provided."
    
    user = User.query.filter_by(user_key=user_key).first()
    if not user:
        return "User not found. Please login."
    
    headers = {
        'Authorization': f'Bearer {user.access_token}',
        'Content-Type': 'application/json'
    }
    response = requests.get("https://api.spotify.com/v1/me", headers=headers)
    if response.status_code != 200:
        new_token = refresh_access_token(user)
        if new_token:
            headers['Authorization'] = f'Bearer {new_token}'
            response = requests.get("https://api.spotify.com/v1/me", headers=headers)
    
    if response.status_code != 200:
        try:
            error_details = response.json()
        except ValueError:
            error_details = response.text or "No details provided."
        return f"Error: Unable to fetch user profile from Spotify - {error_details}", 500
    try:
        user_info = response.json()
    except ValueError:
        return f"Error parsing profile response: {response.text}", 500
    
    return f"Hello, {user_info.get('display_name', 'User')}! Your Widget Key: {user.user_key}"

@app.route('/currently-playing')
def currently_playing():
    # The widget should pass the unique user key as a query parameter 'userKey'
    user_key = request.args.get('userKey')
    if not user_key:
        return jsonify({"error": "Missing userKey"}), 400
    
    user = User.query.filter_by(user_key=user_key).first()
    if not user:
        return jsonify({"error": "Invalid userKey"}), 400
    
    headers = {
        'Authorization': f'Bearer {user.access_token}',
        'Content-Type': 'application/json'
    }
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
        try:
            error_details = response.json()
        except ValueError:
            error_details = response.text or "No details provided."
        return jsonify({
            "error": "Failed to fetch currently playing",
            "details": error_details
        }), response.status_code

    try:
        data = response.json()
    except ValueError:
        return jsonify({"error": "Error parsing currently playing response", "details": response.text}), 500

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

if __name__ == '__main__':
    app.run(port=3000, debug=True)
