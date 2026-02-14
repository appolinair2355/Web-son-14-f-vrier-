import os
import json
import hashlib
import uuid
import threading
import shutil
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory, jsonify
from werkzeug.utils import secure_filename
import subprocess

app = Flask(__name__, template_folder='.')
app.secret_key = os.environ.get('SECRET_KEY', 'votre-cle-secrete-123')

# Configuration
UPLOAD_FOLDER = 'uploads'
SEPARATED_FOLDER = 'separated'
ALLOWED_EXTENSIONS = {'mp3', 'wav', 'flac', 'm4a', 'ogg'}
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB

# Dictionnaire pour stocker la progression des séparations
separation_progress = {}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(SEPARATED_FOLDER, exist_ok=True)

# Initialiser les fichiers JSON
def init_json_files():
    for filename in ['users.json', 'audios.json', 'feedbacks.json']:
        if not os.path.exists(filename):
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump([], f)

init_json_files()

def load_json(filename):
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return []

def save_json(filename, data):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def is_admin_user(nom, prenom):
    return nom.lower() == "sossou" and prenom.lower() == "kouamé"

def run_separation(audio_id, filepath, filename, user_id):
    """Fonction exécutée en arrière-plan pour la séparation"""
    try:
        separation_progress[audio_id] = {'status': 'starting', 'progress': 10}
        
        # Commande Demucs
        cmd = [
            'python', '-m', 'demucs',
            '--out', SEPARATED_FOLDER,
            '--filename', '{track}/{stem}.{ext}',
            filepath
        ]
        
        separation_progress[audio_id] = {'status': 'processing', 'progress': 40}
        
        # Exécuter la commande
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        if result.returncode == 0:
            # Trouver les fichiers générés
            track_name = os.path.basename(filepath).rsplit('.', 1)[0]
            model_name = 'htdemucs'
            separated_path = os.path.join(SEPARATED_FOLDER, model_name, track_name)
            
            output_files = []
            if os.path.exists(separated_path):
                for stem in ['vocals', 'drums', 'bass', 'other']:
                    stem_file = os.path.join(separated_path, f"{stem}.wav")
                    if os.path.exists(stem_file):
                        # Copier avec nom unique
                        new_name = f"{audio_id}_{stem}.wav"
                        new_path = os.path.join(SEPARATED_FOLDER, new_name)
                        shutil.copy2(stem_file, new_path)
                        output_files.append(new_name)
                
                # Nettoyer le dossier temporaire
                shutil.rmtree(os.path.join(SEPARATED_FOLDER, model_name), ignore_errors=True)
            
            # Mettre à jour JSON
            audios = load_json('audios.json')
            for audio in audios:
                if audio['id'] == audio_id:
                    audio['output_files'] = output_files
                    audio['status'] = 'completed'
                    break
            save_json('audios.json', audios)
            
            separation_progress[audio_id] = {'status': 'completed', 'progress': 100}
        else:
            # Erreur
            audios = load_json('audios.json')
            for audio in audios:
                if audio['id'] == audio_id:
                    audio['status'] = 'error'
                    audio['error'] = result.stderr[:200]
                    break
            save_json('audios.json', audios)
            separation_progress[audio_id] = {'status': 'error', 'progress': 0, 'error': result.stderr[:200]}
            
    except Exception as e:
        audios = load_json('audios.json')
        for audio in audios:
            if audio['id'] == audio_id:
                audio['status'] = 'error'
                audio['error'] = str(e)[:200]
                break
        save_json('audios.json', audios)
        separation_progress[audio_id] = {'status': 'error', 'progress': 0, 'error': str(e)[:200]}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        nom = request.form['nom'].strip()
        prenom = request.form['prenom'].strip()
        email = request.form['email'].strip()
        password = request.form['password']
        
        users = load_json('users.json')
        
        if any(u['email'] == email for u in users):
            flash('Cet email est déjà utilisé', 'error')
            return redirect(url_for('register'))
        
        photo_filename = 'default.jpg'
        if 'photo' in request.files:
            photo = request.files['photo']
            if photo.filename:
                ext = photo.filename.rsplit('.', 1)[1].lower()
                photo_filename = f"profile_{uuid.uuid4().hex}.{ext}"
                photo.save(os.path.join(UPLOAD_FOLDER, photo_filename))
        
        is_admin = is_admin_user(nom, prenom)
        
        new_user = {
            'id': len(users) + 1,
            'nom': nom,
            'prenom': prenom,
            'email': email,
            'password': hash_password(password),
            'photo_profil': photo_filename,
            'is_admin': is_admin,
            'created_at': datetime.now().isoformat()
        }
        
        users.append(new_user)
        save_json('users.json', users)
        
        session['user_id'] = new_user['id']
        session['is_admin'] = is_admin
        session['show_welcome'] = True
        
        return redirect(url_for('client'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = hash_password(request.form['password'])
        
        users = load_json('users.json')
        user = next((u for u in users if u['email'] == email and u['password'] == password), None)
        
        if user:
            session['user_id'] = user['id']
            session['is_admin'] = user['is_admin']
            return redirect(url_for('admin' if user['is_admin'] else 'client'))
        else:
            flash('Email ou mot de passe incorrect', 'error')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/client')
def client():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    users = load_json('users.json')
    user = next((u for u in users if u['id'] == session['user_id']), None)
    
    if not user:
        return redirect(url_for('logout'))
    
    audios = load_json('audios.json')
    user_audios = [a for a in audios if a['user_id'] == user['id']]
    
    show_welcome = session.pop('show_welcome', False)
    
    return render_template('client.html', user=user, audios=user_audios, show_welcome=show_welcome)

@app.route('/upload', methods=['POST'])
def upload():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    if 'audio' not in request.files:
        flash('Aucun fichier sélectionné', 'error')
        return redirect(url_for('client'))
    
    file = request.files['audio']
    if file.filename == '':
        flash('Aucun fichier sélectionné', 'error')
        return redirect(url_for('client'))
    
    if file and allowed_file(file.filename):
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)
        
        if file_size > MAX_FILE_SIZE:
            flash('Fichier trop volumineux (max 20 MB)', 'error')
            return redirect(url_for('client'))
        
        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4().hex}_{filename}"
        filepath = os.path.join(UPLOAD_FOLDER, unique_filename)
        file.save(filepath)
        
        # Créer entrée JSON
        audios = load_json('audios.json')
        audio_id = len(audios) + 1
        audios.append({
            'id': audio_id,
            'user_id': session['user_id'],
            'filename': filename,
            'stored_filename': unique_filename,
            'output_files': [],
            'created_at': datetime.now().isoformat(),
            'status': 'processing'
        })
        save_json('audios.json', audios)
        
        # Démarrer séparation en arrière-plan
        thread = threading.Thread(
            target=run_separation,
            args=(audio_id, filepath, filename, session['user_id'])
        )
        thread.daemon = True
        thread.start()
        
        flash('Séparation démarrée ! Suivez la progression ci-dessous.', 'success')
        return redirect(url_for('client'))
    else:
        flash('Format de fichier non supporté', 'error')
    
    return redirect(url_for('client'))

@app.route('/progress/<int:audio_id>')
def get_progress(audio_id):
    """API pour récupérer la progression"""
    progress = separation_progress.get(audio_id, {'status': 'unknown', 'progress': 0})
    return jsonify(progress)

@app.route('/feedback/<int:audio_id>', methods=['POST'])
def feedback(audio_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    feedback_text = request.form.get('feedback_text', '').strip()
    
    if feedback_text:
        feedbacks = load_json('feedbacks.json')
        feedbacks.append({
            'id': len(feedbacks) + 1,
            'audio_id': audio_id,
            'user_id': session['user_id'],
            'feedback_text': feedback_text,
            'created_at': datetime.now().isoformat()
        })
        save_json('feedbacks.json', feedbacks)
        flash('Merci pour votre feedback !', 'success')
    
    return redirect(url_for('client'))

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if 'user_id' not in session or not session.get('is_admin'):
        return redirect(url_for('client'))
    
    users = load_json('users.json')
    audios = load_json('audios.json')
    feedbacks = load_json('feedbacks.json')
    
    users_dict = {u['id']: u for u in users}
    
    # Upload admin
    if request.method == 'POST':
        if 'audio' in request.files:
            file = request.files['audio']
            if file and allowed_file(file.filename):
                file.seek(0, os.SEEK_END)
                file_size = file.tell()
                file.seek(0)
                
                if file_size <= MAX_FILE_SIZE:
                    filename = secure_filename(file.filename)
                    unique_filename = f"admin_{uuid.uuid4().hex}_{filename}"
                    filepath = os.path.join(UPLOAD_FOLDER, unique_filename)
                    file.save(filepath)
                    
                    audios_list = load_json('audios.json')
                    audio_id = len(audios_list) + 1
                    audios_list.append({
                        'id': audio_id,
                        'user_id': session['user_id'],
                        'filename': filename,
                        'stored_filename': unique_filename,
                        'output_files': [],
                        'created_at': datetime.now().isoformat(),
                        'status': 'processing'
                    })
                    save_json('audios.json', audios_list)
                    
                    thread = threading.Thread(
                        target=run_separation,
                        args=(audio_id, filepath, filename, session['user_id'])
                    )
                    thread.daemon = True
                    thread.start()
                    
                    flash('Séparation admin démarrée !', 'success')
                else:
                    flash('Fichier trop volumineux', 'error')
            return redirect(url_for('admin'))
    
    feedback_list = []
    for audio in audios:
        user = users_dict.get(audio['user_id'], {})
        audio_feedbacks = [f for f in feedbacks if f['audio_id'] == audio['id']]
        
        feedback_text = audio_feedbacks[0]['feedback_text'] if audio_feedbacks else "Aucun feedback"
        
        feedback_list.append({
            'audio_id': audio['id'],
            'audio_filename': audio['filename'],
            'user_name': f"{user.get('prenom', '')} {user.get('nom', '')}",
            'user_photo': user.get('photo_profil', 'default.jpg'),
            'feedback_text': feedback_text,
            'status': audio.get('status', 'unknown'),
            'created_at': audio.get('created_at', ''),
            'output_files': audio.get('output_files', [])
        })
    
    admin_audios = [a for a in audios if a['user_id'] == session['user_id']]
    
    stats = {
        'total_users': len([u for u in users if not u.get('is_admin', False)]),
        'total_audios': len(audios),
        'total_feedbacks': len(feedbacks)
    }
    
    return render_template('admin.html', 
                         feedback_list=feedback_list, 
                         stats=stats, 
                         admin_audios=admin_audios,
                         user=users_dict.get(session['user_id'], {}))

@app.route('/uploads/<path:filename>')
def serve_upload(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

@app.route('/audio/<path:filename>')
def serve_audio(filename):
    return send_from_directory(SEPARATED_FOLDER, filename)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
